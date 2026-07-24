"""Verify that recognized triangle-strip MDBs fail safely before scene creation."""

import importlib.util
import struct
import sys
from pathlib import Path

import bpy


def load_addon(addon_root):
    package_name = "_mdb_strip_rejection"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


class ImportOptions:
    option_ignore_errors = False
    option_override_version = 0

    def __init__(self):
        self.messages = []

    def report(self, levels, message):
        self.messages.append((levels, message))


def make_triangle_strip_fixture(source_path, destination_path):
    data = bytearray(source_path.read_bytes())
    object_count, object_offset = struct.unpack_from("<II", data, 0x18)
    assert object_count > 0
    mesh_count, mesh_offset = struct.unpack_from("<II", data, object_offset + 8)
    assert mesh_count > 0
    first_mesh_offset = object_offset + mesh_offset
    data[first_mesh_offset] = 1
    destination_path.write_bytes(data)


def main():
    separator = sys.argv.index("--")
    source_path = Path(sys.argv[separator + 1]).resolve()
    fixture_path = Path(sys.argv[separator + 2]).resolve()
    addon_root = Path(__file__).resolve().parents[1]
    make_triangle_strip_fixture(source_path, fixture_path)

    load_addon(addon_root)
    from _mdb_strip_rejection import import_mdb

    object_count = len(bpy.data.objects)
    material_count = len(bpy.data.materials)
    operator = ImportOptions()
    result = import_mdb.load(
        operator,
        bpy.context,
        filepath=str(fixture_path),
    )

    assert result == {"CANCELLED"}
    assert len(bpy.data.objects) == object_count
    assert len(bpy.data.materials) == material_count
    assert any(
        "Triangle-strip MDB meshes" in message
        for _, message in operator.messages
    )
    print("Triangle-strip import was rejected before creating Blender data.")


if __name__ == "__main__":
    main()
