"""Non-destructive Blender editing workflow for CAS additive CANM clips."""

import hashlib
import json
import math
import struct

import bpy
import mathutils

from bpy.props import EnumProperty, IntProperty, StringProperty


PREVIEW_FLAG = "edf_additive_edit_preview"
SOURCE_NAME = "edf_additive_source_action"
BASE_NAME = "edf_additive_base_action"
BASE_MODE = "edf_additive_base_mode"
BASE_FRAME = "edf_additive_base_frame"
SESSION = "edf_additive_edit_session"
PREVIEW_DIGEST = "edf_additive_preview_digest"
PREVIEW_CHANNEL_DIGESTS = "edf_additive_preview_channel_digests"
SOURCE_DIGEST = "edf_additive_source_digest"
BASE_DIGEST = "edf_additive_base_digest"

TRANSFORM_PROPERTIES = (
    ("location", 3),
    ("rotation_quaternion", 4),
    ("scale", 3),
)


def canm_action(action):
    return (
        action is not None
        and not action.get(PREVIEW_FLAG, False)
        and all(name in action for name in ("duration", "loop", "keyframes"))
    )


def active_armature(context):
    obj = context.active_object
    if obj is not None and obj.type == "ARMATURE":
        return obj
    return None


def action_sample_count(action):
    value = action.get("keyframes")
    count = int(value)
    if count != value or count <= 0:
        raise ValueError(
            f"Action {action.name!r} has invalid CANM sample count {value!r}"
        )
    return count


def action_duration(action):
    duration = float(action.get("duration"))
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError(
            f"Action {action.name!r} has invalid CANM duration {duration!r}"
        )
    return duration


def local_rest_matrix(pose_bone):
    matrix = pose_bone.bone.matrix_local.copy()
    if pose_bone.parent is not None:
        matrix = (
            pose_bone.parent.bone.matrix_local.inverted_safe()
            @ matrix
        )
    return matrix


def transform_curves(action, bone_name, property_name, component_count):
    data_path = f'pose.bones["{bone_name}"].{property_name}'
    curves = [
        action.fcurves.find(data_path, index=index)
        for index in range(component_count)
    ]
    present = [curve is not None for curve in curves]
    if any(present) and not all(present):
        missing = [
            str(index) for index, is_present in enumerate(present)
            if not is_present
        ]
        raise ValueError(
            f"Action {action.name!r}, bone {bone_name!r}: "
            f"{property_name} has incomplete component curves "
            f"({', '.join(missing)} missing)"
        )
    if not any(present):
        return None
    if any(not curve.keyframe_points and not curve.modifiers for curve in curves):
        raise ValueError(
            f"Action {action.name!r}, bone {bone_name!r}: "
            f"{property_name} contains an empty component curve"
        )
    return curves


def action_bone_channels(action, pose_bone):
    result = {}
    for property_name, component_count in TRANSFORM_PROPERTIES:
        result[property_name] = transform_curves(
            action,
            pose_bone.name,
            property_name,
            component_count,
        )
    return result


def evaluate_channels(channels, frame):
    location_curves = channels["location"]
    rotation_curves = channels["rotation_quaternion"]
    scale_curves = channels["scale"]
    location = mathutils.Vector((0.0, 0.0, 0.0))
    rotation = mathutils.Quaternion((1.0, 0.0, 0.0, 0.0))
    scale = mathutils.Vector((1.0, 1.0, 1.0))
    if location_curves:
        location = mathutils.Vector(
            curve.evaluate(frame) for curve in location_curves
        )
    if rotation_curves:
        rotation = mathutils.Quaternion(
            curve.evaluate(frame) for curve in rotation_curves
        )
        if rotation.magnitude == 0.0:
            raise ValueError("Encountered a zero-length rotation quaternion")
        rotation.normalize()
    if scale_curves:
        scale = mathutils.Vector(curve.evaluate(frame) for curve in scale_curves)
    return location, rotation, scale


def raw_local_transform(rest_matrix, channels, frame):
    location, rotation, scale = evaluate_channels(channels, frame)
    basis = mathutils.Matrix.LocRotScale(location, rotation, scale)
    return (rest_matrix @ basis).decompose()


