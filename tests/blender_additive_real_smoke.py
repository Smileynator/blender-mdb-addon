"""Import a real MDB/CANM pair and no-op an additive editing session."""

import importlib
import importlib.util
import sys
from pathlib import Path

import bpy


class Operator:
    option_ignore_errors = False
    option_override_version = 0

    def report(self, levels, message):
        print(f"{','.join(sorted(levels))}: {message}")


def load_addon(addon_root):
    package_name = "_additive_real_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    return package


def action_key_snapshot(action):
    return tuple(
        (
            curve.data_path,
            curve.array_index,
            tuple(
                (
                    tuple(point.co),
                    tuple(point.handle_left),
                    tuple(point.handle_right),
                    point.interpolation,
                )
                for point in curve.keyframe_points
            ),
        )
        for curve in sorted(
            action.fcurves,
            key=lambda item: (item.data_path, item.array_index),
        )
    )


def main():
    separator = sys.argv.index("--")
    mdb_path = Path(sys.argv[separator + 1]).resolve()
    canm_path = Path(sys.argv[separator + 2]).resolve()
    base_name = sys.argv[separator + 3]
    additive_name = sys.argv[separator + 4]
    addon_root = Path(__file__).resolve().parents[1]
    package = load_addon(addon_root)
    import_mdb = importlib.import_module(f"{package.__name__}.import_mdb")
    import_canm = importlib.import_module(f"{package.__name__}.import_canm")
    operator = Operator()
    assert import_mdb.load(
        operator,
        bpy.context,
        filepath=str(mdb_path),
    ) == {"FINISHED"}
    assert import_canm.load(
        operator,
        bpy.context,
        filepath=str(canm_path),
    ) == {"FINISHED"}

    armature_obj = next(
        obj for obj in bpy.data.objects if obj.type == "ARMATURE"
    )
    base = bpy.data.actions[base_name]
    additive = bpy.data.actions[additive_name]
    before = action_key_snapshot(additive)
    preview = package.additive_editing.build_preview_action(
        armature_obj,
        additive,
        base,
        "ACTION",
        1,
    )
    assert preview.fcurves
    package.additive_editing.save_preview_to_additive(
        armature_obj,
        preview,
        additive,
        base,
        "ACTION",
        1,
    )
    assert action_key_snapshot(additive) == before
    print(
        "Real additive smoke passed: "
        f"{additive.name} over {base.name}, "
        f"{additive['keyframes']} samples, "
        f"{len(preview.fcurves)} preview curves."
    )


if __name__ == "__main__":
    main()
