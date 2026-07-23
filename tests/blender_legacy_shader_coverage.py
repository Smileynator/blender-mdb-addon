"""Use the retired recipe table as a coverage oracle for the generic builder."""

import importlib.util
import sys
from pathlib import Path


def load_addon(addon_root):
    package_name = "_mdb_legacy_coverage"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


def material_from_recipe(shader_name, recipe):
    type_info = {
        "float": (0, 1),
        "int": (0, 1),
        "float2": (1, 2),
        "float3": (2, 4),
        "float4": (3, 4),
    }
    parameters = []
    textures = []
    for name, field_type, *_ in recipe:
        if field_type in type_info:
            parameter_type, size = type_info[field_type]
            parameters.append({
                "name": name,
                "type": parameter_type,
                "size": size,
            })
        else:
            textures.append({"map": name})

    return {
        "shader": shader_name,
        "params": parameters,
        "textures": textures,
        "render_layer": 2 if shader_name.lower().endswith(("_alpha", "_clip", "_hair")) else 0,
    }


def main():
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)

    from _mdb_legacy_coverage.shader import get_shader, infer_uv_channel
    from _mdb_legacy_coverage.shader_data import shaders as legacy_recipes

    schema_count = 0
    uv_count = 0
    for shader_name, recipe in legacy_recipes.items():
        material = material_from_recipe(shader_name, recipe)
        shader = get_shader(shader_name, False, material)
        assert shader.shader_tree is not None
        for entry in recipe:
            if entry[1] in ("texture", "texture_alpha", "normal") and len(entry) > 2:
                assert infer_uv_channel(shader_name, entry[0]) == entry[2]
                uv_count += 1
        schema_count += 1

    print(
        f"Generic builder covered all {schema_count} retired shader recipes "
        f"and preserved {uv_count} known non-default UV selections."
    )


if __name__ == "__main__":
    main()
