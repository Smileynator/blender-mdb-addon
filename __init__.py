bl_info = {
    "name": "Earth Defense Force Formats",
    "author": "Smileynator / BlueAmulet",
    "version": (1, 6, 1),
    "blender": (2, 90, 0),
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


import bpy
from bpy.props import (
        StringProperty,
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

    def execute(self, context):
        from . import import_mdb

        keywords = self.as_keywords(ignore=())

        return import_mdb.load(self, context, **keywords)

    def draw(self, context):
        pass


class ExportMDB(bpy.types.Operator, ExportHelper):
    """Write a MDB file"""
    bl_idname = "export_scene.mdb"
    bl_label = "Export MDB"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".mdb"
    filter_glob: StringProperty(default="*.mdb", options={'HIDDEN'})

    check_extension = True

    def execute(self, context):
        from . import export_mdb

        keywords = self.as_keywords(ignore=())

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

    def execute(self, context):
        from . import import_canm

        keywords = self.as_keywords(ignore=())

        return import_canm.load(self, context, **keywords)

    def draw(self, context):
        pass


class ExportCANM(bpy.types.Operator, ExportHelper):
    """Write a CANM file"""
    bl_idname = "export_scene.canm"
    bl_label = "Export CANM"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".CANM"
    filter_glob: StringProperty(default="*.canm", options={'HIDDEN'})

    check_extension = True

    def execute(self, context):
        from . import export_canm

        keywords = self.as_keywords(ignore=())

        return export_canm.save(self, context, **keywords)

    def draw(self, context):
        pass

    @classmethod
    def poll(cls, context):
        # Ensure user has left Edit mode, so the meshes we export are up to date.
        return (context.active_object is not None) and (not context.active_object.mode == 'EDIT')


def menu_func_import(self, context):
    self.layout.operator(ImportMDB.bl_idname, text="Earth Defense Force Model (.mdb)")
    self.layout.operator(ImportCANM.bl_idname, text="Earth Defense Force Animations (.canm)")


def menu_func_export(self, context):
    self.layout.operator(ExportMDB.bl_idname, text="Earth Defense Force Model (.mdb)")
    self.layout.operator(ExportCANM.bl_idname, text="Earth Defense Force Animation (.canm)")


classes = (
    ImportMDB,
    ExportMDB,
    ImportCANM,
    ExportCANM,
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