def sampled_raw_local_transform(rest_matrix, channels, frame):
    lower_frame = math.floor(frame)
    upper_frame = math.ceil(frame)
    if lower_frame == upper_frame:
        return raw_local_transform(rest_matrix, channels, float(lower_frame))
    blend = frame - lower_frame
    lower = raw_local_transform(rest_matrix, channels, float(lower_frame))
    upper = raw_local_transform(rest_matrix, channels, float(upper_frame))
    location = lower[0].lerp(upper[0], blend)
    rotation = lower[1].slerp(upper[1], blend)
    rotation.normalize()
    scale = lower[2].lerp(upper[2], blend)
    return location, rotation, scale


def base_sample_frame(base_action, source_action, source_frame, mode, fixed_frame):
    base_count = action_sample_count(base_action)
    if mode == "FRAME":
        return min(max(float(fixed_frame), 1.0), float(base_count))

    source_count = action_sample_count(source_action)
    if source_count == 1:
        source_time = 0.0
    else:
        source_time = (
            (source_frame - 1.0)
            * action_duration(source_action)
            / (source_count - 1)
        )
    if base_count == 1:
        return 1.0
    base_interval = action_duration(base_action) / (base_count - 1)
    sample_position = source_time / base_interval
    if bool(base_action.get("loop", False)):
        sample_position %= (base_count - 1)
    else:
        sample_position = min(max(sample_position, 0.0), base_count - 1)
    return sample_position + 1.0


def compose_additive(
    rest_components,
    base_components,
    additive_components,
    base_channels,
    additive_channels,
):
    rest_location, rest_rotation, rest_scale = rest_components
    base_location, base_rotation, base_scale = base_components
    add_location, add_rotation, _add_scale = additive_components

    if additive_channels["location"]:
        location = (
            base_location + add_location
            if base_channels["location"]
            else add_location.copy()
        )
    elif base_channels["location"]:
        location = base_location.copy()
    else:
        location = rest_location.copy()

    if additive_channels["rotation_quaternion"]:
        rotation = (
            base_rotation @ add_rotation
            if base_channels["rotation_quaternion"]
            else add_rotation.copy()
        )
    elif base_channels["rotation_quaternion"]:
        rotation = base_rotation.copy()
    else:
        rotation = rest_rotation.copy()
    rotation.normalize()

    # CAS additive tag 0x08 takes scale only from operand A (the base).
    scale = (
        base_scale.copy()
        if base_channels["scale"]
        else rest_scale.copy()
    )
    return location, rotation, scale


def create_curves(action, pose_bone, property_name, component_count):
    data_path = f'pose.bones["{pose_bone.name}"].{property_name}'
    return [
        action.fcurves.new(
            data_path,
            index=index,
            action_group=pose_bone.name,
        )
        for index in range(component_count)
    ]


def replace_curve_samples(curves, samples):
    for curve, values in zip(curves, zip(*samples)):
        while curve.keyframe_points:
            curve.keyframe_points.remove(curve.keyframe_points[-1])
        for frame, value in enumerate(values, 1):
            point = curve.keyframe_points.insert(float(frame), float(value))
            point.interpolation = "LINEAR"
        curve.update()


def quaternion_values(quaternion, previous):
    value = quaternion.copy()
    value.normalize()
    if previous is not None and value.dot(previous) < 0.0:
        value.negate()
    return (value.w, value.x, value.y, value.z), value


def action_sample_digest(action, sample_count):
    digest = hashlib.sha256()
    curves = sorted(
        action.fcurves,
        key=lambda curve: (curve.data_path, curve.array_index),
    )
    for curve in curves:
        digest.update(curve.data_path.encode("utf-8"))
        digest.update(struct.pack("<i", curve.array_index))
        for frame in range(1, sample_count + 1):
            digest.update(struct.pack("<d", curve.evaluate(float(frame))))
    return digest.hexdigest()


def action_channel_digests(action, sample_count):
    grouped = {}
    for curve in action.fcurves:
        grouped.setdefault(curve.data_path, []).append(curve)
    result = {}
    for data_path, curves in grouped.items():
        digest = hashlib.sha256()
        for curve in sorted(curves, key=lambda item: item.array_index):
            digest.update(struct.pack("<i", curve.array_index))
            for frame in range(1, sample_count + 1):
                digest.update(struct.pack("<d", curve.evaluate(float(frame))))
        result[data_path] = digest.hexdigest()
    return result


