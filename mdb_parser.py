"""Binary MDB parser.

The parser produces plain dictionaries and has no ``bpy`` dependency. Blender
scene construction belongs in ``import_mdb``.
"""

import mathutils
import numpy as np

from .mdb_format import (
    BONE_RECORD_SIZE,
    EDF6_VERSION,
    HEADER_SIZE,
    MAGIC,
    MATERIAL_PARAMETER_RECORD_SIZE,
    MATERIAL_RECORD_SIZE,
    MATERIAL_TEXTURE_RECORD_SIZE,
    MESH_RECORD_SIZE,
    NAME_RECORD_SIZE,
    OBJECT_RECORD_SIZE,
    SUPPORTED_VERSIONS,
    TEXTURE_RECORD_SIZE,
    VERTEX_LAYOUT_RECORD_SIZE,
    VERTEX_TYPE_FLOAT2,
    VERTEX_TYPE_FLOAT3,
    VERTEX_TYPE_FLOAT4,
    VERTEX_TYPE_HALF4,
    VERTEX_TYPE_UBYTE4,
    MdbFormatError,
    expect_record_size,
    read_byte,
    read_exact,
    read_float,
    read_int,
    read_short,
    read_str,
    read_struct,
    read_uint,
    read_ushort,
    read_wstr,
)


def read_matrix(stream):
    matrix = mathutils.Matrix()
    for row in range(4):
        for column in range(4):
            matrix[column][row] = read_float(stream)
    return matrix


def parse_names(stream, count, offset):
    names = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        string_offset = read_uint(stream)
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            NAME_RECORD_SIZE,
            'name',
        )
        if string_offset:
            stream.seek(record_start + string_offset)
            names.append(read_wstr(stream))
            stream.seek(next_record)
        else:
            names.append(None)
    return names


def parse_bones(stream, count, offset, name_table):
    bones = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        bone = {
            'index': read_uint(stream),
            'parent': read_int(stream),
            'next_sibling': read_int(stream),
            'first_child': read_int(stream),
        }
        name_index = read_uint(stream)
        bone['name'] = name_table[name_index]
        bone['child_count'] = read_uint(stream)
        bone['participation_metadata'] = read_exact(
            stream,
            1,
            'bone participation metadata',
        )[0]
        bone['semantic_role'] = read_byte(stream)
        bone['normalized_bone_flag'] = (
            read_exact(stream, 1, 'normalized bone flag')[0] == 1
        )
        read_exact(stream, 5, 'bone reserved bytes')
        bone['matrix_local'] = read_matrix(stream)
        bone['matrix_invbind'] = read_matrix(stream)
        bone['bounds_half_size'] = [read_float(stream) for _ in range(4)]
        bone['bounds_center'] = [read_float(stream) for _ in range(4)]
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            BONE_RECORD_SIZE,
            'bone',
        )
        stream.seek(next_record)
        bones.append(bone)
    return bones


def parse_textures(stream, count, offset):
    textures = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        texture = {'index': read_uint(stream)}
        name_offset = read_uint(stream)
        filename_offset = read_uint(stream)
        read_exact(stream, 4, 'texture reserved bytes')
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            TEXTURE_RECORD_SIZE,
            'texture',
        )
        stream.seek(record_start + name_offset)
        texture['name'] = read_wstr(stream)
        stream.seek(record_start + filename_offset)
        texture['filename'] = read_wstr(stream)
        stream.seek(next_record)
        textures.append(texture)
    return textures


def parse_mat_param(stream, count, offset):
    parameters = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        parameter = {
            f'val{index}': read_float(stream)
            for index in range(6)
        }
        name_offset = read_uint(stream)
        parameter['type'] = read_exact(
            stream,
            1,
            'material parameter type',
        )[0]
        parameter['size'] = read_exact(
            stream,
            1,
            'material parameter component count',
        )[0]
        read_exact(stream, 2, 'material parameter padding')
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            MATERIAL_PARAMETER_RECORD_SIZE,
            'material parameter',
        )
        stream.seek(record_start + name_offset)
        parameter['name'] = read_str(stream)
        stream.seek(next_record)
        parameters.append(parameter)
    return parameters


