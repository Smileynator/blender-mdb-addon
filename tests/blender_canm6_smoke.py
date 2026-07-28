"""Exercise EDF6 CANM channel encoding and decoding in Blender."""

import importlib.util
import io
import math
import sys
import tempfile
from pathlib import Path
from struct import unpack

import bpy
import mathutils


class Operator:
    def __init__(self):
        self.messages = []

    def report(self, levels, message):
        self.messages.append((levels, message))


def load_addon(addon_root):
    package_name = "_canm6_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


def assert_scale_action_round_trip(export_canm, import_canm):
    armature = bpy.data.armatures.new("CANM scale test")
    armature_obj = bpy.data.objects.new("CANM scale test", armature)
    bpy.context.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bone = armature.edit_bones.new("scale_bone")
    edit_bone.head = (0.0, 0.0, 0.0)
    edit_bone.tail = (0.0, 1.0, 0.0)
    bpy.ops.object.mode_set(mode="OBJECT")

    scale_point = {
        "base_x": 0.55,
        "base_y": 0.98,
        "base_z": 0.56,
        "speed_x": (1.01 - 0.55) / 65535.0,
        "speed_y": (1.00 - 0.98) / 65535.0,
        "speed_z": (1.06 - 0.56) / 65535.0,
        "keyframes": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 65535.0, "y": 65535.0, "z": 65535.0},
        ],
    }
    bone_animation = {
        "bone_id": 0,
        "point_trans_id": -1,
        "point_rot_id": -1,
        "point_scale_id": 0,
    }
    animation = {
        "name": "scale_round_trip",
        "loop": False,
        "duration": 4.0,
        "keyframes": 2,
        "bone_data": [bone_animation],
    }
    canm = {
        "bone_names": ["scale_bone"],
        "anm_points": [scale_point],
    }
    pose_bone = armature_obj.pose.bones["scale_bone"]
    import_canm.create_action_with_animation(
        armature_obj,
        animation,
        canm,
        [(0, pose_bone)],
    )

    action = armature_obj.animation_data.nla_tracks[-1].strips[0].action
    exported_bone = export_canm.get_bone_data(
        action,
        canm["bone_names"],
        [pose_bone],
    )[0]
    exported_scales = export_canm.get_matrix_channel_from_curves(
        animation,
        exported_bone,
        5,
    )["scale"]
    expected_scales = (
        mathutils.Vector((0.55, 0.98, 0.56)),
        mathutils.Vector((1.01, 1.00, 1.06)),
    )
    for actual, expected in zip(exported_scales, expected_scales):
        assert max(abs(actual[i] - expected[i]) for i in range(3)) < 1e-6

    encoded_scale = export_canm.vector_to_channel(exported_scales, True)
    decoded_scales = [
        mathutils.Vector((
            encoded_scale["base_x"] + x * encoded_scale["speed_x"],
            encoded_scale["base_y"] + y * encoded_scale["speed_y"],
            encoded_scale["base_z"] + z * encoded_scale["speed_z"],
        ))
        for x, y, z in zip(
            encoded_scale["offsets_x"],
            encoded_scale["offsets_y"],
            encoded_scale["offsets_z"],
        )
    ]
    for actual, expected in zip(decoded_scales, expected_scales):
        assert max(abs(actual[i] - expected[i]) for i in range(3)) < 1e-5


