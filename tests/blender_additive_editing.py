"""Headless tests for the non-destructive additive CANM editing workflow."""

import importlib
import importlib.util
import math
import sys
import tempfile
from pathlib import Path

import bpy
import mathutils


class Operator:
    def __init__(self):
        self.messages = []

    def report(self, levels, message):
        self.messages.append((levels, message))


def load_addon(addon_root):
    package_name = "_additive_editing_test"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    return package


def assert_vector_close(actual, expected, tolerance=1e-5):
    assert max(abs(actual[index] - expected[index]) for index in range(3)) < \
        tolerance, (actual, expected)


def assert_quaternion_close(actual, expected, tolerance=1e-5):
    actual = actual.normalized()
    expected = expected.normalized()
    assert abs(actual.dot(expected)) > 1.0 - tolerance, (actual, expected)


def add_transform_action(
    module,
    pose_bone,
    name,
    raw_transforms,
    duration,
    loop=False,
):
    action = bpy.data.actions.new(name)
    action["duration"] = float(duration)
    action["loop"] = bool(loop)
    action["keyframes"] = len(raw_transforms)
    rest_inverse = module.local_rest_matrix(pose_bone).inverted_safe()
    positions = []
    rotations = []
    previous = None
    for location, rotation in raw_transforms:
        basis = (
            rest_inverse
            @ mathutils.Matrix.LocRotScale(
                location,
                rotation,
                mathutils.Vector((1.0, 1.0, 1.0)),
            )
        )
        position, basis_rotation, _scale = basis.decompose()
        positions.append(tuple(position))
        values, previous = module.quaternion_values(basis_rotation, previous)
        rotations.append(values)
    module.replace_curve_samples(
        module.create_curves(action, pose_bone, "location", 3),
        positions,
    )
    module.replace_curve_samples(
        module.create_curves(
            action,
            pose_bone,
            "rotation_quaternion",
            4,
        ),
        rotations,
    )
    return action


def raw_action_transform(module, action, pose_bone, frame):
    rest = module.local_rest_matrix(pose_bone)
    channels = module.action_bone_channels(action, pose_bone)
    return module.raw_local_transform(rest, channels, float(frame))


def set_preview_raw_transform(
    module,
    action,
    pose_bone,
    frame,
    location,
    rotation,
):
    rest_inverse = module.local_rest_matrix(pose_bone).inverted_safe()
    basis = (
        rest_inverse
        @ mathutils.Matrix.LocRotScale(
            location,
            rotation,
            mathutils.Vector((1.0, 1.0, 1.0)),
        )
    )
    basis_location, basis_rotation, _scale = basis.decompose()
    channels = module.action_bone_channels(action, pose_bone)
    for index, curve in enumerate(channels["location"]):
        curve.keyframe_points[frame - 1].co.y = basis_location[index]
        curve.update()
    values = (
        basis_rotation.w,
        basis_rotation.x,
        basis_rotation.y,
        basis_rotation.z,
    )
    for index, curve in enumerate(channels["rotation_quaternion"]):
        curve.keyframe_points[frame - 1].co.y = values[index]
        curve.update()


def make_armature():
    armature = bpy.data.armatures.new("Additive test armature")
    obj = bpy.data.objects.new("Additive test armature", armature)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone = armature.edit_bones.new("offset_bone")
    bone.head = (1.0, 2.0, 0.5)
    bone.tail = (1.3, 3.0, 0.7)
    bone.roll = math.radians(17.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.animation_data_create()
    return obj, obj.pose.bones["offset_bone"]


def test_animated_base(module, armature_obj, pose_bone):
    base_raw = (
        (
            mathutils.Vector((1.0, 2.0, 3.0)),
            mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(10.0)),
        ),
        (
            mathutils.Vector((2.0, 3.0, 4.0)),
            mathutils.Quaternion((0.0, 1.0, 0.0), math.radians(35.0)),
        ),
        (
            mathutils.Vector((3.0, 4.0, 5.0)),
            mathutils.Quaternion((0.0, 0.0, 1.0), math.radians(-20.0)),
        ),
    )
    additive_raw = (
        (
            mathutils.Vector((0.1, -0.2, 0.3)),
            mathutils.Quaternion((0.0, 0.0, 1.0), math.radians(5.0)),
        ),
        (
            mathutils.Vector((0.2, -0.1, 0.4)),
            mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(15.0)),
        ),
        (
            mathutils.Vector((0.3, 0.0, 0.5)),
            mathutils.Quaternion((0.0, 1.0, 0.0), math.radians(25.0)),
        ),
    )
    base = add_transform_action(
        module,
        pose_bone,
        "normal_base",
        base_raw,
        duration=8.0,
    )
    additive = add_transform_action(
        module,
        pose_bone,
        "overlay_add",
        additive_raw,
        duration=8.0,
    )
    before = [
        raw_action_transform(module, additive, pose_bone, frame)
        for frame in range(1, 4)
    ]
    preview = module.build_preview_action(
        armature_obj,
        additive,
        base,
        "ACTION",
        1,
    )
    for frame in range(1, 4):
        location, rotation, _scale = raw_action_transform(
            module,
            preview,
            pose_bone,
            frame,
        )
        expected_location = base_raw[frame - 1][0] + additive_raw[frame - 1][0]
        expected_rotation = base_raw[frame - 1][1] @ additive_raw[frame - 1][1]
        assert_vector_close(location, expected_location)
        assert_quaternion_close(rotation, expected_rotation)

    # A no-edit save must preserve the source additive samples.
    module.save_preview_to_additive(
        armature_obj,
        preview,
        additive,
        base,
        "ACTION",
        1,
    )
    for frame, (old_location, old_rotation, _old_scale) in enumerate(before, 1):
        location, rotation, _scale = raw_action_transform(
            module,
            additive,
            pose_bone,
            frame,
        )
        assert_vector_close(location, old_location)
        assert_quaternion_close(rotation, old_rotation)

    # Editing the normal-looking preview must recover the matching raw delta.
    desired_location = mathutils.Vector((5.0, 7.0, 9.0))
    desired_rotation = mathutils.Quaternion(
        (0.0, 0.0, 1.0),
        math.radians(48.0),
    )
    set_preview_raw_transform(
        module,
        preview,
        pose_bone,
        2,
        desired_location,
        desired_rotation,
    )
    module.save_preview_to_additive(
        armature_obj,
        preview,
        additive,
        base,
        "ACTION",
        1,
    )
    location, rotation, _scale = raw_action_transform(
        module,
        additive,
        pose_bone,
        2,
    )
    assert_vector_close(location, desired_location - base_raw[1][0])
    assert_quaternion_close(
        rotation,
        base_raw[1][1].inverted() @ desired_rotation,
    )
    return base, additive, preview