def build_preview_action(
    armature_obj,
    additive_action,
    base_action,
    mode,
    fixed_frame,
):
    sample_count = action_sample_count(additive_action)
    action_duration(additive_action)
    action_sample_count(base_action)
    action_duration(base_action)

    preview = bpy.data.actions.new(
        name=f"{additive_action.name} [Additive Edit]"
    )
    preview["duration"] = float(additive_action["duration"])
    preview["loop"] = bool(additive_action["loop"])
    preview["keyframes"] = sample_count
    preview[PREVIEW_FLAG] = True
    preview[SOURCE_NAME] = additive_action.name
    preview[BASE_NAME] = base_action.name
    preview[BASE_MODE] = mode
    preview[BASE_FRAME] = int(fixed_frame)

    for pose_bone in armature_obj.pose.bones:
        additive_channels = action_bone_channels(additive_action, pose_bone)
        base_channels = action_bone_channels(base_action, pose_bone)
        output_position = bool(
            additive_channels["location"] or base_channels["location"]
        )
        output_rotation = bool(
            additive_channels["rotation_quaternion"]
            or base_channels["rotation_quaternion"]
        )
        output_scale = bool(base_channels["scale"])
        if not (output_position or output_rotation or output_scale):
            continue

        rest_matrix = local_rest_matrix(pose_bone)
        rest_inverse = rest_matrix.inverted_safe()
        rest_components = rest_matrix.decompose()
        positions = []
        rotations = []
        scales = []
        previous_rotation = None
        for source_frame in range(1, sample_count + 1):
            sampled_base_frame = base_sample_frame(
                base_action,
                additive_action,
                source_frame,
                mode,
                fixed_frame,
            )
            base_components = sampled_raw_local_transform(
                rest_matrix,
                base_channels,
                sampled_base_frame,
            )
            additive_components = raw_local_transform(
                rest_matrix,
                additive_channels,
                float(source_frame),
            )
            combined = compose_additive(
                rest_components,
                base_components,
                additive_components,
                base_channels,
                additive_channels,
            )
            basis = (
                rest_inverse
                @ mathutils.Matrix.LocRotScale(*combined)
            )
            position, rotation, scale = basis.decompose()
            positions.append(tuple(position))
            rotation_values, previous_rotation = quaternion_values(
                rotation,
                previous_rotation,
            )
            rotations.append(rotation_values)
            scales.append(tuple(scale))

        if output_position:
            replace_curve_samples(
                create_curves(preview, pose_bone, "location", 3),
                positions,
            )
        if output_rotation:
            replace_curve_samples(
                create_curves(
                    preview,
                    pose_bone,
                    "rotation_quaternion",
                    4,
                ),
                rotations,
            )
        if output_scale:
            replace_curve_samples(
                create_curves(preview, pose_bone, "scale", 3),
                scales,
            )
    preview[PREVIEW_DIGEST] = action_sample_digest(preview, sample_count)
    preview[PREVIEW_CHANNEL_DIGESTS] = json.dumps(
        action_channel_digests(preview, sample_count),
        sort_keys=True,
    )
    preview[SOURCE_DIGEST] = action_sample_digest(
        additive_action,
        sample_count,
    )
    preview[BASE_DIGEST] = action_sample_digest(
        base_action,
        action_sample_count(base_action),
    )
    return preview


