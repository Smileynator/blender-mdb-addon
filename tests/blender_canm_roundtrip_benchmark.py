"""Import an MDB/CANM pair, export CANM, and report channel-count drift."""

import importlib.util
import struct
import sys
import tempfile
import time
from pathlib import Path

import bpy


def load_addon(addon_root):
    package_name = "_canm_roundtrip_benchmark"
    spec = importlib.util.spec_from_file_location(
        package_name,
        addon_root / "__init__.py",
        submodule_search_locations=[str(addon_root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = package
    spec.loader.exec_module(package)
    return package


class Operator:
    option_ignore_errors = False
    option_override_version = 0

    def report(self, levels, message):
        print(f"{','.join(sorted(levels))}: {message}")


def channel_count(path):
    with path.open("rb") as stream:
        stream.seek(0x10)
        return struct.unpack("<I", stream.read(4))[0]


def main():
    separator = sys.argv.index("--")
    mdb_path = Path(sys.argv[separator + 1]).resolve()
    canm_path = Path(sys.argv[separator + 2]).resolve()
    addon_root = Path(__file__).resolve().parents[1]
    load_addon(addon_root)
    from _canm_roundtrip_benchmark import export_canm, import_canm, import_mdb

    operator = Operator()

    started = time.perf_counter()
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
    imported = time.perf_counter()

    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / canm_path.name
        assert export_canm.save(
            operator,
            bpy.context,
            filepath=str(output_path),
            version=5,
        ) == {"FINISHED"}
        exported = time.perf_counter()
        source_count = channel_count(canm_path)
        output_count = channel_count(output_path)
        print(
            "CANM round-trip benchmark: "
            f"source_channels={source_count}, "
            f"exported_channels={output_count}, "
            f"drift={output_count - source_count:+d}, "
            f"import_seconds={imported - started:.3f}, "
            f"export_seconds={exported - imported:.3f}"
        )


if __name__ == "__main__":
    main()
