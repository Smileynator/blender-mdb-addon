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


def assert_curve_validation(export_canm):
    armature_obj = bpy.data.objects["CANM scale test"]
    pose_bone = armature_obj.pose.bones["scale_bone"]

    partial_action = bpy.data.actions.new("partial_location")
    partial_action["duration"] = 4.0
    partial_action["loop"] = False
    partial_action["keyframes"] = 2
    partial_action.fcurves.new(
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
    scale_curves = []
    for index in range(3):
        curve = complete_action.fcurves.new(
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
    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / "invalid.CANM"
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


def main():
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)

    from _canm6_smoke import export_canm, import_canm

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
    assert_curve_validation(export_canm)

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
