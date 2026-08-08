# MDB Exporter for Blender
# Author: Smileynator

import bpy
import json
import mathutils
import os
from dataclasses import dataclass, field

from .mdb_format import (
    BONE_METADATA_PROPERTIES,
    EDF5_VERSION,
    EDF6_VERSION,
    MATERIAL_METADATA_PROPERTIES,
    SOURCE_ID_PROPERTY,
    TEXTURE_METADATA_PROPERTIES,
    VERTEX_TYPE_FLOAT2,
    VERTEX_TYPE_FLOAT3,
    VERTEX_TYPE_FLOAT4,
    VERTEX_TYPE_HALF4,
    VERTEX_TYPE_UBYTE4,
)
from .mdb_writer import (
    rewrite_offset,
    write_ascii_strings as write_ascii_string,
    write_bone_data,
    write_header,
    write_indexed_strings,
    write_material_data,
    write_mdb,
    write_mesh_data,
    write_object_data,
    write_texture_data,
    write_utf16_strings,
    write_vertex_data,
)

# Original model is Y UP, but blender is Z UP by default, we convert that here.
bone_up_Y = mathutils.Matrix(((1.0, 0.0, 0.0, 0.0),
                              (0.0, 0.0, -1.0, 0.0),
                              (0.0, 1.0, 0.0, 0.0),
                              (0.0, 0.0, 0.0, 1.0)))


def source_id_of(data_block):
    if data_block is None:
        return None
    source_id = data_block.get(SOURCE_ID_PROPERTY)
    if source_id:
        return source_id
    source_id = source_id_of(getattr(data_block, 'data', None))
    if source_id:
        return source_id
    return source_id_of(getattr(data_block, 'parent', None))


def get_export_source_id(context):
    active_source_id = source_id_of(context.active_object)
    source_ids = {
        source_id_of(obj)
        for obj in bpy.data.objects
        if source_id_of(obj)
    }
    if active_source_id:
        return active_source_id, None
    if len(source_ids) == 1:
        return source_ids.pop(), None
    if not source_ids:
        return None, (
            'This scene has no current MDB source association. Re-import the '
            'source MDB with this add-on version.'
        )
    return None, (
        'Multiple imported MDB models are present. Select an object belonging '
        'to the model you want to export.'
    )


def get_source_armature(source_id):
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and source_id_of(obj) == source_id:
            return obj.data
    return None


def get_unique_names(source_id, armature):
    names_set = set()
    names_list = []
    # Note, bones come first, and in the exact order
    # Messing this up causes the game to break frogs and other detaching limb systems.

    # Get all bone names
    for bone in armature.bones:
        if bone.name not in names_set:
            names_set.add(bone.name)
            names_list.append(bone.name)

    # Only model-container empties belong in the MDB name table. Armatures,
    # cameras, lights, and unrelated scene helpers must not leak into it.
    for obj in iter_mdb_containers(source_id):
        name = obj['mdb_name']
        if name not in names_set:
            names_set.add(name)
            names_list.append(name)

    # Only materials that will actually be exported belong in the table.
    for material in bpy.data.materials:
        if (
            source_id_of(material) == source_id
            and material.use_nodes
            and find_mdb_shader_node(material) is not None
        ):
            name = material['mdb_name']
            if name not in names_set:
                names_set.add(name)
                names_list.append(name)
    return names_list


def iter_mdb_containers(source_id):
    for obj in bpy.data.objects:
        if (
            source_id_of(obj) == source_id
            and obj.data is None
            and any(child.type == 'MESH' for child in obj.children)
        ):
            yield obj


def iter_exported_mesh_objects(source_id):
    for container in iter_mdb_containers(source_id):
        for child in container.children:
            if child.type == 'MESH':
                yield child


def iter_assigned_materials(source_id):
    seen = set()
    for mesh_object in iter_exported_mesh_objects(source_id):
        for material in mesh_object.data.materials:
            if material is None or material in seen:
                continue
            seen.add(material)
            yield material


def find_non_triangulated_meshes(source_id):
    return [
        mesh_object.name
        for mesh_object in iter_exported_mesh_objects(source_id)
        if any(polygon.loop_total != 3 for polygon in mesh_object.data.polygons)
    ]


