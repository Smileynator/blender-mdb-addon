"""Binary MDB serializer.

Input records are plain dictionaries assembled by ``export_mdb``. This module
contains no Blender dependency.
"""

from .mdb_format import (
    HEADER_SIZE,
    VERTEX_TYPE_FLOAT2,
    VERTEX_TYPE_FLOAT3,
    VERTEX_TYPE_FLOAT4,
    VERTEX_TYPE_HALF4,
    VERTEX_TYPE_UBYTE4,
    write_struct,
)


def write_header(stream, version, names, bones, objects, materials, textures):
    stream.write(b'MDB0')
    write_struct(stream, 'I', version)
    write_struct(stream, 'I', len(names))
    write_struct(stream, 'I', HEADER_SIZE)
    write_struct(stream, 'I', len(bones))
    write_struct(stream, 'I', HEADER_SIZE + len(names) * 4)
    write_struct(stream, 'I', len(objects))
    write_struct(stream, 'I', 0)
    write_struct(stream, 'I', len(materials))
    write_struct(stream, 'I', 0)
    write_struct(stream, 'I', len(textures))
    write_struct(stream, 'I', 0)


def rewrite_offset(stream, write_position, target_position, record_start):
    stream.seek(write_position)
    write_struct(stream, 'I', target_position - record_start)
    stream.seek(target_position)


def write_bone_data(stream, bones):
    for bone in bones:
        write_struct(stream, 'I', bone['index'])
        write_struct(stream, 'i', bone['parent'])
        write_struct(stream, 'i', bone['next_sibling'])
        write_struct(stream, 'i', bone['first_child'])
        write_struct(stream, 'I', bone['name_index'])
        write_struct(stream, 'I', bone['child_count'])
        write_struct(stream, 'B', bone['participation_metadata'])
        write_struct(stream, 'b', bone['semantic_role'])
        write_struct(stream, 'B', bone['normalized_bone_flag'])
        stream.write(bytes(5))
        write_struct(stream, '16f', *bone['local_matrix'])
        write_struct(stream, '16f', *bone['inverse_bind_matrix'])
        write_struct(stream, '4f', *bone['bounds_half_size'])
        write_struct(stream, '4f', *bone['bounds_center'])


def write_texture_data(stream, textures, utf16_strings):
    for fallback_index, texture in enumerate(textures):
        record_start = stream.tell()
        write_struct(stream, 'I', texture.get('index', fallback_index))
        utf16_strings.append({
            'string': texture['name'],
            'base_pos': record_start,
            'write_pos': stream.tell(),
        })
        stream.write(bytes(4))
        utf16_strings.append({
            'string': texture['filename'],
            'base_pos': record_start,
            'write_pos': stream.tell(),
        })
        stream.write(bytes(8))


def write_material_data(stream, materials, ascii_strings, utf16_strings):
    for material in materials:
        material['base_pos'] = stream.tell()
        write_struct(stream, 'H', material['index'])
        write_struct(stream, 'b', material['draw_priority'])
        write_struct(stream, 'B', material['render_queue_class'])
        write_struct(stream, 'I', material['mat_name_index'])
        utf16_strings.append({
            'string': material['shader_name'],
            'base_pos': material['base_pos'],
            'write_pos': stream.tell(),
        })
        stream.write(bytes(4))
        material['parameter_pos'] = stream.tell()
        write_struct(stream, 'i', 0)
        write_struct(stream, 'i', material['parameter_count'])
        material['texture_pos'] = stream.tell()
        write_struct(stream, 'i', 0)
        write_struct(stream, 'i', material['texture_count'])
        write_struct(stream, 'B', material['render_participation_flags'])
        stream.write(bytes(3))

    for material in materials:
        parameters_position = stream.tell()
        rewrite_offset(
            stream,
            material['parameter_pos'],
            parameters_position,
            material['base_pos'],
        )
        for parameter in material['parameters']:
            record_start = stream.tell()
            write_struct(stream, '6f', *parameter['values'])
            ascii_strings.append({
                'string': parameter['name'],
                'base_pos': record_start,
                'write_pos': stream.tell(),
            })
            write_struct(stream, 'i', 0)
            write_struct(stream, 'B', parameter['type'])
            write_struct(stream, 'B', parameter['size'])
            stream.write(bytes(2))

        textures_position = stream.tell()
        rewrite_offset(
            stream,
            material['texture_pos'],
            textures_position,
            material['base_pos'],
        )
        for texture in material['textures']:
            record_start = stream.tell()
            write_struct(stream, 'i', texture['texture_index'])
            ascii_strings.append({
                'string': texture['type'],
                'base_pos': record_start,
                'write_pos': stream.tell(),
            })
            write_struct(stream, 'i', 0)
            write_struct(
                stream,
                'HhBBBbfff',
                texture['sampler_flags'],
                texture['filter'],
                texture['address_u'],
                texture['address_v'],
                texture['address_w'],
                texture['max_anisotropy'],
                texture['min_lod'],
                texture['max_lod'],
                texture['lod_bias'],
            )


