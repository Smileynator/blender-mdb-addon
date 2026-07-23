"""Headless Blender smoke test for importing and exporting one MDB file."""

import importlib.util
import json
import math
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
    export_version = int(sys.argv[separator + 3]) if len(sys.argv) > separator + 3 else 5
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
                input_x = shader_node.inputs.get(name + "_x")
                input_y = shader_node.inputs.get(name + "_y")
                assert input_x is not None
                assert input_y is not None
                assert math.isclose(input_x.default_value, parameter["val0"])
                assert math.isclose(input_y.default_value, parameter["val1"])
            else:
                material_input = shader_node.inputs.get(name)
                assert material_input is not None
                if parameter["size"] == 1:
                    assert math.isclose(material_input.default_value, parameter["val0"])
                elif parameter["size"] >= 3:
                    for component in range(3):
                        assert math.isclose(
                            material_input.default_value[component],
                            parameter[f"val{component}"],
                        )
            if parameter["type"] == 3:
                alpha_input = shader_node.inputs.get(name + "_alpha")
                assert alpha_input is not None
                assert math.isclose(alpha_input.default_value, parameter["val3"])

        parameter_names = {parameter["name"] for parameter in parameters}
        texture_nodes = [
            node for node in material.node_tree.nodes
            if node.type == "TEX_IMAGE" and "mdb_texture_binding" in node
        ]
        assert len(texture_nodes) == len({
            node["mdb_texture_binding"] for node in texture_nodes
        })
        texture_slots = {node["mdb_texture_slot"] for node in texture_nodes}

        preview = shader_node.node_tree
        bsdf = next(node for node in preview.nodes if node.type == "BSDF_PRINCIPLED")
        if {"diffuse", "albedo"} & (parameter_names | texture_slots):
            assert bsdf.inputs["Base Color"].is_linked
        if {"normal", "damage_normal"} & texture_slots:
            assert bsdf.inputs["Normal"].is_linked
        if (
            material["render_layer"] == 2
            and "albedo" in texture_slots
        ):
            assert bsdf.inputs["Alpha"].is_linked

        editing_notes = [
            node for node in material.node_tree.nodes
            if node.type == "FRAME" and node.name == "MDB Editing Notes"
        ]
        assert len(editing_notes) == 1
        assert editing_notes[0].text is not None

    export_mdb.save(
        object(),
        bpy.context,
        filepath=str(output_path),
        version=export_version,
    )
    assert output_path.exists()


if __name__ == "__main__":
    main()
