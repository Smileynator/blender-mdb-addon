bl_info = {
    "name": "Earth Defense Force Formats",
    "author": "Smileynator / BlueAmulet / Ktaro",
    "version": (1, 9, 3),
    "blender": (3, 6, 0),
    "location": "File > Import-Export",
    "description": "Import-Export MDB, CANM, mesh, UV's, materials, textures, Animations from Earth Defense Force",
    "warning": "",
    "support": 'COMMUNITY',
    "category": "Import-Export",
}


if "bpy" in locals():
    import importlib
    if "import_mdb" in locals():
        importlib.reload(import_mdb)
    if "export_mdb" in locals():
        importlib.reload(export_mdb)
    if "import_canm" in locals():
        importlib.reload(import_canm)
    if "export_canm" in locals():
        importlib.reload(export_canm)
    if "additive_editing" in locals():
        importlib.reload(additive_editing)


import bpy
from . import additive_editing
from bpy.props import (
        StringProperty,
        IntProperty,
        BoolProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        )


class ImportMDB(bpy.types.Operator, ImportHelper):
    """Load a MDB file"""
    bl_idname = "import_scene.mdb"
    bl_label = "Import MDB"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".mdb"
    filter_glob: StringProperty(default="*.mdb", options={'HIDDEN'})

    option_override_version: IntProperty(
        name="Override Version Int",
        description="Ignores the file version Int, instead uses this if non 0. 20 == EDF5, 32 == EDF6",
        default=0,
    )

    option_ignore_errors: BoolProperty(
        name="Ignore Errors",
        description="Catch and ignore any known errors, instead of stopping import. Will break exports!",
        default=False,
    )


    def execute(self, context):
        from . import import_mdb
        keywords = self.as_keywords(ignore=())
        return import_mdb.load(self, context, **keywords)

    def draw(self, context):
        layout = self.layout
        if bpy.app.version >= (5, 2, 0):
            if hasattr(self, "option_override_version"):
                layout.prop(self, "option_override_version")
            if hasattr(self, "option_ignore_errors"):
                layout.prop(self, "option_ignore_errors")
        else:
            layout.prop(self, "option_override_version")
            layout.prop(self, "option_ignore_errors")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class ExportMDB_5(bpy.types.Operator, ExportHelper):
    """Write a MDB file"""
    bl_idname = "export_scene_edf5.mdb"
    bl_label = "Export MDB EDF5"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".mdb"
    filter_glob: StringProperty(default="*.mdb", options={'HIDDEN'})

    check_extension = True

    def execute(self, context):
        from . import export_mdb

        keywords = self.as_keywords(ignore=())
        keywords['version'] = 5  # Set the version to 5

        return export_mdb.save(self, context, **keywords)

    def draw(self, context):
        pass

    @classmethod
    def poll(cls, context):
        # Ensure user has left Edit mode, so the meshes we export are up to date.
        return (context.active_object is not None) and (not context.active_object.mode == 'EDIT')

class ExportMDB_6(bpy.types.Operator, ExportHelper):
    """Write a MDB file"""
    bl_idname = "export_scene_edf6.mdb"
    bl_label = "Export MDB EDF6"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".mdb"
    filter_glob: StringProperty(default="*.mdb", options={'HIDDEN'})

    check_extension = True

    def execute(self, context):
        from . import export_mdb

        keywords = self.as_keywords(ignore=())
        keywords['version'] = 6  # Set the version to 6

        return export_mdb.save(self, context, **keywords)

    def draw(self, context):
        pass

    @classmethod
    def poll(cls, context):
        # Ensure user has left Edit mode, so the meshes we export are up to date.
        return (context.active_object is not None) and (not context.active_object.mode == 'EDIT')


class ImportCANM(bpy.types.Operator, ImportHelper):
    """Load a CANM file"""
    bl_idname = "import_scene.canm"
    bl_label = "Import CANM"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".canm"
    filter_glob: StringProperty(default="*.canm", options={'HIDDEN'})

    option_override_version: IntProperty(
        name="Override Version Int",
        description="Ignores the file version Int, instead uses this if non 0. 512 == EDF5, 768 == EDF6",
        default=0,
    )

    option_ignore_errors: BoolProperty(
        name="Ignore Errors",
        description="Catch and ignore any known errors, instead of stopping import. Will break exports!",
        default=False,
    )

    def execute(self, context):
        from . import import_canm
        keywords = self.as_keywords(ignore=())
        return import_canm.load(self, context, **keywords)

    def draw(self, context):
        layout = self.layout
        if bpy.app.version >= (5, 2, 0):
            if hasattr(self, "option_override_version"):
                layout.prop(self, "option_override_version")
            if hasattr(self, "option_ignore_errors"):
                layout.prop(self, "option_ignore_errors")
        else:
            layout.prop(self, "option_override_version")
            layout.prop(self, "option_ignore_errors")
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class ExportCANM_5(bpy.types.Operator, ExportHelper):
    """Write a CANM file"""
    bl_idname = "export_scene_edf5.canm"
    bl_label = "Export CANM EDF5"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".CANM"
    filter_glob: StringProperty(default="*.canm", options={'HIDDEN'})

    check_extension = True

    def execute(self, context):
        from . import export_canm

        keywords = self.as_keywords(ignore=())
        keywords['version'] = 5

        return export_canm.save(self, context, **keywords)

    def draw(self, context):
        pass

    @classmethod
    def poll(cls, context):
        # Ensure user has left Edit mode, so the meshes we export are up to date.
        return (context.active_object is not None) and (not context.active_object.mode == 'EDIT')


