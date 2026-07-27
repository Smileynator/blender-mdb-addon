"""Measure CANM parsing and Blender Action construction separately."""

import importlib
import importlib.util
import sys
import time
from pathlib import Path

import bpy


class Operator:
    option_ignore_errors = False
    option_override_version = 0

    def report(self, levels, message):
        print(f"{','.join(sorted(levels))}: {message}")


def load_addon(addon_root):
    package_name = "_canm_import_benchmark"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    return package


def main():
    separator = sys.argv.index("--")
    mdb_path = Path(sys.argv[separator + 1]).resolve()
    canm_path = Path(sys.argv[separator + 2]).resolve()
    addon_root = Path(__file__).resolve().parents[1]
    package = load_addon(addon_root)
    import_mdb = importlib.import_module(f"{package.__name__}.import_mdb")
    import_canm = importlib.import_module(f"{package.__name__}.import_canm")
    operator = Operator()

    started = time.perf_counter()
    assert import_mdb.load(
        operator,
        bpy.context,
        filepath=str(mdb_path),
    ) == {"FINISHED"}
    mdb_imported = time.perf_counter()
    import_canm.override_version = 0
    with canm_path.open("rb") as stream:
        canm = import_canm.parse_canm(stream)
    parsed = time.perf_counter()

    armature_obj = next(
        obj for obj in bpy.data.objects if obj.type == "ARMATURE"
    )
    bone_index_by_name = {
        name: index for index, name in enumerate(canm["bone_names"])
    }
    mapped_pose_bones = [
        (bone_index_by_name[pose_bone.name], pose_bone)
        for pose_bone in armature_obj.pose.bones
        if pose_bone.name in bone_index_by_name
    ]
    for animation in canm["animations"]:
        import_canm.create_action_with_animation(
            armature_obj,
            animation,
            canm,
            mapped_pose_bones,
        )
    actions_created = time.perf_counter()
    print(
        "CANM import benchmark: "
        f"animations={len(canm['animations'])}, "
        f"channels={len(canm['anm_points'])}, "
        f"mdb_seconds={mdb_imported - started:.3f}, "
        f"parse_seconds={parsed - mdb_imported:.3f}, "
        f"action_seconds={actions_created - parsed:.3f}"
    )


if __name__ == "__main__":
    main()