def find_material_slot_issues(source_id):
    issues = []
    for mesh_object in iter_exported_mesh_objects(source_id):
        materials = mesh_object.data.materials
        if len(materials) == 0:
            issues.append(f"mesh '{mesh_object.name}': no material assigned")
        elif len(materials) > 1:
            issues.append(
                f"mesh '{mesh_object.name}': {len(materials)} material slots "
                '(MDB supports exactly one)',
            )
        elif materials[0] is None:
            issues.append(f"mesh '{mesh_object.name}': empty material slot")
    return issues


def find_overweight_vertices(source_id):
    for mesh_object in iter_exported_mesh_objects(source_id):
        for vertex in mesh_object.data.vertices:
            if sum(group.weight > 0.0 for group in vertex.groups) > 4:
                return True
    return False


def bone_name_to_index(armature):
    return {
        bone.name: index
        for index, bone in enumerate(armature.bones)
    }


def strongest_vertex_influences(vertex):
    return sorted(
        (
            (assignment.weight, assignment.group)
            for assignment in vertex.groups
            if assignment.weight > 0.0
        ),
        reverse=True,
    )[:4]


def find_bone_weight_issues(source_id, armature):
    if armature is None:
        return []
    issues = []
    bone_indices = bone_name_to_index(armature)
    for mesh_object in iter_exported_mesh_objects(source_id):
        unknown_groups = set()
        unaddressable_bones = set()
        for vertex in mesh_object.data.vertices:
            for _, group_index in strongest_vertex_influences(vertex):
                group_name = mesh_object.vertex_groups[group_index].name
                if group_name not in bone_indices:
                    unknown_groups.add(group_name)
                elif bone_indices[group_name] > 0xFF:
                    unaddressable_bones.add(
                        (group_name, bone_indices[group_name]),
                    )
        if unknown_groups:
            issues.append(
                f"mesh '{mesh_object.name}': weighted groups do not match MDB "
                'bones: ' + ', '.join(sorted(unknown_groups)),
            )
        if unaddressable_bones:
            formatted_bones = ', '.join(
                f'{name} (index {index})'
                for name, index in sorted(
                    unaddressable_bones,
                    key=lambda item: item[1],
                )
            )
            issues.append(
                f"mesh '{mesh_object.name}': weighted bones exceed the 8-bit "
                f'blend-index limit: {formatted_bones}. Reduce or carefully '
                'reorder the armature so every deforming bone is within MDB '
                'indices 0-255',
            )
    return issues


def get_bone_data(names, armature):
    bones = []
    if not armature:
        return
    # Make a lookup for bone indexes
    blender_bones = {}
    for index, bone in enumerate(armature.bones):
        blender_bones[bone] = index
    # Populate bone data
    for bone in armature.bones:
        bone_data = {}
        bone_data['index'] = blender_bones[bone]
        bone_data['name'] = bone.name
        bone_data['parent'] = blender_bones[bone.parent] if bone.parent else -1
        bone_data['next_sibling'] = -1
        # Find next sibling if any
        if bone.parent:
            found_self = False
            for sibling in bone.parent.children:
                if sibling == bone:
                    found_self = True
                    continue
                if found_self:
                    bone_data['next_sibling'] = blender_bones[sibling]
                    break
        # Find first child if i have any
        bone_data['first_child'] = blender_bones[bone.children[0]] if bone.children else -1
        bone_data['name_index'] = names.index(bone.name)
        bone_data['child_count'] = len(bone.children)
        # Unpack the 4x4 matrices into a flat list of 16 float values
        # Local matrix back to file format
        matrix = bone_up_Y.inverted() @ bone.matrix_local
        if bone.parent:
            matrix = bone.parent.matrix_local.inverted() @ bone.matrix_local
        bone_data['local_matrix'] = [element for col in matrix.col for element in col]
        # Inverse bind matrix
        inv_matrix = bone.matrix_local.inverted() @ bone_up_Y
        bone_data['inverse_bind_matrix'] = [element for col in inv_matrix.col for element in col]
        bone_data['inv_matrix'] = inv_matrix
        bone_data['world_bind_translation'] = (
            bone_up_Y.inverted() @ bone.matrix_local
        ).translation.copy()
        bone_data['participation_metadata'] = bone['participation_metadata']
        bone_data['semantic_role'] = bone['semantic_role']
        bone_data['normalized_bone_flag'] = bool(bone['normalized_bone_flag'])
        bone_data['bounds_half_size'] = list(bone['bounds_half_size'])
        bone_data['bounds_center'] = list(bone['bounds_center'])
        # Append the bone data to the list
        bones.append(bone_data)
    return bones


