"""Headless Blender checks for mandatory MDB export safety behavior."""

import importlib.util
import sys
from pathlib import Path

import bpy
import mathutils


def load_addon(addon_root):
    package_name = "_mdb_export_safety"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


class Operator:
    def __init__(self):
        self.messages = []

    def report(self, levels, message):
        self.messages.append((levels, message))


def create_mesh(name, vertices, faces):
    mesh = bpy.data.meshes.new(name + "Data")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    separator = sys.argv.index("--")
    output_path = Path(sys.argv[separator + 1]).resolve()
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)

    from _mdb_export_safety import export_mdb

    container = bpy.data.objects.new("Container", None)
    container["mdb_source_id"] = "export-safety"
    bpy.context.scene.collection.objects.link(container)
    quad = create_mesh(
        "Quad",
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
        ((0, 1, 2, 3),),
    )
    quad.parent = container

    operator = Operator()
    result = export_mdb.save(
        operator,
        bpy.context,
        filepath=str(output_path),
        version=5,
    )
    assert result == {"CANCELLED"}
    assert not output_path.exists()
    assert any("triangulated" in message for _, message in operator.messages)

    bpy.data.objects.remove(quad, do_unlink=True)
    bpy.data.objects.remove(container, do_unlink=True)

    legacy_container = bpy.data.objects.new("LegacyContainer", None)
    bpy.context.scene.collection.objects.link(legacy_container)
    legacy_triangle = create_mesh(
        "LegacyTriangle",
        ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        ((0, 1, 2),),
    )
    legacy_triangle.parent = legacy_container
    operator = Operator()
    result = export_mdb.save(
        operator,
        bpy.context,
        filepath=str(output_path),
        version=5,
    )
    assert result == {"CANCELLED"}
    assert not output_path.exists()
    assert any("Re-import" in message for _, message in operator.messages)
    bpy.data.objects.remove(legacy_triangle, do_unlink=True)
    bpy.data.objects.remove(legacy_container, do_unlink=True)

    material_container = bpy.data.objects.new("MaterialContainer", None)
    material_container["mdb_source_id"] = "material-validation"
    bpy.context.scene.collection.objects.link(material_container)
    material_triangle = create_mesh(
        "MaterialTriangle",
        ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        ((0, 1, 2),),
    )
    material_triangle.parent = material_container
    issues = export_mdb.find_material_slot_issues("material-validation")
    assert any("no material assigned" in issue for issue in issues)
    material_triangle.data.materials.append(
        bpy.data.materials.new("MaterialOne"),
    )
    material_triangle.data.materials.append(
        bpy.data.materials.new("MaterialTwo"),
    )
    issues = export_mdb.find_material_slot_issues("material-validation")
    assert any("2 material slots" in issue for issue in issues)
    bpy.data.objects.remove(material_triangle, do_unlink=True)
    bpy.data.objects.remove(material_container, do_unlink=True)

    seam_mesh = create_mesh(
        "UVSeam",
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
        ((0, 1, 2), (0, 2, 3)),
    )
    uv_layer = seam_mesh.data.uv_layers.new(name="UVMap")
    coordinates = (
        (0, 0), (1, 0), (1, 1),
        (0.5, 0), (1, 1), (0, 1),
    )
    for loop, coordinate in zip(seam_mesh.data.loops, coordinates):
        uv_layer.data[loop.index].uv = coordinate
    seam_mesh.data.calc_tangents()

    vertex_loop_pairs, indices = export_mdb.split_vertices(seam_mesh.data)
    assert len(vertex_loop_pairs) == 5
    assert indices[0] != indices[3]

    for group_index, weight in enumerate((0.1, 0.2, 0.3, 0.4, 0.5)):
        group = seam_mesh.vertex_groups.new(name=f"Bone{group_index}")
        group.add((0,), weight, "REPLACE")
    layouts = {
        layout["name"]: layout
        for layout in export_mdb.get_vertex_layouts(
            seam_mesh,
            True,
            vertex_loop_pairs,
            5,
            {
                f"Bone{index}": 100 + index
                for index in range(5)
            },
        )
    }
    strongest_weights = layouts["BLENDWEIGHT"]["data"][0]
    strongest_indices = layouts["BLENDINDICES"]["data"][0]
    assert abs(sum(strongest_weights) - 1.0) < 1e-6
    assert strongest_indices == [104, 103, 102, 101]

    index_issues = export_mdb.find_index_limit_issues([{
        "name": "LargeObject",
        "mesh_data": [{
            "mesh_index": 0,
            "vertex_count": 65_537,
            "indices": [0, 1, 65_536],
        }],
    }])
    assert len(index_issues) == 1
    assert "65,536" in index_issues[0]
    assert "Split the geometry" in index_issues[0]

    bones = [{
        "index": 0,
        "name": "Bone",
        "participation_metadata": 3,
        "inv_matrix": mathutils.Matrix.Identity(4),
        "bounds_half_size": [0.0] * 4,
        "bounds_center": [0.0] * 4,
    }]
    objects = [{
        "index": 0,
        "name": "Object",
        "mesh_data": [{
            "is_skinned": 1,
            "vertex_layouts": [
                {
                    "name": "position",
                    "data": ((0, 0, 0, 1), (2, 4, 6, 1)),
                },
                {
                    "name": "BLENDINDICES",
                    "data": ((0, 0, 0, 0), (0, 0, 0, 0)),
                },
                {
                    "name": "BLENDWEIGHT",
                    "data": ((1, 0, 0, 0), (1, 0, 0, 0)),
                },
            ],
        }],
    }]
    export_mdb.recompute_bone_bounding_boxes(bones, objects)
    assert bones[0]["bounds_half_size"] == [1.0, 2.0, 3.0, 1.0]
    assert bones[0]["bounds_center"] == [1.0, 2.0, 3.0, 1.0]

    print(
        "Mandatory triangulation and metadata checks, UV seams, normalized "
        "influence limits, and bone bounds passed."
    )


if __name__ == "__main__":
    main()