def assert_direct_curve_construction_matches_pose_insertion(
    import_canm,
    action_compat,
):
    armature = bpy.data.armatures.new("CANM direct curve test")
    armature_obj = bpy.data.objects.new("CANM direct curve test", armature)
    bpy.context.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    armature_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    parent = armature.edit_bones.new("direct_parent")
    parent.head = (0.4, -0.2, 0.3)
    parent.tail = (0.7, 1.1, 0.5)
    parent.roll = math.radians(21.0)
    child = armature.edit_bones.new("direct_child")
    child.parent = parent
    child.head = (0.7, 1.1, 0.5)
    child.tail = (1.2, 2.0, 0.9)
    child.roll = math.radians(-14.0)
    bpy.ops.object.mode_set(mode="POSE")
    pose_bones = [
        armature_obj.pose.bones["direct_parent"],
        armature_obj.pose.bones["direct_child"],
    ]

    vector_frames = [
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"x": 1.0, "y": 2.0, "z": 3.0},
        {"x": 2.0, "y": 4.0, "z": 6.0},
    ]
    quaternion_frames = []
    for angle in (5.0, 25.0, 55.0):
        value = mathutils.Quaternion(
            (0.2, 0.8, 0.4),
            math.radians(angle),
        )
        quaternion_frames.append({
            "x": value.x,
            "y": value.y,
            "z": value.z,
            "w": value.w,
        })
    canm = {
        "anm_points": [
            {
                "type": 1,
                "base_x": 1.0,
                "base_y": -2.0,
                "base_z": 0.5,
                "speed_x": 0.2,
                "speed_y": 0.1,
                "speed_z": -0.05,
                "keyframes": vector_frames,
            },
            {
                "type": 3,
                "base_x": 0.0,
                "base_y": 0.0,
                "base_z": 0.0,
                "base_w": 1.0,
                "keyframes": quaternion_frames,
            },
            {
                "type": 1,
                "base_x": 0.9,
                "base_y": 1.0,
                "base_z": 1.1,
                "speed_x": 0.02,
                "speed_y": -0.01,
                "speed_z": 0.03,
                "keyframes": vector_frames,
            },
        ],
    }
    bone_data = [
        {
            "bone_id": index,
            "point_trans_id": 0,
            "point_rot_id": 1,
            "point_scale_id": 2,
        }
        for index in range(2)
    ]
    animation = {
        "name": "direct_curve_equivalence",
        "loop": False,
        "duration": 8.0,
        "keyframes": 3,
        "bone_data": bone_data,
    }

    expected = {}
    for frame_index in range(3):
        for pose_bone, bone_anim in zip(pose_bones, bone_data):
            result = import_canm.get_bone_matrix_of_frame(
                canm,
                bone_anim,
                frame_index,
            )
            parent_matrix = (
                pose_bone.parent.matrix
                if pose_bone.parent
                else mathutils.Matrix.Identity(4)
            )
            pose_bone.matrix = parent_matrix @ result["matrix"]
            expected[(pose_bone.name, frame_index + 1)] = (
                pose_bone.location.copy(),
                pose_bone.rotation_quaternion.copy(),
                pose_bone.scale.copy(),
            )
    for pose_bone in pose_bones:
        pose_bone.matrix_basis = mathutils.Matrix.Identity(4)
    bpy.ops.object.mode_set(mode="OBJECT")

    import_canm.create_action_with_animation(
        armature_obj,
        animation,
        canm,
        list(enumerate(pose_bones)),
    )
    action = armature_obj.animation_data.nla_tracks[-1].strips[0].action
    curves = action_compat.action_fcurves(action)
    for pose_bone in pose_bones:
        paths = {
            property_name: [
                curves.find(
                    f'pose.bones["{pose_bone.name}"].{property_name}',
                    index=index,
                )
                for index in range(component_count)
            ]
            for property_name, component_count in (
                ("location", 3),
                ("rotation_quaternion", 4),
                ("scale", 3),
            )
        }
        for frame in range(1, 4):
            expected_location, expected_rotation, expected_scale = expected[
                (pose_bone.name, frame)
            ]
            actual_location = mathutils.Vector(
                curve.evaluate(frame) for curve in paths["location"]
            )
            actual_rotation = mathutils.Quaternion(
                curve.evaluate(frame)
                for curve in paths["rotation_quaternion"]
            )
            actual_scale = mathutils.Vector(
                curve.evaluate(frame) for curve in paths["scale"]
            )
            assert (actual_location - expected_location).length < 1e-5
            assert abs(actual_rotation.normalized().dot(
                expected_rotation.normalized()
            )) > 1.0 - 1e-6
            assert (actual_scale - expected_scale).length < 1e-5


