"""Build generic preview graphs for every MDB below the supplied directories."""

import importlib.util
import sys
from pathlib import Path


def load_addon(addon_root):
    package_name = "_mdb_shader_coverage"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


def parse_materials(import_mdb, source):
    source.seek(8)
    name_count = import_mdb.read_uint(source)
    name_offset = import_mdb.read_uint(source)
    source.seek(0x20)
    material_count = import_mdb.read_uint(source)
    material_offset = import_mdb.read_uint(source)
    names = import_mdb.parse_names(source, name_count, name_offset)
    return import_mdb.parse_materials(source, material_count, material_offset, names)


def assert_schema(shader, material):
    for parameter in material["params"]:
        name = parameter["name"]
        if parameter["size"] == 2:
            assert shader.input(name + "_x") is not None
            assert shader.input(name + "_y") is not None
        else:
            assert shader.input(name) is not None
        if parameter["type"] == 3:
            assert shader.input(name + "_alpha") is not None

    for texture in material["textures"]:
        name = texture["map"]
        assert shader.input(name) is not None
        assert shader.input(name + "_alpha") is not None
        assert name in shader.param_map

    bsdf = next(node for node in shader.shader_tree.nodes if node.type == "BSDF_PRINCIPLED")
    available = (
        {parameter["name"] for parameter in material["params"]}
        | {texture["map"] for texture in material["textures"]}
    )
    if {"diffuse", "albedo"} & available:
        assert bsdf.inputs["Base Color"].is_linked
    if {"normal", "damage_normal"} & available:
        assert bsdf.inputs["Normal"].is_linked


def main():
    separator = sys.argv.index("--")
    roots = [Path(argument).resolve() for argument in sys.argv[separator + 1:]]
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)

    from _mdb_shader_coverage import import_mdb
    from _mdb_shader_coverage.shader import get_shader

    files = sorted(
        file
        for root in roots
        for file in root.rglob("*.mdb")
    )
    material_count = 0
    schemas = set()
    for file in files:
        with file.open("rb") as source:
            materials = parse_materials(import_mdb, source)
        for material in materials:
            shader = get_shader(material["shader"], False, material)
            assert_schema(shader, material)
            schemas.add(shader.shader_tree.name)
            material_count += 1

    print(
        f"Built {len(schemas)} generic shader schemas for "
        f"{material_count} materials across {len(files)} MDB files."
    )


if __name__ == "__main__":
    main()
