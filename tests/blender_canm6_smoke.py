"""Exercise EDF6 CANM channel encoding and decoding in Blender."""

import importlib.util
import io
import math
import sys
from pathlib import Path
from struct import unpack

import mathutils


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


def main():
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)

    from _canm6_smoke import export_canm, import_canm

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