def parse_mat_txr(stream, count, offset):
    textures = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        texture = {'texture': read_uint(stream)}
        type_name_offset = read_uint(stream)
        texture['sampler_flags'] = read_ushort(stream)
        texture['filter'] = read_short(stream)
        texture['address_u'] = read_exact(stream, 1, 'texture address U')[0]
        texture['address_v'] = read_exact(stream, 1, 'texture address V')[0]
        texture['address_w'] = read_exact(stream, 1, 'texture address W')[0]
        texture['max_anisotropy'] = read_byte(stream)
        texture['min_lod'] = read_float(stream)
        texture['max_lod'] = read_float(stream)
        texture['lod_bias'] = read_float(stream)
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            MATERIAL_TEXTURE_RECORD_SIZE,
            'material texture',
        )
        stream.seek(record_start + type_name_offset)
        texture['map'] = read_str(stream)
        stream.seek(next_record)
        textures.append(texture)
    return textures


def parse_materials(stream, count, offset, name_table):
    materials = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        material = {
            'index': read_ushort(stream),
            'draw_priority': read_byte(stream),
            'render_queue_class': read_exact(
                stream,
                1,
                'render queue class',
            )[0],
        }
        material_name_index = read_uint(stream)
        shader_offset = read_uint(stream)
        parameter_offset = read_uint(stream)
        parameter_count = read_uint(stream)
        texture_offset = read_uint(stream)
        texture_count = read_uint(stream)
        material['render_participation_flags'] = read_exact(
            stream,
            1,
            'render participation flags',
        )[0]
        read_exact(stream, 3, 'material reserved bytes')
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            MATERIAL_RECORD_SIZE,
            'material',
        )
        material['name'] = name_table[material_name_index]
        stream.seek(record_start + shader_offset)
        material['shader'] = read_wstr(stream)
        material['params'] = parse_mat_param(
            stream,
            parameter_count,
            record_start + parameter_offset,
        )
        material['textures'] = parse_mat_txr(
            stream,
            texture_count,
            record_start + texture_offset,
        )
        stream.seek(next_record)
        materials.append(material)
    return materials


def parse_vertex_layout(stream, count, offset):
    layout = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        element = {
            'type': read_uint(stream),
            'offset': read_uint(stream),
            'channel': read_uint(stream),
        }
        name_offset = read_uint(stream)
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            VERTEX_LAYOUT_RECORD_SIZE,
            'vertex layout',
        )
        stream.seek(record_start + name_offset)
        element['name'] = read_str(stream)
        stream.seek(next_record)
        layout.append(element)
    return layout


def parse_indices(stream, count, offset):
    stream.seek(offset)
    return [read_ushort(stream) for _ in range(count)]


def parse_vertices(stream, count, offset, layout, vertex_stride):
    vertices = []
    for vertex_index in range(count):
        vertex_start = offset + vertex_index * vertex_stride
        vertex = {}
        for element in layout:
            stream.seek(vertex_start + element['offset'])
            vertex_type = element['type']
            if vertex_type == VERTEX_TYPE_FLOAT4:
                values = read_struct(stream, '4f', 'float4 vertex element')
            elif vertex_type == VERTEX_TYPE_FLOAT3:
                values = read_struct(stream, '3f', 'float3 vertex element')
            elif vertex_type == VERTEX_TYPE_HALF4:
                values = np.frombuffer(
                    read_exact(stream, 8, 'half4 vertex element'),
                    dtype=np.half,
                )
            elif vertex_type == VERTEX_TYPE_FLOAT2:
                values = read_struct(stream, '2f', 'float2 vertex element')
            elif vertex_type == VERTEX_TYPE_UBYTE4:
                values = read_struct(stream, '4B', 'ubyte4 vertex element')
            else:
                raise MdbFormatError(
                    f'Unsupported vertex layout type {vertex_type}.'
                )
            key = element['name'].lower() + str(element['channel'])
            vertex[key] = values
        vertices.append(vertex)
    return vertices