def save_preview_to_additive(
    armature_obj,
    preview,
    additive_action,
    base_action,
    mode,
    fixed_frame,
):
    sample_count = action_sample_count(additive_action)
    if action_sample_count(preview) != sample_count:
        raise ValueError("The additive preview sample count was changed")
    if (
        float(preview.get("duration")) != action_duration(additive_action)
        or bool(preview.get("loop")) != bool(additive_action.get("loop"))
    ):
        raise ValueError(
            "The additive preview timing metadata was changed; restore it "
            "or cancel the session"
        )
    if preview.get(SOURCE_DIGEST) != action_sample_digest(
        additive_action,
        sample_count,
    ):
        raise ValueError(
            "The source additive Action changed outside the preview; "
            "cancel this session and start again"
        )
    if preview.get(BASE_DIGEST) != action_sample_digest(
        base_action,
        action_sample_count(base_action),
    ):
        raise ValueError(
            "The base Action changed during additive editing; cancel this "
            "session and start again"
        )
    if preview.get(PREVIEW_DIGEST) == action_sample_digest(
        preview,
        sample_count,
    ):
        return any(
            action_bone_channels(additive_action, pose_bone)["scale"]
            for pose_bone in armature_obj.pose.bones
        )
    try:
        original_channel_digests = json.loads(
            preview[PREVIEW_CHANNEL_DIGESTS]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "The additive preview's channel safety metadata is damaged"
        ) from error
    current_channel_digests = action_channel_digests(preview, sample_count)
    changed_paths = {
        data_path
        for data_path in (
            set(original_channel_digests) | set(current_channel_digests)
        )
        if original_channel_digests.get(data_path)
        != current_channel_digests.get(data_path)
    }
    writable_paths = set()
    for pose_bone in armature_obj.pose.bones:
        channels = action_bone_channels(additive_action, pose_bone)
        for property_name in ("location", "rotation_quaternion"):
            if channels[property_name]:
                writable_paths.add(
                    f'pose.bones["{pose_bone.name}"].{property_name}'
                )
    unsupported_paths = sorted(changed_paths - writable_paths)
    if unsupported_paths:
        summary = ", ".join(unsupported_paths[:4])
        if len(unsupported_paths) > 4:
            summary += f", and {len(unsupported_paths) - 4} more"
        raise ValueError(
            "The preview changes base-only, new, or scale channels that "
            f"cannot be stored in this additive Action: {summary}. "
            "Undo those channel edits or cancel the session"
        )

    ignored_scale = False
    for pose_bone in armature_obj.pose.bones:
        additive_channels = action_bone_channels(additive_action, pose_bone)
        if not any(additive_channels.values()):
            continue
        base_channels = action_bone_channels(base_action, pose_bone)
        preview_channels = action_bone_channels(preview, pose_bone)
        if additive_channels["location"] and not preview_channels["location"]:
            raise ValueError(
                f"Preview action lost location curves for bone {pose_bone.name!r}"
            )
        if (
            additive_channels["rotation_quaternion"]
            and not preview_channels["rotation_quaternion"]
        ):
            raise ValueError(
                f"Preview action lost rotation curves for bone {pose_bone.name!r}"
            )

        rest_matrix = local_rest_matrix(pose_bone)
        rest_inverse = rest_matrix.inverted_safe()
        positions = []
        rotations = []
        previous_rotation = None
        for source_frame in range(1, sample_count + 1):
            frame = float(source_frame)
            sampled_base_frame = base_sample_frame(
                base_action,
                additive_action,
                source_frame,
                mode,
                fixed_frame,
            )
            base_location, base_rotation, _base_scale = (
                sampled_raw_local_transform(
                    rest_matrix,
                    base_channels,
                    sampled_base_frame,
                )
            )
            preview_location, preview_rotation, _preview_scale = (
                raw_local_transform(rest_matrix, preview_channels, frame)
            )
            old_location, old_rotation, old_scale = raw_local_transform(
                rest_matrix,
                additive_channels,
                frame,
            )

            delta_location = old_location
            if additive_channels["location"]:
                delta_location = (
                    preview_location - base_location
                    if base_channels["location"]
                    else preview_location
                )
            delta_rotation = old_rotation
            if additive_channels["rotation_quaternion"]:
                delta_rotation = (
                    base_rotation.inverted() @ preview_rotation
                    if base_channels["rotation_quaternion"]
                    else preview_rotation
                )
                delta_rotation.normalize()

            delta_basis = (
                rest_inverse
                @ mathutils.Matrix.LocRotScale(
                    delta_location,
                    delta_rotation,
                    old_scale,
                )
            )
            position, rotation, _scale = delta_basis.decompose()
            positions.append(tuple(position))
            rotation_values, previous_rotation = quaternion_values(
                rotation,
                previous_rotation,
            )
            rotations.append(rotation_values)

        if additive_channels["location"]:
            replace_curve_samples(additive_channels["location"], positions)
        if additive_channels["rotation_quaternion"]:
            replace_curve_samples(
                additive_channels["rotation_quaternion"],
                rotations,
            )
        if additive_channels["scale"]:
            ignored_scale = True
    return ignored_scale