def get_textures(source_id):
    textures = []

    # Imported materials retain the original table, including unused entries.
    for material in bpy.data.materials:
        if source_id_of(material) != source_id:
            continue
        encoded_table = material.get('mdb_texture_table')
        if encoded_table:
            table = json.loads(encoded_table)
            if len(table) > len(textures):
                textures = table

    # Used binding nodes expose editable copies of their table entries.
    for material in bpy.data.materials:
        if source_id_of(material) != source_id or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type != 'TEX_IMAGE':
                continue
            if 'mdb_texture_index' in node:
                index = node['mdb_texture_index']
                while len(textures) <= index:
                    textures.append({'index': len(textures), 'name': '', 'filename': ''})
                textures[index] = {
                    'index': index,
                    'name': node['mdb_texture_name'],
                    'filename': get_export_texture_filename(node),
                }
    return textures


def get_materials(indexed_strings, source_id):
    materials = []
    valid_materials = []
    # Only explicitly tagged MDB materials are exportable.
    for material in bpy.data.materials:
        if (
            source_id_of(material) == source_id
            and material.use_nodes
            and find_mdb_shader_node(material) is not None
        ):
            valid_materials.append(material)

    valid_materials.sort(key=lambda material: material['mdb_material_index'])

    # Process the valid materials
    for material in valid_materials:
        material_data = {
            'index': material['mdb_material_index'],
            'mat_name_index': indexed_strings.index(material['mdb_name']),
            'blender_material': material,
            'draw_priority': material['draw_priority'],
            'render_queue_class': material['render_queue_class'],
            'render_participation_flags': material['render_participation_flags'],
        }
        parameters = []
        texture_data = []
        node = find_mdb_shader_node(material)
        material_data['shader_name'] = material['mdb_shader_name']

        parameters = [
            get_preserved_parameter(node.inputs, parameter)
            for parameter in json.loads(node['mdb_parameters'])
        ]
        texture_nodes = [
            texture_node for texture_node in material.node_tree.nodes
            if texture_node.type == 'TEX_IMAGE' and 'mdb_texture_binding' in texture_node
        ]
        texture_nodes.sort(key=lambda texture_node: texture_node['mdb_texture_binding'])
        texture_data = [get_preserved_texture(texture_node) for texture_node in texture_nodes]
        material_data['parameters'] = parameters
        material_data['parameter_count'] = len(parameters)
        material_data['parameter_offset'] = 0
        material_data['textures'] = texture_data
        material_data['texture_count'] = len(texture_data)
        material_data['texture_offset'] = 0
        materials.append(material_data)
    return materials


def find_mdb_shader_node(material):
    for node in material.node_tree.nodes:
        if not hasattr(node, 'inputs') or node.type != 'GROUP':
            continue
        if 'mdb_shader_name' in node:
            return node
    return None


def get_preserved_parameter(all_inputs, parameter):
    values = [parameter[f'val{index}'] for index in range(6)]
    name = parameter['name']
    size = parameter['size']

    if size == 1 and all_inputs.get(name) is not None:
        values[0] = all_inputs[name].default_value
    elif size == 2 and all_inputs.get(name + '_x') is not None:
        values[0] = all_inputs[name + '_x'].default_value
        values[1] = all_inputs[name + '_y'].default_value
    elif size >= 3 and all_inputs.get(name) is not None:
        color = all_inputs[name].default_value
        values[0:3] = color[0:3]
        alpha = all_inputs.get(name + '_alpha')
        if parameter['type'] == 3 and alpha is not None:
            values[3] = alpha.default_value

    return {
        'name': name,
        'values': values,
        'type': parameter['type'],
        'size': size,
    }


def get_export_texture_filename(image_node):
    # The image selected in Blender's Image Texture node is the natural
    # authoring source. Its disk filename therefore overrides the imported
    # MDB table entry; the remaining properties preserve EDF-only metadata.
    texture_filename = image_node['mdb_texture_filename']
    image = getattr(image_node, 'image', None)
    if image is not None:
        image_path = getattr(image, 'filepath_raw', '') or getattr(
            image,
            'filepath',
            '',
        )
        if image_path:
            # Blender paths can use either separator, regardless of the host
            # which created the .blend file.
            texture_filename = image_path.replace('\\', '/').rsplit('/', 1)[-1]
    return texture_filename