def assert_curve_validation(export_canm, action_compat):
    armature_obj = bpy.data.objects["CANM scale test"]
    pose_bone = armature_obj.pose.bones["scale_bone"]

    partial_action = bpy.data.actions.new("partial_location")
    partial_action["duration"] = 4.0
    partial_action["loop"] = False
    partial_action["keyframes"] = 2
    partial_curves = action_compat.initialize_action_fcurves(
        partial_action,
        armature_obj,
    )
    action_compat.new_fcurve(
        partial_curves,
        'pose.bones["scale_bone"].location',
        index=0,
    ).keyframe_points.insert(1.0, 0.0)
    try:
        export_canm.get_bone_data(
            partial_action,
            ["scale_bone"],
            [pose_bone],
        )
    except ValueError as error:
        assert "missing component curve(s) Y, Z" in str(error)
    else:
        raise AssertionError("Partial XYZ curves were silently accepted")

    complete_action = bpy.data.actions.new("yz_animated_scale")
    complete_curves = action_compat.initialize_action_fcurves(
        complete_action,
        armature_obj,
    )
    scale_curves = []
    for index in range(3):
        curve = action_compat.new_fcurve(
            complete_curves,
            'pose.bones["scale_bone"].scale',
            index=index,
        )
        curve.keyframe_points.insert(1.0, 1.0)
        scale_curves.append(curve)
    scale_curves[1].keyframe_points.insert(2.0, 1.5)
    assert export_canm.curves_have_animation(scale_curves)

    track = armature_obj.animation_data.nla_tracks.new()
    track.name = partial_action.name
    track.strips.new(partial_action.name, 1, partial_action)
    operator = Operator()
    output_path = Path(tempfile.gettempdir()) / "mdb_invalid_canm_test.CANM"
    if output_path.exists():
        output_path.unlink()
    result = export_canm.save(
        operator,
        bpy.context,
        filepath=str(output_path),
        version=5,
    )
    assert result == {"CANCELLED"}
    assert not output_path.exists()
    assert any(
        "missing component curve(s) Y, Z" in message
        for _, message in operator.messages
    )
    armature_obj.animation_data.nla_tracks.remove(track)


def assert_channel_deduplication(export_canm):
    position_a = export_canm.vector_to_channel(
        [
            mathutils.Vector((1.0, 2.0, 3.0)),
            mathutils.Vector((2.0, 3.0, 4.0)),
        ],
        True,
    )
    position_close = export_canm.vector_to_channel(
        [
            mathutils.Vector((1.00001, 2.00001, 3.00001)),
            mathutils.Vector((2.00001, 3.00001, 4.00001)),
        ],
        True,
    )
    position_far = export_canm.vector_to_channel(
        [
            mathutils.Vector((1.00003, 2.00003, 3.00003)),
            mathutils.Vector((2.00003, 3.00003, 4.00003)),
        ],
        True,
    )
    deduplicator = export_canm.ChannelDeduplicator(5)
    first_index = deduplicator.add(position_a, role="position")
    assert deduplicator.add(
        position_close,
        role="position",
    ) == first_index
    assert deduplicator.add(
        position_far,
        role="position",
    ) != first_index
    assert deduplicator.add(
        position_close,
        role="scale",
    ) != first_index

    rotation_a = export_canm.vector_to_channel(
        [mathutils.Vector((0.0, 0.0, 0.0))],
        False,
    )
    rotation_equivalent = export_canm.vector_to_channel(
        [mathutils.Vector((2.0 * math.pi, 0.0, 0.0))],
        False,
    )
    rotation_deduplicator = export_canm.ChannelDeduplicator(5)
    rotation_index = rotation_deduplicator.add(
        rotation_a,
        role="rotation",
    )
    assert rotation_deduplicator.add(
        rotation_equivalent,
        role="rotation",
    ) == rotation_index

    quaternion_a = export_canm.quaternion_to_channel(
        [mathutils.Quaternion((1.0, 0.0, 0.0, 0.0))],
        False,
    )
    quaternion_negated = export_canm.quaternion_to_channel(
        [mathutils.Quaternion((-1.0, 0.0, 0.0, 0.0))],
        False,
    )
    quaternion_deduplicator = export_canm.ChannelDeduplicator(6)
    quaternion_index = quaternion_deduplicator.add(
        quaternion_a,
        role="rotation",
    )
    assert quaternion_deduplicator.add(
        quaternion_negated,
        role="rotation",
    ) == quaternion_index