def capture_session(armature_obj, preview, previous_action):
    animation_data = armature_obj.animation_data
    state = {
        "preview": preview.name,
        "previous_action": previous_action.name if previous_action else "",
        "track_mutes": [bool(track.mute) for track in animation_data.nla_tracks],
    }
    armature_obj[SESSION] = json.dumps(state)
    for track in animation_data.nla_tracks:
        track.mute = True
    animation_data.action = preview


def read_session(armature_obj):
    serialized = armature_obj.get(SESSION)
    if not serialized:
        return None
    try:
        return json.loads(serialized)
    except (TypeError, ValueError) as error:
        raise ValueError("The stored additive editing session is damaged") from error


def restore_session(armature_obj, remove_preview):
    state = read_session(armature_obj)
    if state is None:
        return
    animation_data = armature_obj.animation_data
    animation_data.action = None
    for index, mute in enumerate(state.get("track_mutes", [])):
        if index < len(animation_data.nla_tracks):
            animation_data.nla_tracks[index].mute = bool(mute)
    previous_name = state.get("previous_action", "")
    if previous_name:
        animation_data.action = bpy.data.actions.get(previous_name)
    preview = bpy.data.actions.get(state.get("preview", ""))
    del armature_obj[SESSION]
    if (
        remove_preview
        and preview is not None
        and preview.get(PREVIEW_FLAG, False)
    ):
        bpy.data.actions.remove(preview)


def session_actions(armature_obj):
    state = read_session(armature_obj)
    if state is None:
        raise ValueError("No additive editing session is active")
    preview = bpy.data.actions.get(state.get("preview", ""))
    if preview is None or not preview.get(PREVIEW_FLAG, False):
        raise ValueError("The additive preview Action no longer exists")
    source = bpy.data.actions.get(preview.get(SOURCE_NAME, ""))
    base = bpy.data.actions.get(preview.get(BASE_NAME, ""))
    if source is None:
        raise ValueError(
            "The source additive Action was deleted or renamed during editing"
        )
    if base is None:
        raise ValueError(
            "The base Action was deleted or renamed during editing"
        )
    return preview, source, base


class EDF_OT_start_additive_editing(bpy.types.Operator):
    """Create an editable normal-pose preview of a CANM additive Action"""

    bl_idname = "edf.start_additive_editing"
    bl_label = "Start Additive Editing"
    bl_options = {"REGISTER", "UNDO"}

    additive_action: StringProperty(name="Additive Action")
    base_action: StringProperty(name="Base Action")
    base_mode: EnumProperty(
        name="Base Sampling",
        items=(
            (
                "ACTION",
                "Animated Action",
                "Sample the base in CANM game time, respecting duration and looping",
            ),
            (
                "FRAME",
                "Fixed Frame",
                "Hold one frame of the base Action for the complete additive clip",
            ),
        ),
        default="ACTION",
    )
    base_frame: IntProperty(
        name="Base Frame",
        description="One-based sample frame used by Fixed Frame mode",
        default=1,
        min=1,
    )

    @classmethod
    def poll(cls, context):
        obj = active_armature(context)
        return obj is not None and obj.mode != "EDIT"

    def invoke(self, context, event):
        obj = active_armature(context)
        if obj is not None and obj.animation_data is not None:
            current = obj.animation_data.action
            if canm_action(current):
                self.additive_action = current.name
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        layout.prop_search(
            self,
            "additive_action",
            bpy.data,
            "actions",
            text="Additive",
        )
        layout.prop_search(
            self,
            "base_action",
            bpy.data,
            "actions",
            text="Base",
        )
        layout.prop(self, "base_mode")
        if self.base_mode == "FRAME":
            layout.prop(self, "base_frame")
        layout.label(
            text="Only channels already present in the additive Action are saved.",
            icon="INFO",
        )

    def execute(self, context):
        obj = active_armature(context)
        preview = None
        action_names_before = {action.name for action in bpy.data.actions}
        try:
            if read_session(obj) is not None:
                raise ValueError(
                    "Finish or cancel the current additive editing session first"
                )
            additive = bpy.data.actions.get(self.additive_action)
            base = bpy.data.actions.get(self.base_action)
            if not canm_action(additive):
                raise ValueError(
                    "Choose an additive Action with CANM metadata"
                )
            if not canm_action(base):
                raise ValueError("Choose a base Action with CANM metadata")
            if additive == base:
                raise ValueError("The additive and base Actions must differ")
            if obj.animation_data is None:
                obj.animation_data_create()
            previous_action = obj.animation_data.action
            preview = build_preview_action(
                obj,
                additive,
                base,
                self.base_mode,
                self.base_frame,
            )
            capture_session(obj, preview, previous_action)
            context.scene.frame_start = 1
            context.scene.frame_end = action_sample_count(additive)
            context.scene.frame_set(1)
        except (KeyError, TypeError, ValueError) as error:
            if obj.get(SESSION) is None:
                for candidate in list(bpy.data.actions):
                    if (
                        candidate.name not in action_names_before
                        and candidate.get(PREVIEW_FLAG, False)
                    ):
                        bpy.data.actions.remove(candidate)
            self.report({"ERROR"}, f"Could not start additive editing: {error}")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Additive preview created. Edit this Action, then use "
            "Save Additive Editing.",
        )
        return {"FINISHED"}


