"""Headless Blender checks for isolation between multiple imported MDB files."""

import importlib.util
import sys
from pathlib import Path

import bpy


def load_addon(addon_root):
    package_name = "_mdb_source_isolation"
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


def import_model(import_mdb, path):
    result = import_mdb.load(
        ImportOptions(),
        bpy.context,
        filepath=str(path),
    )
    assert result == {"FINISHED"}
    armature_object = bpy.context.active_object
    return armature_object, armature_object["mdb_source_id"]


def main():
    separator = sys.argv.index("--")
    first_path = Path(sys.argv[separator + 1]).resolve()
    second_path = Path(sys.argv[separator + 2]).resolve()
    addon_root = Path(__file__).resolve().parents[1]

    load_addon(addon_root)
    from _mdb_source_isolation import export_mdb, import_mdb

    first_armature, first_source = import_model(import_mdb, first_path)
    second_armature, second_source = import_model(import_mdb, second_path)
    assert first_source != second_source

    bpy.context.view_layer.objects.active = first_armature
    selected_source, error = export_mdb.get_export_source_id(bpy.context)
    assert error is None
    assert selected_source == first_source

    first_materials = export_mdb.get_materials(
        export_mdb.get_unique_names(first_source, first_armature.data),
        first_source,
    )
    assert first_materials
    assert all(
        material["blender_material"]["mdb_source_id"] == first_source
        for material in first_materials
    )
    assert all(
        material["blender_material"]["mdb_source_id"] != second_source
        for material in first_materials
    )

    first_mesh_object = next(export_mdb.iter_exported_mesh_objects(first_source))
    foreign_material = next(
        material for material in bpy.data.materials
        if material.get("mdb_source_id") == second_source
    )
    first_mesh_object.data.materials.append(foreign_material)
    missing = export_mdb.find_incomplete_mdb_metadata(
        first_source,
        first_armature.data,
    )
    assert any("different MDB import" in problem for problem in missing)
    first_mesh_object.data.materials.pop(
        index=len(first_mesh_object.data.materials) - 1,
    )

    first_container = next(export_mdb.iter_mdb_containers(first_source))
    replacement_mesh = bpy.data.meshes.new("ReplacementMeshData")
    replacement_object = bpy.data.objects.new("ReplacementMesh", replacement_mesh)
    bpy.context.scene.collection.objects.link(replacement_object)
    replacement_object.parent = first_container
    assert export_mdb.source_id_of(replacement_object) == first_source
    bpy.data.objects.remove(replacement_object, do_unlink=True)
    bpy.data.meshes.remove(replacement_mesh)

    duplicated_material = first_materials[0]["blender_material"].copy()
    assert duplicated_material["mdb_source_id"] == first_source
    bpy.data.materials.remove(duplicated_material)

    bpy.context.view_layer.objects.active = second_armature
    selected_source, error = export_mdb.get_export_source_id(bpy.context)
    assert error is None
    assert selected_source == second_source

    print(
        "Multiple MDB imports remained isolated; replacement meshes inherit "
        "their container source and duplicated materials retain metadata."
    )


if __name__ == "__main__":
    main()
