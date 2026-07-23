import io
import importlib.util
import struct
import sys
import types
import unittest
from pathlib import Path


ADDON_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ADDON_ROOT.parent


def load_addon_module(name):
    qualified_name = f"_mdb_test_addon.{name}"
    spec = importlib.util.spec_from_file_location(
        qualified_name,
        ADDON_ROOT / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


def load_material_modules():
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(version=(3, 6, 0))
    sys.modules.setdefault("bpy", bpy)

    mathutils = types.ModuleType("mathutils")
    mathutils.Matrix = lambda values=None: [
        list(row) for row in values
    ] if values is not None else [[0.0] * 4 for _ in range(4)]
    sys.modules.setdefault("mathutils", mathutils)

    numpy = types.ModuleType("numpy")
    numpy.half = object()
    sys.modules.setdefault("numpy", numpy)

    package = types.ModuleType("_mdb_test_addon")
    package.__path__ = [str(ADDON_ROOT)]
    sys.modules.setdefault("_mdb_test_addon", package)

    load_addon_module("shader")
    return load_addon_module("import_mdb"), load_addon_module("export_mdb")


IMPORT_MDB, EXPORT_MDB = load_material_modules()
IMPORT_MDB.override_version = 0


def export_material(parsed_material):
    return {
        "index": parsed_material["index"],
        "mat_name_index": 0,
        "render_priority": parsed_material["render_priority"],
        "render_layer": parsed_material["render_layer"],
        "render_type": parsed_material["render_type"],
        "shader_name": parsed_material["shader"],
        "parameters": [
            {
                "name": parameter["name"],
                "values": [parameter[f"val{index}"] for index in range(6)],
                "type": parameter["type"],
                "size": parameter["size"],
            }
            for parameter in parsed_material["params"]
        ],
        "parameter_count": len(parsed_material["params"]),
        "textures": [
            {
                "texture_index": texture["texture"],
                "type": texture["map"],
                "sampler_flags": texture["sampler_flags"],
                "filter": texture["filter"],
                "address_u": texture["address_u"],
                "address_v": texture["address_v"],
                "address_w": texture["address_w"],
                "max_anisotropy": texture["max_anisotropy"],
                "min_lod": texture["min_lod"],
                "max_lod": texture["max_lod"],
                "lod_bias": texture["lod_bias"],
            }
            for texture in parsed_material["textures"]
        ],
        "texture_count": len(parsed_material["textures"]),
    }


def float_bits(values):
    return struct.pack(f"<{len(values)}f", *values)


def parse_fixture_materials(source):
    source.seek(8)
    name_count = IMPORT_MDB.read_uint(source)
    name_offset = IMPORT_MDB.read_uint(source)
    source.seek(0x20)
    material_count = IMPORT_MDB.read_uint(source)
    material_offset = IMPORT_MDB.read_uint(source)
    names = IMPORT_MDB.parse_names(source, name_count, name_offset)
    return IMPORT_MDB.parse_materials(source, material_count, material_offset, names)


class MaterialRoundTripTests(unittest.TestCase):
    fixtures = (
        FIXTURE_ROOT / "E503_FROG" / "MODEL" / "e503_frog.mdb",
        FIXTURE_ROOT / "E505_GENERATOR" / "MODEL" / "e505_generator.mdb",
    )

    def test_fixture_material_blocks_round_trip_without_field_loss(self):
        missing = [fixture for fixture in self.fixtures if not fixture.exists()]
        if missing:
            self.skipTest(f"Optional local fixtures not found: {missing}")

        for fixture in self.fixtures:
            with self.subTest(fixture=fixture.name), fixture.open("rb") as source:
                parsed_materials = parse_fixture_materials(source)

                materials = [export_material(material) for material in parsed_materials]
                encoded = io.BytesIO()
                ascii_strings = []
                utf16_strings = []
                EXPORT_MDB.write_material_data(
                    encoded,
                    materials,
                    ascii_strings,
                    utf16_strings,
                )
                EXPORT_MDB.write_ascii_string(encoded, ascii_strings)
                EXPORT_MDB.write_utf16_strings(encoded, utf16_strings)

                encoded.seek(0)
                reparsed = IMPORT_MDB.parse_materials(
                    encoded,
                    len(materials),
                    0,
                    ["material"],
                )

                self.assert_materials_equal(parsed_materials, reparsed)

    def test_editing_a_visible_value_preserves_unrepresented_slots(self):
        parameter = {
            "name": "roughness",
            "type": 0,
            "size": 1,
            "val0": 0.25,
            "val1": 11.0,
            "val2": 12.0,
            "val3": 13.0,
            "val4": 14.0,
            "val5": 15.0,
        }
        inputs = {"roughness": types.SimpleNamespace(default_value=0.75)}

        exported = EXPORT_MDB.get_preserved_parameter(inputs, parameter)

        self.assertEqual(exported["values"], [0.75, 11.0, 12.0, 13.0, 14.0, 15.0])
        self.assertEqual(exported["type"], 0)
        self.assertEqual(exported["size"], 1)

    def test_rgba_uses_the_separate_editable_alpha_socket(self):
        parameter = {
            "name": "diffuse",
            "type": 3,
            "size": 4,
            **{f"val{index}": 0.0 for index in range(6)},
        }
        inputs = {
            "diffuse": types.SimpleNamespace(default_value=(0.1, 0.2, 0.3, 1.0)),
            "diffuse_alpha": types.SimpleNamespace(default_value=0.4),
        }

        exported = EXPORT_MDB.get_preserved_parameter(inputs, parameter)

        self.assertEqual(float_bits(exported["values"][:4]), float_bits([0.1, 0.2, 0.3, 0.4]))

    def assert_materials_equal(self, expected_materials, actual_materials):
        self.assertEqual(len(expected_materials), len(actual_materials))
        for expected, actual in zip(expected_materials, actual_materials):
            for field in ("index", "render_priority", "render_layer", "render_type", "shader"):
                self.assertEqual(expected[field], actual[field])

            self.assertEqual(len(expected["params"]), len(actual["params"]))
            for expected_param, actual_param in zip(expected["params"], actual["params"]):
                self.assertEqual(expected_param["name"], actual_param["name"])
                self.assertEqual(expected_param["type"], actual_param["type"])
                self.assertEqual(expected_param["size"], actual_param["size"])
                expected_values = [expected_param[f"val{index}"] for index in range(6)]
                actual_values = [actual_param[f"val{index}"] for index in range(6)]
                self.assertEqual(float_bits(expected_values), float_bits(actual_values))

            self.assertEqual(len(expected["textures"]), len(actual["textures"]))
            for expected_texture, actual_texture in zip(expected["textures"], actual["textures"]):
                for field in (
                    "texture",
                    "map",
                    "sampler_flags",
                    "filter",
                    "address_u",
                    "address_v",
                    "address_w",
                    "max_anisotropy",
                ):
                    self.assertEqual(expected_texture[field], actual_texture[field])
                expected_lod = [
                    expected_texture["min_lod"],
                    expected_texture["max_lod"],
                    expected_texture["lod_bias"],
                ]
                actual_lod = [
                    actual_texture["min_lod"],
                    actual_texture["max_lod"],
                    actual_texture["lod_bias"],
                ]
                self.assertEqual(float_bits(expected_lod), float_bits(actual_lod))


if __name__ == "__main__":
    unittest.main()