class EDF_OT_save_additive_editing(bpy.types.Operator):
    """Bake the edited preview back into the original additive CANM Action"""

    bl_idname = "edf.save_additive_editing"
    bl_label = "Save Additive Editing"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = active_armature(context)
        return obj is not None and obj.get(SESSION) is not None

    def execute(self, context):
        obj = active_armature(context)
        try:
            preview, additive, base = session_actions(obj)
            ignored_scale = save_preview_to_additive(
                obj,
                preview,
                additive,
                base,
                preview[BASE_MODE],
                int(preview[BASE_FRAME]),
            )
            restore_session(obj, remove_preview=True)
            context.scene.frame_set(context.scene.frame_current)
        except (KeyError, TypeError, ValueError) as error:
            self.report({"ERROR"}, f"Could not save additive editing: {error}")
            return {"CANCELLED"}
        if ignored_scale:
            self.report(
                {"WARNING"},
                "Saved translation/rotation. Existing additive scale curves "
                "were preserved because CAS additive composition ignores them.",
            )
        else:
            self.report(
                {"INFO"},
                f"Saved edited deltas to additive Action {additive.name!r}.",
            )
        return {"FINISHED"}


class EDF_OT_cancel_additive_editing(bpy.types.Operator):
    """Discard the temporary additive preview without changing its source"""

    bl_idname = "edf.cancel_additive_editing"
    bl_label = "Cancel Additive Editing"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = active_armature(context)
        return obj is not None and obj.get(SESSION) is not None

    def execute(self, context):
        obj = active_armature(context)
        try:
            restore_session(obj, remove_preview=True)
            context.scene.frame_set(context.scene.frame_current)
        except (TypeError, ValueError) as error:
            self.report({"ERROR"}, f"Could not cancel additive editing: {error}")
            return {"CANCELLED"}
        return {"FINISHED"}


class EDF_PT_additive_editing(bpy.types.Panel):
    bl_label = "EDF Additive Animation"
    bl_idname = "EDF_PT_additive_editing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Animation"

    def draw(self, context):
        layout = self.layout
        obj = active_armature(context)
        if obj is None:
            layout.label(text="Select an armature to edit CANM actions.", icon="INFO")
            return
        if obj.get(SESSION) is None:
            layout.operator(
                EDF_OT_start_additive_editing.bl_idname,
                icon="ACTION",
            )
            layout.label(
                text="Select source and base in the dialog.",
                icon="INFO",
            )
            return
        try:
            preview, source, base = session_actions(obj)
            layout.label(text=f"Editing: {source.name}")
            layout.label(text=f"Base: {base.name}")
            if preview[BASE_MODE] == "FRAME":
                layout.label(text=f"Fixed base frame: {preview[BASE_FRAME]}")
            else:
                layout.label(text="Base sampled in CANM time")
        except ValueError as error:
            layout.label(text=str(error), icon="ERROR")
        row = layout.row(align=True)
        row.operator(
            EDF_OT_save_additive_editing.bl_idname,
            icon="CHECKMARK",
        )
        row.operator(
            EDF_OT_cancel_additive_editing.bl_idname,
            icon="CANCEL",
        )


CLASSES = (
    EDF_OT_start_additive_editing,
    EDF_OT_save_additive_editing,
    EDF_OT_cancel_additive_editing,
    EDF_PT_additive_editing,
)
