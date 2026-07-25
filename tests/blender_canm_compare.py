"""Compare two CANM files in decoded local-transform space."""

import importlib.util
import math
import sys
from pathlib import Path


def load_addon(addon_root):
    package_name = "_canm_compare"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)


def parse(import_canm, path):
    import_canm.override_version = 0
    with path.open("rb") as stream:
        return import_canm.parse_canm(stream)


def quaternion_angle(first, second):
    first_values = tuple(float(value) for value in first)
    second_values = tuple(float(value) for value in second)
    dot = sum(
        first_value * second_value
        for first_value, second_value in zip(first_values, second_values)
    )
    length_product = math.sqrt(
        sum(value * value for value in first_values)
        * sum(value * value for value in second_values)
    )
    cosine = min(1.0, abs(dot) / length_product)
    return 2.0 * math.acos(cosine)


def main():
    separator = sys.argv.index("--")
    source_path = Path(sys.argv[separator + 1]).resolve()
    compared_path = Path(sys.argv[separator + 2]).resolve()
    excluded_bones = set(sys.argv[separator + 3:])
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)
    from _canm_compare import import_canm

    source = parse(import_canm, source_path)
    compared = parse(import_canm, compared_path)
    source_animations = {
        animation["name"]: animation
        for animation in source["animations"]
    }
    compared_animations = {
        animation["name"]: animation
        for animation in compared["animations"]
    }
    if source_animations.keys() != compared_animations.keys():
        raise AssertionError("Animation-name sets differ")

    count = 0
    position_squared_sum = 0.0
    scale_squared_sum = 0.0
    rotation_squared_sum = 0.0
    maxima = {
        "position": (0.0, ""),
        "scale": (0.0, ""),
        "rotation": (0.0, ""),
    }
    for animation_name, source_animation in source_animations.items():
        compared_animation = compared_animations[animation_name]
        if source_animation["keyframes"] != compared_animation["keyframes"]:
            raise AssertionError(
                f"Sample-count mismatch for {animation_name!r}"
            )
        source_bones = {
            source["bone_names"][bone["bone_id"]]: bone
            for bone in source_animation["bone_data"]
        }
        compared_bones = {
            compared["bone_names"][bone["bone_id"]]: bone
            for bone in compared_animation["bone_data"]
        }
        for bone_name, source_bone in source_bones.items():
            if bone_name in excluded_bones:
                continue
            compared_bone = compared_bones[bone_name]
            for sample_index in range(source_animation["keyframes"]):
                source_matrix = import_canm.get_bone_matrix_of_frame(
                    source,
                    source_bone,
                    sample_index,
                )["matrix"]
                compared_matrix = import_canm.get_bone_matrix_of_frame(
                    compared,
                    compared_bone,
                    sample_index,
                )["matrix"]
                source_position, source_rotation, source_scale = \
                    source_matrix.decompose()
                compared_position, compared_rotation, compared_scale = \
                    compared_matrix.decompose()
                position_error = (
                    source_position - compared_position
                ).length
                scale_error = max(
                    abs(source_scale[index] - compared_scale[index])
                    for index in range(3)
                )
                rotation_error = math.degrees(
                    quaternion_angle(source_rotation, compared_rotation)
                )
                label = (
                    f"{animation_name}/{bone_name}/"
                    f"sample {sample_index + 1}"
                )
                for kind, error in (
                    ("position", position_error),
                    ("scale", scale_error),
                    ("rotation", rotation_error),
                ):
                    if error > maxima[kind][0]:
                        maxima[kind] = (error, label)
                position_squared_sum += position_error * position_error
                scale_squared_sum += scale_error * scale_error
                rotation_squared_sum += rotation_error * rotation_error
                count += 1

    print(
        "CANM transform comparison: "
        f"samples={count}, "
        f"position_rms={math.sqrt(position_squared_sum / count):.9g}, "
        f"position_max={maxima['position'][0]:.9g} "
        f"({maxima['position'][1]}), "
        f"scale_rms={math.sqrt(scale_squared_sum / count):.9g}, "
        f"scale_max={maxima['scale'][0]:.9g} "
        f"({maxima['scale'][1]}), "
        f"rotation_rms_degrees="
        f"{math.sqrt(rotation_squared_sum / count):.9g}, "
        f"rotation_max_degrees={maxima['rotation'][0]:.9g} "
        f"({maxima['rotation'][1]})"
    )


if __name__ == "__main__":
    main()
