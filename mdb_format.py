"""Shared constants and binary primitives for the MDB format.

This module deliberately has no Blender dependency. Keep scene construction in
``import_mdb``/``export_mdb`` and put binary-format facts here.
"""

from struct import calcsize, pack, unpack


MAGIC = b'MDB0'
HEADER_SIZE = 0x30
EDF5_VERSION = 0x14
EDF6_VERSION = 0x20
SUPPORTED_VERSIONS = (EDF5_VERSION, EDF6_VERSION)

SOURCE_ID_PROPERTY = 'mdb_source_id'
SOURCE_PATH_PROPERTY = 'mdb_source_path'

NAME_RECORD_SIZE = 0x04
BONE_RECORD_SIZE = 0xC0
TEXTURE_RECORD_SIZE = 0x10
MATERIAL_RECORD_SIZE = 0x20
MATERIAL_PARAMETER_RECORD_SIZE = 0x20
MATERIAL_TEXTURE_RECORD_SIZE = 0x1C
OBJECT_RECORD_SIZE = 0x10
MESH_RECORD_SIZE = 0x28
VERTEX_LAYOUT_RECORD_SIZE = 0x10

VERTEX_TYPE_FLOAT4 = 1
VERTEX_TYPE_FLOAT3 = 4
VERTEX_TYPE_HALF4 = 7
VERTEX_TYPE_FLOAT2 = 12
VERTEX_TYPE_UBYTE4 = 21

VERTEX_TYPE_SIZES = {
    VERTEX_TYPE_FLOAT4: 16,
    VERTEX_TYPE_FLOAT3: 12,
    VERTEX_TYPE_HALF4: 8,
    VERTEX_TYPE_FLOAT2: 8,
    VERTEX_TYPE_UBYTE4: 4,
}

BONE_METADATA_PROPERTIES = (
    'participation_metadata',
    'semantic_role',
    'normalized_bone_flag',
    'bounds_half_size',
    'bounds_center',
)

MATERIAL_METADATA_PROPERTIES = (
    'mdb_material_index',
    'mdb_name',
    'mdb_shader_name',
    'mdb_texture_table',
    'draw_priority',
    'render_queue_class',
    'render_participation_flags',
)

TEXTURE_METADATA_PROPERTIES = (
    'mdb_texture_index',
    'mdb_texture_name',
    'mdb_texture_filename',
    'mdb_texture_slot',
    'mdb_sampler_flags',
    'mdb_filter',
    'mdb_address_u',
    'mdb_address_v',
    'mdb_address_w',
    'mdb_max_anisotropy',
    'mdb_min_lod',
    'mdb_max_lod',
    'mdb_lod_bias',
)


class MdbFormatError(ValueError):
    """Raised when an MDB stream is truncated or structurally invalid."""


def read_exact(stream, size, description='data'):
    data = stream.read(size)
    if len(data) != size:
        raise MdbFormatError(
            f'Unexpected end of MDB while reading {description}: '
            f'expected {size} bytes, got {len(data)}.'
        )
    return data


def read_struct(stream, fmt, description):
    little_endian_format = '<' + fmt
    size = calcsize(little_endian_format)
    return unpack(
        little_endian_format,
        read_exact(stream, size, description),
    )


def read_ushort(stream):
    return read_struct(stream, 'H', 'uint16')[0]


def read_short(stream):
    return read_struct(stream, 'h', 'int16')[0]


def read_byte(stream):
    return read_struct(stream, 'b', 'int8')[0]


def read_int(stream):
    return read_struct(stream, 'i', 'int32')[0]


def read_uint(stream):
    return read_struct(stream, 'I', 'uint32')[0]


def read_float(stream):
    return read_struct(stream, 'f', 'float32')[0]


def read_str(stream):
    data = bytearray()
    while True:
        char = read_exact(stream, 1, 'Shift-JIS string')
        if char == b'\0':
            return data.decode('shift-jis')
        data.extend(char)


def read_wstr(stream):
    data = bytearray()
    while True:
        char = read_exact(stream, 2, 'UTF-16LE string')
        if char == b'\0\0':
            return data.decode('utf-16-le')
        data.extend(char)


def expect_record_size(stream, record_start, expected_size, record_name):
    actual_size = stream.tell() - record_start
    if actual_size != expected_size:
        raise MdbFormatError(
            f'Invalid {record_name} record size: '
            f'expected {expected_size}, got {actual_size}.'
        )


def write_struct(stream, fmt, *values):
    stream.write(pack('<' + fmt, *values))