class ExportCANM_6(bpy.types.Operator, ExportHelper):
    """Write an EDF6 CANM file"""
    bl_idname = "export_scene_edf6.canm"
    bl_label = "Export CANM EDF6"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".CANM"
    filter_glob: StringProperty(default="*.canm", options={'HIDDEN'})

    check_extension = True

    def execute(self, context):
        from . import export_canm

        keywords = self.as_keywords(ignore=())
        keywords['version'] = 6
        return export_canm.save(self, context, **keywords)

    def draw(self, context):
        pass

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.mode != 'EDIT'
        )


def get_context_action(context):
    action = getattr(context, "active_action", None)
    if action is not None:
        return action
    obj = context.active_object
    if obj is None or obj.animation_data is None:
        return None
    return obj.animation_data.action


def infer_canm_timing(context, action):
    frame_start, frame_end = action.frame_range
    if frame_end > frame_start:
        sample_count = int(round(frame_end - frame_start)) + 1
    else:
        sample_count = int(context.scene.frame_end - context.scene.frame_start) + 1
    sample_count = max(2, sample_count)
    return float(sample_count), sample_count


class EDF_OT_add_canm_action_properties(bpy.types.Operator):
    """Add the CANM custom properties required for exporting this Action"""

    bl_idname = "edf.add_canm_action_properties"
    bl_label = "Add CANM Properties"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_context_action(context) is not None

    def execute(self, context):
        action = get_context_action(context)
        if action is None:
            self.report({'ERROR'}, "No active Action found")
            return {'CANCELLED'}

        duration, keyframes = infer_canm_timing(context, action)
        added = []
        if "duration" not in action:
            action["duration"] = duration
            added.append("duration")
        if "loop" not in action:
            action["loop"] = False
            added.append("loop")
        if "keyframes" not in action:
            action["keyframes"] = keyframes
            added.append("keyframes")

        if added:
            self.report(
                {'INFO'},
                f"Added CANM properties to {action.name!r}: {', '.join(added)}",
            )
        else:
            self.report(
                {'INFO'},
                f"Action {action.name!r} already has CANM properties",
            )
        return {'FINISHED'}


class EDF_PT_canm_action_properties(bpy.types.Panel):
    bl_label = "EDF CANM"
    bl_idname = "EDF_PT_canm_action_properties"
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "UI"
    bl_category = "EDF"

    def draw(self, context):
        layout = self.layout
        action = get_context_action(context)
        if action is None:
            layout.label(text="No active Action.", icon="INFO")
            return

        missing = [
            name for name in ("duration", "loop", "keyframes")
            if name not in action
        ]
        row = layout.row()
        row.operator(
            EDF_OT_add_canm_action_properties.bl_idname,
            icon="ADD",
        )
        if missing:
            layout.label(text=f"Missing: {', '.join(missing)}", icon="ERROR")
        else:
            layout.label(text="CANM properties present.", icon="CHECKMARK")


def menu_func_import(self, context):
    self.layout.operator(ImportMDB.bl_idname, text="Earth Defense Force Model (.mdb)")
    self.layout.operator(ImportCANM.bl_idname, text="Earth Defense Force Animations (.canm)")


def menu_func_export(self, context):
    self.layout.operator(ExportMDB_5.bl_idname, text="Earth Defense Force 5 Model (.mdb)")
    self.layout.operator(ExportMDB_6.bl_idname, text="Earth Defense Force 6 Model (.mdb)")
    self.layout.operator(ExportCANM_5.bl_idname, text="Earth Defense Force 5 Animation (.canm)")
    self.layout.operator(ExportCANM_6.bl_idname, text="Earth Defense Force 6 Animation (.canm)")


classes = (
    ImportMDB,
    ExportMDB_5,
    ExportMDB_6,
    ImportCANM,
    ExportCANM_5,
    ExportCANM_6,
    EDF_OT_add_canm_action_properties,
    EDF_PT_canm_action_properties,
    *additive_editing.CLASSES,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
