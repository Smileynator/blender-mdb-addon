bl_info = {
    "name": "MDB format",
    "author": "BlueAmulet",
    "version": (1, 0, 10),
    "blender": (2, 90, 0),
    "location": "File > Import-Export",
    "description": "Import-Export MDB, mesh, UV's, materials and textures",
    "warning": "",
    #"doc_url": "",
    "support": 'COMMUNITY',
    "category": "Import-Export",
}


if "bpy" in locals():
    import importlib
    if "import_mdb" in locals():
        importlib.reload(import_mdb)
    if "export_mdb" in locals():
        importlib.reload(export_mdb)


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


def menu_func_import(self, context):
    self.layout.operator(ImportMDB.bl_idname, text="Earth Defense Force (.mdb)")


def menu_func_export(self, context):
    self.layout.operator(ExportMDB.bl_idname, text="Earth Defense Force (.mdb)")


classes = (
    ImportMDB,
    ExportMDB,
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