def parse_meshes(stream, count, offset):
    meshes = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        mesh = {
            'topology_selector': read_exact(
                stream,
                1,
                'mesh topology selector',
            )[0],
            'is_skinned': read_exact(stream, 1, 'mesh skinning flag')[0],
            'bone_influence_count': read_byte(stream),
            'reserved_alignment': read_exact(
                stream,
                1,
                'mesh reserved alignment',
            )[0],
            'material_index': read_int(stream),
            'reserved_0x08': read_uint(stream),
        }
        layout_offset = read_uint(stream)
        mesh['vertex_stride'] = read_ushort(stream)
        layout_count = read_ushort(stream)
        vertex_count = read_uint(stream)
        mesh['mesh_index'] = read_uint(stream)
        vertex_offset = read_uint(stream)
        index_count = read_uint(stream)
        index_offset = read_uint(stream)
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            MESH_RECORD_SIZE,
            'mesh',
        )
        mesh['layout'] = parse_vertex_layout(
            stream,
            layout_count,
            record_start + layout_offset,
        )
        mesh['indices'] = parse_indices(
            stream,
            index_count,
            record_start + index_offset,
        )
        mesh['vertices'] = parse_vertices(
            stream,
            vertex_count,
            record_start + vertex_offset,
            mesh['layout'],
            mesh['vertex_stride'],
        )
        stream.seek(next_record)
        meshes.append(mesh)
    return meshes


def parse_objects(stream, count, offset, name_table):
    objects = []
    stream.seek(offset)
    for _ in range(count):
        record_start = stream.tell()
        object_data = {'index': read_uint(stream)}
        name_index = read_uint(stream)
        mesh_count = read_uint(stream)
        mesh_offset = read_uint(stream)
        next_record = stream.tell()
        expect_record_size(
            stream,
            record_start,
            OBJECT_RECORD_SIZE,
            'object',
        )
        object_data['name'] = name_table[name_index]
        object_data['meshes'] = parse_meshes(
            stream,
            mesh_count,
            record_start + mesh_offset,
        )
        stream.seek(next_record)
        objects.append(object_data)
    return objects


def parse_mdb(stream, override_version=0):
    stream.seek(0)
    magic = read_exact(stream, 4, 'MDB magic')
    file_version = read_uint(stream)
    name_count = read_uint(stream)
    name_offset = read_uint(stream)
    bone_count = read_uint(stream)
    bone_offset = read_uint(stream)
    object_count = read_uint(stream)
    object_offset = read_uint(stream)
    material_count = read_uint(stream)
    material_offset = read_uint(stream)
    texture_count = read_uint(stream)
    texture_offset = read_uint(stream)
    expect_record_size(stream, 0, HEADER_SIZE, 'header')

    if magic != MAGIC:
        raise MdbFormatError(f'Invalid MDB magic {magic!r}.')
    if override_version:
        file_version = override_version
    elif file_version not in SUPPORTED_VERSIONS:
        raise MdbFormatError(
            f'Unsupported MDB version 0x{file_version:X}.'
        )

    names = parse_names(stream, name_count, name_offset)
    return {
        'version': file_version,
        'is_edf6': file_version == EDF6_VERSION,
        'names': names,
        'bones': parse_bones(stream, bone_count, bone_offset, names),
        'textures': parse_textures(stream, texture_count, texture_offset),
        'materials': parse_materials(
            stream,
            material_count,
            material_offset,
            names,
        ),
        'objects': parse_objects(
            stream,
            object_count,
            object_offset,
            names,
        ),
    }