def write_mesh_data(stream, object_data, ascii_strings):
    for mesh in object_data['mesh_data']:
        mesh['base_pos'] = stream.tell()
        stream.write(bytes([0]))  # Triangle-list topology.
        write_struct(stream, 'B', mesh['is_skinned'])
        write_struct(stream, 'B', mesh['bone_influence_count'])
        stream.write(bytes([0]))
        write_struct(stream, 'i', mesh['material_index'])
        write_struct(stream, 'I', 0)
        mesh['vertex_layout_pos'] = stream.tell()
        write_struct(stream, 'i', 0)
        write_struct(stream, 'H', mesh['vertex_stride'])
        write_struct(stream, 'H', mesh['layout_count'])
        write_struct(stream, 'I', mesh['vertex_count'])
        write_struct(stream, 'I', mesh['mesh_index'])
        mesh['vertex_data_pos'] = stream.tell()
        write_struct(stream, 'i', 0)
        write_struct(stream, 'I', mesh['index_count'])
        mesh['index_data_pos'] = stream.tell()
        write_struct(stream, 'i', 0)

    for mesh in object_data['mesh_data']:
        rewrite_offset(
            stream,
            mesh['vertex_layout_pos'],
            stream.tell(),
            mesh['base_pos'],
        )
        for layout in mesh['vertex_layouts']:
            record_start = stream.tell()
            write_struct(stream, 'I', layout['type'])
            write_struct(stream, 'I', layout['offset'])
            write_struct(stream, 'I', layout['channel'])
            ascii_strings.append({
                'string': layout['name'],
                'base_pos': record_start,
                'write_pos': stream.tell(),
            })
            write_struct(stream, 'I', 0)


def write_vertex_data(stream, object_data):
    for mesh in object_data['mesh_data']:
        rewrite_offset(
            stream,
            mesh['index_data_pos'],
            stream.tell(),
            mesh['base_pos'],
        )
        for index in mesh['indices']:
            write_struct(stream, 'H', index)

    for mesh in object_data['mesh_data']:
        rewrite_offset(
            stream,
            mesh['vertex_data_pos'],
            stream.tell(),
            mesh['base_pos'],
        )
        for vertex_index in range(mesh['vertex_count']):
            for layout in mesh['vertex_layouts']:
                vertex_type = layout['type']
                values = layout['data'][vertex_index]
                if vertex_type == VERTEX_TYPE_FLOAT4:
                    write_struct(stream, '4f', *values)
                elif vertex_type == VERTEX_TYPE_FLOAT3:
                    write_struct(stream, '3f', *values)
                elif vertex_type == VERTEX_TYPE_HALF4:
                    write_struct(stream, '4e', *values)
                elif vertex_type == VERTEX_TYPE_FLOAT2:
                    write_struct(stream, '2f', *values)
                elif vertex_type == VERTEX_TYPE_UBYTE4:
                    write_struct(stream, '4B', *values)
                else:
                    raise ValueError(
                        f'Unsupported vertex layout type {vertex_type}.'
                    )


def write_object_data(stream, objects, ascii_strings):
    for object_data in objects:
        object_data['base_pos'] = stream.tell()
        write_struct(stream, 'I', object_data['index'])
        write_struct(stream, 'i', object_data['name_index'])
        write_struct(stream, 'I', object_data['mesh_count'])
        object_data['mesh_pos'] = stream.tell()
        write_struct(stream, 'I', 0)
    for object_data in objects:
        rewrite_offset(
            stream,
            object_data['mesh_pos'],
            stream.tell(),
            object_data['base_pos'],
        )
        write_mesh_data(stream, object_data, ascii_strings)
    for object_data in objects:
        write_vertex_data(stream, object_data)


def write_ascii_strings(stream, strings):
    positions = {}
    for string_data in strings:
        encoded = string_data['string'].encode('ascii')
        if encoded not in positions:
            positions[encoded] = stream.tell()
            stream.write(encoded + b'\0')
    end_position = stream.tell()
    for string_data in strings:
        encoded = string_data['string'].encode('ascii')
        rewrite_offset(
            stream,
            string_data['write_pos'],
            positions[encoded],
            string_data['base_pos'],
        )
    stream.seek(end_position)


def write_indexed_strings(stream, strings):
    positions = []
    for raw_string in strings:
        positions.append(stream.tell())
        stream.write(raw_string.encode('utf-16-le') + b'\0\0')
    end_position = stream.tell()
    stream.seek(HEADER_SIZE)
    for position in positions:
        write_struct(stream, 'I', position - stream.tell())
    stream.seek(end_position)


def write_utf16_strings(stream, strings):
    positions = {}
    for string_data in strings:
        encoded = string_data['string'].encode('utf-16-le')
        if encoded not in positions:
            positions[encoded] = stream.tell()
            stream.write(encoded + b'\0\0')
    end_position = stream.tell()
    for string_data in strings:
        encoded = string_data['string'].encode('utf-16-le')
        rewrite_offset(
            stream,
            string_data['write_pos'],
            positions[encoded],
            string_data['base_pos'],
        )
    stream.seek(end_position)


def write_mdb(stream, data):
    write_header(
        stream,
        data.file_version,
        data.names,
        data.bones,
        data.objects,
        data.materials,
        data.textures,
    )
    stream.write(bytes([1, 2, 3, 4]) * len(data.names))
    write_bone_data(stream, data.bones)
    rewrite_offset(stream, 0x2C, stream.tell(), 0)
    write_texture_data(stream, data.textures, data.utf16_strings)
    rewrite_offset(stream, 0x24, stream.tell(), 0)
    write_material_data(
        stream,
        data.materials,
        data.ascii_strings,
        data.utf16_strings,
    )
    rewrite_offset(stream, 0x1C, stream.tell(), 0)
    write_object_data(stream, data.objects, data.ascii_strings)
    write_ascii_strings(stream, data.ascii_strings)
    write_indexed_strings(stream, data.names)
    write_utf16_strings(stream, data.utf16_strings)