def test_fixed_base(module, armature_obj, pose_bone, base, additive):
    original_duration = additive["duration"]
    additive["duration"] = 4.0
    fractional_frame = module.base_sample_frame(
        base,
        additive,
        2,
        "ACTION",
        1,
    )
    assert math.isclose(fractional_frame, 1.5)
    rest = module.local_rest_matrix(pose_bone)
    base_channels = module.action_bone_channels(base, pose_bone)
    location, rotation, _scale = module.sampled_raw_local_transform(
        rest,
        base_channels,
        fractional_frame,
    )
    first_location, first_rotation, _scale = raw_action_transform(
        module,
        base,
        pose_bone,
        1,
    )
    second_location, second_rotation, _scale = raw_action_transform(
        module,
        base,
        pose_bone,
        2,
    )
    assert_vector_close(location, first_location.lerp(second_location, 0.5))
    assert_quaternion_close(rotation, first_rotation.slerp(second_rotation, 0.5))
    additive["duration"] = original_duration

    preview = module.build_preview_action(
        armature_obj,
        additive,
        base,
        "FRAME",
        2,
    )
    base_location, base_rotation, _scale = raw_action_transform(
        module,
        base,
        pose_bone,
        2,
    )
    for frame in range(1, 4):
        add_location, add_rotation, _scale = raw_action_transform(
            module,
            additive,
            pose_bone,
            frame,
        )
        location, rotation, _scale = raw_action_transform(
            module,
            preview,
            pose_bone,
            frame,
        )
        assert_vector_close(location, base_location + add_location)
        assert_quaternion_close(rotation, base_rotation @ add_rotation)
    scale_curves = module.create_curves(
        preview,
        pose_bone,
        "scale",
        3,
    )
    module.replace_curve_samples(
        scale_curves,
        [(1.0, 1.0, 1.0), (1.1, 1.0, 1.0), (1.0, 1.0, 1.0)],
    )
    try:
        module.save_preview_to_additive(
            armature_obj,
            preview,
            additive,
            base,
            "FRAME",
            2,
        )
    except ValueError as error:
        assert "base-only, new, or scale channels" in str(error)
    else:
        raise AssertionError("An unsupported preview scale edit was accepted")


def test_session_restore(module, export_canm, armature_obj, base, additive):
    track = armature_obj.animation_data.nla_tracks.new()
    track.name = additive.name
    track.strips.new(additive.name, 1, additive)
    track.mute = False
    armature_obj.animation_data.action = base
    preview = module.build_preview_action(
        armature_obj,
        additive,
        base,
        "ACTION",
        1,
    )
    module.capture_session(armature_obj, preview, base)
    assert track.mute
    assert armature_obj.animation_data.action == preview
    operator = Operator()
    with tempfile.TemporaryDirectory() as temporary_directory:
        output = Path(temporary_directory) / "must_not_export.CANM"
        assert export_canm.save(
            operator,
            bpy.context,
            filepath=str(output),
            version=6,
        ) == {"CANCELLED"}
        assert not output.exists()
    assert any(
        "active additive editing session" in message
        for _levels, message in operator.messages
    )
    preview_name = preview.name
    module.restore_session(armature_obj, remove_preview=True)
    assert not track.mute
    assert armature_obj.animation_data.action == base
    assert bpy.data.actions.get(preview_name) is None


def main():
    addon_root = Path(__file__).resolve().parents[1]
    package = load_addon(addon_root)
    package.register()
    module = package.additive_editing
    export_canm = importlib.import_module(
        f"{package.__name__}.export_canm"
    )
    armature_obj, pose_bone = make_armature()
    base, additive, old_preview = test_animated_base(
        module,
        armature_obj,
        pose_bone,
    )
    bpy.data.actions.remove(old_preview)
    test_fixed_base(module, armature_obj, pose_bone, base, additive)
    test_session_restore(
        module,
        export_canm,
        armature_obj,
        base,
        additive,
    )
    package.unregister()
    print("Additive editing preview/save tests passed.")


if __name__ == "__main__":
    main()