def get_preserved_texture(image_node):
    return {
        'texture_index': image_node['mdb_texture_index'],
        'type': image_node['mdb_texture_slot'],
        'sampler_flags': image_node['mdb_sampler_flags'],
        'filter': image_node['mdb_filter'],
        'address_u': image_node['mdb_address_u'],
        'address_v': image_node['mdb_address_v'],
        'address_w': image_node['mdb_address_w'],
        'max_anisotropy': image_node['mdb_max_anisotropy'],
        'min_lod': image_node['mdb_min_lod'],
        'max_lod': image_node['mdb_max_lod'],
        'lod_bias': image_node['mdb_lod_bias'],
    }


# Gathers all objects and their underlying data
def get_objects(
    names,
    materials,
    game_version,
    source_id,
    bone_indices,
):
    objects = []
    obj_index = 0
    for obj in iter_mdb_containers(source_id):
        object_name = obj['mdb_name']
        object_data = {
            'index': obj_index,
            'name': object_name,
            'name_index': names.index(object_name),
        }
        # Get all meshes
        mesh_objects = [child for child in obj.children if child.type == 'MESH']
        object_data['mesh_count'] = len(mesh_objects)
        object_data['mesh_data'] = []
        for index, mesh_object in enumerate(mesh_objects):
            object_data['mesh_data'].append(
                get_mesh_data(
                    index,
                    mesh_object,
                    materials,
                    game_version,
                    bone_indices,
                )
            )

        obj_index += 1
        objects.append(object_data)
    return objects


def split_vertices(mesh):
    """Return one exported vertex for every distinct per-loop vertex payload."""
    unique_vertices = {}
    vertex_loop_pairs = []
    indices = []
    for loop in mesh.loops:
        uv_key = tuple(
            tuple(uv_layer.data[loop.index].uv)
            for uv_layer in mesh.uv_layers
        )
        key = (
            loop.vertex_index,
            tuple(loop.normal),
            tuple(loop.tangent),
            loop.bitangent_sign,
            uv_key,
        )
        exported_index = unique_vertices.get(key)
        if exported_index is None:
            exported_index = len(vertex_loop_pairs)
            unique_vertices[key] = exported_index
            vertex_loop_pairs.append((mesh.vertices[loop.vertex_index], loop))
        indices.append(exported_index)
    return vertex_loop_pairs, indices


# Gathers mesh info data
def get_mesh_data(
    index,
    mesh_object,
    materials,
    game_version,
    bone_indices,
):
    mesh = mesh_object.data
    material_index = -1
    # Get the material used for this mesh
    for mat in materials:
        if mesh.materials[0] == mat['blender_material']:
            material_index = mat['index']
            break
    bone_weights = min(
        4,
        max(
            (
                sum(group.weight > 0.0 for group in vertex.groups)
                for vertex in mesh.vertices
            ),
            default=0,
        ),
    )
    is_skinned = bone_weights > 0
    mesh.calc_tangents()
    vertex_loop_pairs, indices = split_vertices(mesh)
    mesh_data = {
        'is_skinned': int(is_skinned),
        'bone_influence_count': bone_weights,
        'material_index': material_index,
        'vertex_count': len(vertex_loop_pairs),
        'mesh_index': index,
        'vertex_layouts': get_vertex_layouts(
            mesh_object,
            is_skinned,
            vertex_loop_pairs,
            game_version,
            bone_indices,
        ),
        'index_count': len(indices),
        'indices': indices,
    }
    # Total byte stride of one interleaved vertex record.
    data_size = 0
    for data in mesh_data['vertex_layouts']:
        data_size += data['size']
    mesh_data['vertex_stride'] = data_size
    mesh_data['layout_count'] = len(mesh_data['vertex_layouts'])
    return mesh_data

