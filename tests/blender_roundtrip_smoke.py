"""Headless Blender smoke test for importing and exporting one MDB file."""

import importlib.util
import json
import sys
from pathlib import Path

import bpy


def load_addon(addon_root):
    package_name = "_mdb_blender_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    return package


class ImportOptions:
    option_ignore_errors = False
    option_override_version = 0


def main():
    separator = sys.argv.index("--")
    input_path = Path(sys.argv[separator + 1]).resolve()
    output_path = Path(sys.argv[separator + 2]).resolve()
    addon_root = Path(__file__).resolve().parents[1]

    load_addon(addon_root)
    from _mdb_blender_smoke import export_mdb, import_mdb

    import_mdb.load(ImportOptions(), bpy.context, filepath=str(input_path))

    imported_materials = [
        material for material in bpy.data.materials
        if material.get("mdb_shader_name")
    ]
    assert imported_materials, "No tagged MDB materials were imported"
    for material in imported_materials:
        shader_nodes = [
            node for node in material.node_tree.nodes
            if node.type == "GROUP" and node.get("mdb_shader_name")
        ]
        assert len(shader_nodes) == 1
        shader_node = shader_nodes[0]
        parameters = json.loads(shader_node["mdb_parameters"])
        for parameter in parameters:
            name = parameter["name"]
            if parameter["size"] == 2:
                assert shader_node.inputs.get(name + "_x") is not None
                assert shader_node.inputs.get(name + "_y") is not None
            else:
                assert shader_node.inputs.get(name) is not None
            if parameter["type"] == 3:
                assert shader_node.inputs.get(name + "_alpha") is not None

        texture_nodes = [
            node for node in material.node_tree.nodes
            if node.type == "TEX_IMAGE" and "mdb_texture_binding" in node
        ]
        assert len(texture_nodes) == len({
            node["mdb_texture_binding"] for node in texture_nodes
        })

    export_mdb.save(
        object(),
        bpy.context,
        filepath=str(output_path),
        version=5,
    )
    assert output_path.exists()


if __name__ == "__main__":
    main()
