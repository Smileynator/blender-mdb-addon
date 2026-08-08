"""Exercise the Dope Sheet helper for CANM Action metadata."""

import importlib.util
import sys
from pathlib import Path

import bpy


def load_addon(addon_root):
    package_name = "_canm_action_properties"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    package.register()
    return package


def main():
    addon_root = Path(__file__).resolve().parents[1]
    package = load_addon(addon_root)

    try:
        armature = bpy.data.armatures.new("CANM metadata test")
        armature_obj = bpy.data.objects.new("CANM metadata test", armature)
        bpy.context.collection.objects.link(armature_obj)
        bpy.context.view_layer.objects.active = armature_obj
        armature_obj.select_set(True)
        armature_obj.animation_data_create()

        action = bpy.data.actions.new("new user action")
        action["loop"] = True
        armature_obj.animation_data.action = action

        curve = action.fcurves.new("location", index=0)
        curve.keyframe_points.insert(1.0, 0.0)
        curve.keyframe_points.insert(12.0, 1.0)

        result = bpy.ops.edf.add_canm_action_properties()
        assert result == {"FINISHED"}
        assert action["duration"] == 12.0
        assert action["loop"] is True
        assert action["keyframes"] == 12

        action["duration"] = 30.0
        action["keyframes"] = 3
        result = bpy.ops.edf.add_canm_action_properties()
        assert result == {"FINISHED"}
        assert action["duration"] == 30.0
        assert action["loop"] is True
        assert action["keyframes"] == 3
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