def main():
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)

    from _canm6_smoke import action_compat, export_canm, import_canm

    assert export_canm.calculate_frame_interval(12.0, 1) == 12.0
    assert export_canm.calculate_frame_interval(12.0, 4) == 4.0
    assert export_canm.encode_channel_index(-1) == 0xFFFF
    assert export_canm.encode_channel_index(0x8000) == 0x8000
    assert export_canm.encode_channel_index(0xFFFE) == 0xFFFE
    for invalid_index in (-2, 0xFFFF):
        try:
            export_canm.encode_channel_index(invalid_index)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Invalid channel index {invalid_index} was accepted"
            )
    export_canm.validate_channel_count([None] * 0xFFFF)
    try:
        export_canm.validate_channel_count([None] * 0x10000)
    except ValueError:
        pass
    else:
        raise AssertionError("65,536 CANM channels were accepted")
    animation_bytes = io.BytesIO()
    export_canm.write_animations(animation_bytes, [{
        "loop": False,
        "duration": 4.0,
        "between_keyframes": 4.0,
        "keyframes": 2,
        "bone_data": [{
            "index": 7,
            "channel_index_pos": 0x8000,
            "channel_index_rot": 0xFFFE,
            "channel_index_scale": -1,
        }],
    }])
    assert unpack(
        "<hHHH",
        animation_bytes.getvalue()[0x1C:0x24],
    ) == (7, 0x8000, 0xFFFE, 0xFFFF)

    scale = import_canm.scale_matrix(2.0, 3.0, 4.0)
    assert scale == mathutils.Matrix.Diagonal((2.0, 3.0, 4.0, 1.0))
    assert scale @ mathutils.Vector((1.0, 1.0, 1.0, 1.0)) == \
        mathutils.Vector((2.0, 3.0, 4.0, 1.0))
    sampled_scale = import_canm.get_bone_matrix_of_frame(
        {
            "anm_points": [{
                "base_x": 1.0,
                "base_y": 2.0,
                "base_z": 3.0,
                "speed_x": 0.5,
                "speed_y": 0.5,
                "speed_z": 0.5,
                "keyframes": [{"x": 2.0, "y": 4.0, "z": 6.0}],
            }],
        },
        {
            "point_trans_id": -1,
            "point_rot_id": -1,
            "point_scale_id": 0,
        },
        0,
    )
    assert sampled_scale["scale"]
    assert sampled_scale["matrix"] == \
        mathutils.Matrix.Diagonal((2.0, 4.0, 6.0, 1.0))
    assert_scale_action_round_trip(export_canm, import_canm)
    assert_curve_validation(export_canm, action_compat)
    assert_channel_deduplication(export_canm)
    assert_direct_curve_construction_matches_pose_insertion(
        import_canm,
        action_compat,
    )

    static_position = export_canm.vector_to_channel(
        [mathutils.Vector((1.0, 2.0, 3.0))],
        False,
    )
    static_position.update({"type": 0, "base_w": 1.0, "speed_w": 0.0})

    animated_position = export_canm.vector_to_channel(
        [
            mathutils.Vector((0.0, 0.0, 0.0)),
            mathutils.Vector((1.0, 2.0, 3.0)),
        ],
        True,
    )
    animated_position.update({"type": 1, "base_w": 1.0, "speed_w": 0.0})

    static_rotation = export_canm.quaternion_to_channel(
        [mathutils.Quaternion((1.0, 0.0, 0.0, 0.0))],
        False,
    )
    animated_rotation = export_canm.quaternion_to_channel(
        [
            mathutils.Quaternion((1.0, 0.0, 0.0, 0.0)),
            mathutils.Quaternion((0.9238795, 0.0, 0.3826834, 0.0)),
        ],
        True,
    )

    channels = (
        static_position,
        animated_position,
        static_rotation,
        animated_rotation,
    )
    encoded = io.BytesIO()
    export_canm.write_channels6(encoded, channels)

    parsed = import_canm.parse_anm_point6(encoded, len(channels), 0)
    assert [channel["type"] for channel in parsed] == [0, 1, 2, 3]
    assert len(parsed[1]["keyframes"]) == 2
    assert len(parsed[3]["keyframes"]) == 2

    quaternion_record = 3 * 0x30
    encoded.seek(quaternion_record + 0x20)
    quaternion_offset = unpack("<I", encoded.read(4))[0]
    assert (quaternion_record + quaternion_offset) % 16 == 0

    expected = animated_rotation["frames"][1]
    actual = parsed[3]["keyframes"][1]
    assert all(
        math.isclose(actual[axis], expected[index], abs_tol=1e-7)
        for index, axis in enumerate("xyzw")
    )

    print("EDF6 CANM channel round trip and quaternion alignment passed.")


if __name__ == "__main__":
    main()