# Build the interleaved vertex-layout channels and their values.
def get_vertex_layouts(
    mesh_object,
    is_skinned,
    vertex_loop_pairs,
    game_version,
    bone_indices,
):
    mesh = mesh_object.data
    vertex_layouts = []
    # Due to the nature of this data, it makes sense to just generate it as i saw in example files
    # We cannot be certain for each of these if they exist or not until proven otherwise in practice
    if is_skinned:
        blend_indices_data = {
            'name': 'BLENDINDICES',
            'type': VERTEX_TYPE_UBYTE4,
            'size': 4,
            'channel': 0,
            'data': []
        }
        vertex_layouts.append(blend_indices_data)
        blend_weight_data = {
            'name': 'BLENDWEIGHT',
            'type': VERTEX_TYPE_FLOAT4,
            'size': 16,
            'channel': 0,
            'data': []
        }
        vertex_layouts.append(blend_weight_data)
    binormal_data = {
        'name': 'binormal',
        'type': VERTEX_TYPE_HALF4,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertex_layouts.append(binormal_data)
    normal_data = {
        'name': 'normal',
        'type': VERTEX_TYPE_HALF4,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertex_layouts.append(normal_data)
    position_data = {
        'name': 'position',
        'type': VERTEX_TYPE_HALF4,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertex_layouts.append(position_data)
    tangent_data = {
        'name': 'tangent',
        'type': VERTEX_TYPE_HALF4,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertex_layouts.append(tangent_data)
    # We store a UV array seperately just for easy access when looping over indices.
    uv_data = []
    for channel, uv in enumerate(mesh.uv_layers):
        texcoord_data = {
            'name': 'texcoord',
            'type': VERTEX_TYPE_FLOAT2,
            'size': 8,
            'channel': channel,
            'data': []
        }
        uv_data.append(texcoord_data)
        vertex_layouts.append(texcoord_data)

    # Capitalize all the names in EDF6, as they seem to expect that
    if game_version == 6:
        for data in uv_data:
            data['name'] = data['name'].upper()
    
    # Populate each exported vertex from its source vertex and face corner.
    uv_count = len(mesh.uv_layers)
    for vert, loop in vertex_loop_pairs:
        position_data['data'].append([vert.co[0], vert.co[2], -vert.co[1], 1.0])  # Correct orientation from import!
        normal_data['data'].append([loop.normal[0], loop.normal[2], -loop.normal[1], 1.0])
        binormal_data['data'].append([loop.bitangent[0], loop.bitangent[2], -loop.bitangent[1], 1.0])
        tangent_data['data'].append([loop.tangent[0], loop.tangent[2], -loop.tangent[1], 1.0])
        # UVs
        for i in range(uv_count):
            uv_vector = mesh.uv_layers[i].data[loop.index].uv
            uv_data[i]['data'].append([uv_vector[0], 1.0 - uv_vector[1]])  # UV map flip Y value
        # Skinned mesh
        if is_skinned:
            influences = [
                (
                    weight,
                    bone_indices[mesh_object.vertex_groups[group_index].name],
                )
                for weight, group_index in strongest_vertex_influences(vert)
            ]
            weight_total = sum(weight for weight, _ in influences)
            weights = [
                weight / weight_total
                for weight, _ in influences
            ]
            indices = [group_index for _, group_index in influences]
            while len(weights) < 4:
                weights.append(0.0)
                indices.append(0)
            blend_weight_data['data'].append([weights[0], weights[1], weights[2], weights[3]])
            blend_indices_data['data'].append([indices[0], indices[1], indices[2], indices[3]])
    # Set offsets in data
    offset = 0
    for layout in vertex_layouts:
        layout['offset'] = offset
        offset += layout['size']
    return vertex_layouts


def sort_objects_by_name_order(array_to_sort, reference_array):
    # Create a dictionary to store the index of each object's name in the reference array
    name_index_map = {obj['name']: i for i, obj in enumerate(reference_array)}

    # Sort the main array based on the index of each object's name in the reference array
    sorted_array = sorted(array_to_sort, key=lambda x: name_index_map.get(x['name'], len(reference_array)))

    return sorted_array


def resolve_bone_name_matches(bones, objects):
    positions_by_object_index = {}
    for object_data in objects:
        positions = []
        for mesh_data in object_data['mesh_data']:
            position_layout = next(
                data for data in mesh_data['vertex_layouts']
                if data['name'].lower() == 'position'
            )
            positions.extend(
                mathutils.Vector(position[:3])
                for position in position_layout['data']
            )
        positions_by_object_index[object_data['index']] = positions

    objects_by_name = {}
    for object_data in objects:
        if object_data['name']:
            objects_by_name.setdefault(object_data['name'], []).append(object_data)

    bones_by_name = {}
    for bone in bones:
        if bone['participation_metadata'] in (1, 2) and bone['name']:
            bones_by_name.setdefault(bone['name'], []).append(bone)

    matches = {}
    for name, matching_bones in bones_by_name.items():
        remaining_objects = list(objects_by_name.get(name, ()))
        for bone in matching_bones:
            if not remaining_objects:
                break
            bone_position = bone['world_bind_translation']
            candidates = []
            for object_data in remaining_objects:
                vertices = positions_by_object_index[object_data['index']]
                if not vertices:
                    continue
                centroid = (
                    sum(vertices, mathutils.Vector((0.0, 0.0, 0.0)))
                    / len(vertices)
                )
                candidates.append((
                    (bone_position - centroid).length_squared,
                    object_data,
                ))
            if not candidates:
                break
            _, closest_object = min(candidates, key=lambda candidate: candidate[0])
            matches[bone['index']] = positions_by_object_index[closest_object['index']]
            remaining_objects.remove(closest_object)
    return matches


def recompute_bone_bounding_boxes(bones, objects):
    """Recompute the two float4 bone bounds required by the game."""
    skinned_vertices = {}
    for object_data in objects:
        for mesh_data in object_data['mesh_data']:
            if not mesh_data['is_skinned']:
                continue
            layouts = {
                data['name'].lower(): data
                for data in mesh_data['vertex_layouts']
            }
            for position, indices, weights in zip(
                layouts['position']['data'],
                layouts['blendindices']['data'],
                layouts['blendweight']['data'],
            ):
                vertex = mathutils.Vector(position[:3])
                for bone_index, weight in zip(indices, weights):
                    if weight > 0.0:
                        skinned_vertices.setdefault(int(bone_index), []).append(vertex)

    rigid_vertices = resolve_bone_name_matches(bones, objects)
    for bone in bones:
        if bone['participation_metadata'] == 0:
            continue
        if bone['participation_metadata'] == 3:
            vertices = skinned_vertices.get(bone['index'])
        else:
            vertices = rigid_vertices.get(bone['index'])

        if not vertices:
            bone['bounds_half_size'] = [0.0, 0.0, 0.0, 1.0]
            bone['bounds_center'] = [0.0, 0.0, 0.0, 1.0]
            continue

        local_vertices = [bone['inv_matrix'] @ vertex for vertex in vertices]
        minimum = mathutils.Vector(tuple(
            min(vertex[axis] for vertex in local_vertices)
            for axis in range(3)
        ))
        maximum = mathutils.Vector(tuple(
            max(vertex[axis] for vertex in local_vertices)
            for axis in range(3)
        ))
        size = (maximum - minimum) * 0.5
        offset = (maximum + minimum) * 0.5
        bone['bounds_half_size'] = [size.x, size.y, size.z, 1.0]
        bone['bounds_center'] = [offset.x, offset.y, offset.z, 1.0]


def report_export(operator, level, message):
    if hasattr(operator, 'report'):
        operator.report({level}, message)
    print(f'{level}: {message}')


def find_incomplete_mdb_metadata(source_id, armature):
    missing = []
    if armature is None:
        return ['armature: missing']
    for bone in armature.bones:
        absent = [name for name in BONE_METADATA_PROPERTIES if name not in bone]
        if absent:
            missing.append(f"bone '{bone.name}': {', '.join(absent)}")

    assigned_materials = set(iter_assigned_materials(source_id))
    for material in assigned_materials:
        if source_id_of(material) != source_id:
            missing.append(
                f"material '{material.name}': belongs to a different MDB import",
            )
            continue
        if not material.use_nodes:
            missing.append(f"material '{material.name}': nodes disabled")
            continue
        if find_mdb_shader_node(material) is None:
            missing.append(
                f"material '{material.name}': current MDB shader metadata",
            )

    for material in bpy.data.materials:
        if source_id_of(material) != source_id:
            continue
        shader_node = (
            find_mdb_shader_node(material)
            if material.use_nodes
            else None
        )
        if shader_node is None:
            continue
        absent = [
            name for name in MATERIAL_METADATA_PROPERTIES
            if name not in material
        ]
        if 'mdb_parameters' not in shader_node:
            absent.append('shader node mdb_parameters')
        for texture_node in material.node_tree.nodes:
            if texture_node.type != 'TEX_IMAGE' or 'mdb_texture_binding' not in texture_node:
                continue
            absent.extend(
                f"texture node {name}"
                for name in TEXTURE_METADATA_PROPERTIES
                if name not in texture_node
            )
        if absent:
            missing.append(f"material '{material.name}': {', '.join(absent)}")

    for container in iter_mdb_containers(source_id):
        if 'mdb_name' not in container:
            missing.append(f"object '{container.name}': mdb_name")
    return missing


@dataclass
class ExportData:
    game_version: int
    file_version: int
    names: list
    bones: list
    textures: list
    materials: list
    objects: list
    ascii_strings: list = field(default_factory=list)
    utf16_strings: list = field(default_factory=list)


def find_index_limit_issues(objects):
    issues = []
    for object_data in objects:
        for mesh in object_data['mesh_data']:
            if mesh['vertex_count'] > 0x10000:
                issues.append(
                    f"object '{object_data['name']}' mesh "
                    f"{mesh['mesh_index']}: {mesh['vertex_count']} exported "
                    'vertices exceed the 65,536 addressable by 16-bit indices. '
                    'Split the geometry into multiple child meshes, or reduce '
                    'geometry and UV/normal seams',
                )
            elif any(index > 0xFFFF for index in mesh['indices']):
                issues.append(
                    f"object '{object_data['name']}' mesh "
                    f"{mesh['mesh_index']}: index exceeds the 16-bit limit. "
                    'Split the geometry into multiple child meshes',
                )
    return issues


def build_export_data(game_version, source_id, armature):
    names = get_unique_names(source_id, armature)
    bones = get_bone_data(names, armature)
    textures = get_textures(source_id)
    materials = get_materials(names, source_id)
    objects = get_objects(
        names,
        materials,
        game_version,
        source_id,
        bone_name_to_index(armature),
    )
    recompute_bone_bounding_boxes(bones, objects)
    objects = sort_objects_by_name_order(objects, bones)
    file_version = EDF5_VERSION if game_version == 5 else EDF6_VERSION
    return ExportData(
        game_version=game_version,
        file_version=file_version,
        names=names,
        bones=bones,
        textures=textures,
        materials=materials,
        objects=objects,
    )


def save(operator, context, filepath="", version=0, **kwargs):
    del kwargs
    if version not in (5, 6):
        report_export(operator, 'ERROR', f'Unsupported export version {version}.')
        return {'CANCELLED'}
    source_id, source_error = get_export_source_id(context)
    if source_error:
        report_export(operator, 'ERROR', source_error)
        return {'CANCELLED'}
    armature = get_source_armature(source_id)
    non_triangular = find_non_triangulated_meshes(source_id)
    if non_triangular:
        message = (
            'MDB export requires triangulated meshes. Export cancelled for: '
            + ', '.join(non_triangular)
        )
        report_export(operator, 'ERROR', message)
        return {'CANCELLED'}
    material_issues = find_material_slot_issues(source_id)
    if material_issues:
        report_export(
            operator,
            'ERROR',
            'Each MDB mesh requires exactly one material. Export cancelled: '
            + '; '.join(material_issues[:8]),
        )
        return {'CANCELLED'}
    incomplete_metadata = find_incomplete_mdb_metadata(source_id, armature)
    if incomplete_metadata:
        report_export(
            operator,
            'ERROR',
            'This scene lacks current lossless MDB metadata. Re-import the '
            'source MDB with this add-on version. Missing: '
            + '; '.join(incomplete_metadata[:8]),
        )
        return {'CANCELLED'}
    bone_weight_issues = find_bone_weight_issues(source_id, armature)
    if bone_weight_issues:
        report_export(
            operator,
            'ERROR',
            'MDB skinning metadata is invalid. Export cancelled: '
            + '; '.join(bone_weight_issues[:8]),
        )
        return {'CANCELLED'}
    if find_overweight_vertices(source_id):
        report_export(
            operator,
            'WARNING',
            'Vertices with more than four bone influences will use their four '
            'strongest influences, normalized to a total weight of 1.',
        )
    data = build_export_data(version, source_id, armature)
    index_limit_issues = find_index_limit_issues(data.objects)
    if index_limit_issues:
        report_export(
            operator,
            'ERROR',
            'MDB uses 16-bit mesh indices. Export cancelled: '
            + '; '.join(index_limit_issues[:8]),
        )
        return {'CANCELLED'}

    with open(filepath, 'wb') as file:
        write_mdb(file, data)
    return {'FINISHED'}
