# MDB loader for Blender

import os
import json
import uuid
import bpy
import mathutils
import numpy as np

from dataclasses import dataclass
from .mdb_format import (
    MdbFormatError,
    SOURCE_ID_PROPERTY,
    SOURCE_PATH_PROPERTY,
    read_uint,
)
from .mdb_parser import (
    parse_bones,
    parse_indices,
    parse_mat_param,
    parse_mat_txr,
    parse_materials,
    parse_mdb,
    parse_meshes,
    parse_names,
    parse_objects,
    parse_textures,
    parse_vertex_layout,
    parse_vertices,
)
from .shader import new_socket, get_shader

MDB_EDITING_NOTES = """MDB material editing

- Unlinked numeric/color inputs on the shader group are MDB parameters and are exported.
- Texture and normal connections build the Blender preview. A connected socket's fallback
  value is ignored and is not an MDB value.
- Disconnecting a texture does not remove its MDB binding; bindings are preserved separately.
- Connecting a Blender Value/RGB node does not export the evaluated result. Edit the shader
  group's own input value instead.
- Lookup-only preview defaults are never added to the exported MDB.

See README.md, \"Editing MDB materials\", for the complete rules.
"""
# Original model is Y UP, but blender is Z UP by default, we convert that here.
bone_up_Y = mathutils.Matrix(((1.0, 0.0, 0.0, 0.0),
                            (0.0, 0.0, -1.0, 0.0),
                            (0.0, 1.0, 0.0, 0.0),
                            (0.0, 0.0, 0.0, 1.0)))


@dataclass(frozen=True)
class ImportSettings:
    ignore_errors: bool = False
    override_version: int = 0

def warnparam(socket, material, param):
    if socket is None:
        print('Warning: Material ' + material['name'] + ' references missing parameter ' + material['shader'] + '.' + param['name'])
    return socket


def add_material_editing_note(node_tree, shader_node):
    text = bpy.data.texts.get('MDB Editing Notes')
    if text is None:
        text = bpy.data.texts.new('MDB Editing Notes')
        text.write(MDB_EDITING_NOTES)

    note = node_tree.nodes.new('NodeFrame')
    note.name = 'MDB Editing Notes'
    note.label = 'MDB Editing Notes — preview links vs exported data'
    note.text = text
    note.shrink = False
    note.label_size = 18
    note.width = 520
    note.height = 230
    note.location[0] = shader_node.location[0] - 260
    note.location[1] = shader_node.location[1] + 420
    note.use_custom_color = True
    note.color = (0.12, 0.22, 0.32)
    note.select = False


def ensure_normal_unswizzle_group():
    existing = bpy.data.node_groups.get('Normal Unswizzle')
    if existing is not None:
        return existing

    spacing = 160
    node_tree = bpy.data.node_groups.new(
        'Normal Unswizzle',
        'ShaderNodeTree',
    )
    group_inputs = node_tree.nodes.new('NodeGroupInput')
    group_inputs.location[0] = spacing * 0
    new_socket(node_tree, 'Color', 'INPUT', 'NodeSocketColor')
    new_socket(node_tree, 'Alpha', 'INPUT', 'NodeSocketFloat')

    split_rgb = node_tree.nodes.new('ShaderNodeSeparateRGB')
    split_rgb.location[0] = spacing * 1
    node_tree.links.new(
        split_rgb.inputs['Image'],
        group_inputs.outputs['Color'],
    )

    value_r = node_tree.nodes.new('ShaderNodeMath')
    value_r.location[0] = spacing * 2
    value_r.operation = 'MULTIPLY'
    node_tree.links.new(value_r.inputs[0], split_rgb.outputs['R'])
    node_tree.links.new(value_r.inputs[1], group_inputs.outputs['Alpha'])

    multiply_r = node_tree.nodes.new('ShaderNodeMath')
    multiply_r.location[0] = spacing * 3
    multiply_r.operation = 'MULTIPLY_ADD'
    node_tree.links.new(multiply_r.inputs[0], value_r.outputs['Value'])
    multiply_r.inputs[1].default_value = 2.0
    multiply_r.inputs[2].default_value = -1.0

    multiply_g = node_tree.nodes.new('ShaderNodeMath')
    multiply_g.location[0] = spacing * 3
    multiply_g.location[1] -= 170
    multiply_g.operation = 'MULTIPLY_ADD'
    node_tree.links.new(multiply_g.inputs[0], split_rgb.outputs['G'])
    multiply_g.inputs[1].default_value = 2.0
    multiply_g.inputs[2].default_value = -1.0

    squared_r = node_tree.nodes.new('ShaderNodeMath')
    squared_r.location[0] = spacing * 4
    squared_r.operation = 'MULTIPLY'
    node_tree.links.new(squared_r.inputs[0], multiply_r.outputs['Value'])
    node_tree.links.new(squared_r.inputs[1], multiply_r.outputs['Value'])

    squared_g = node_tree.nodes.new('ShaderNodeMath')
    squared_g.location[0] = spacing * 4
    squared_g.location[1] -= 170
    squared_g.operation = 'MULTIPLY'
    node_tree.links.new(squared_g.inputs[0], multiply_g.outputs['Value'])
    node_tree.links.new(squared_g.inputs[1], multiply_g.outputs['Value'])

    remaining_r = node_tree.nodes.new('ShaderNodeMath')
    remaining_r.location[0] = spacing * 5
    remaining_r.operation = 'SUBTRACT'
    remaining_r.inputs[0].default_value = 1.0
    node_tree.links.new(remaining_r.inputs[1], squared_r.outputs['Value'])

    remaining_g = node_tree.nodes.new('ShaderNodeMath')
    remaining_g.location[0] = spacing * 6
    remaining_g.operation = 'SUBTRACT'
    node_tree.links.new(remaining_g.inputs[0], remaining_r.outputs['Value'])
    node_tree.links.new(remaining_g.inputs[1], squared_g.outputs['Value'])

    reconstructed_b = node_tree.nodes.new('ShaderNodeMath')
    reconstructed_b.location[0] = spacing * 7
    reconstructed_b.operation = 'SQRT'
    node_tree.links.new(
        reconstructed_b.inputs[0],
        remaining_g.outputs['Value'],
    )

    packed_b = node_tree.nodes.new('ShaderNodeMath')
    packed_b.location[0] = spacing * 8
    packed_b.operation = 'MULTIPLY_ADD'
    node_tree.links.new(packed_b.inputs[0], reconstructed_b.outputs['Value'])
    packed_b.inputs[1].default_value = 0.5
    packed_b.inputs[2].default_value = 0.5

    flipped_g = node_tree.nodes.new('ShaderNodeMath')
    flipped_g.location[0] = spacing * 9
    flipped_g.operation = 'SUBTRACT'
    flipped_g.inputs[0].default_value = 1.0
    node_tree.links.new(flipped_g.inputs[1], split_rgb.outputs['G'])

    combine_rgb = node_tree.nodes.new('ShaderNodeCombineRGB')
    combine_rgb.location[0] = spacing * 10
    node_tree.links.new(combine_rgb.inputs['R'], value_r.outputs['Value'])
    node_tree.links.new(combine_rgb.inputs['G'], flipped_g.outputs['Value'])
    node_tree.links.new(combine_rgb.inputs['B'], packed_b.outputs['Value'])

    group_outputs = node_tree.nodes.new('NodeGroupOutput')
    group_outputs.location[0] = spacing * 11
    new_socket(node_tree, 'Color', 'OUTPUT', 'NodeSocketColor')
    node_tree.links.new(
        group_outputs.inputs['Color'],
        combine_rgb.outputs['Image'],
    )
    return node_tree


def set_material_parameter_values(shader_node, mdb_material):
    for parameter in mdb_material['params']:
        name = parameter['name']
        size = parameter['size']
        if size == 1:
            socket = warnparam(
                shader_node.inputs.get(name),
                mdb_material,
                parameter,
            )
            if socket is not None:
                socket.default_value = parameter['val0']
        elif size == 2:
            socket_x = warnparam(
                shader_node.inputs.get(name + '_x'),
                mdb_material,
                parameter,
            )
            if socket_x is not None:
                shader_node.inputs[name + '_y'].default_value = parameter['val1']
                socket_x.default_value = parameter['val0']
        elif size >= 3:
            color_socket = warnparam(
                shader_node.inputs.get(name),
                mdb_material,
                parameter,
            )
            if color_socket is not None:
                color_socket.default_value = (
                    parameter['val0'],
                    parameter['val1'],
                    parameter['val2'],
                    1,
                )
                alpha_socket = shader_node.inputs.get(name + '_alpha')
                if alpha_socket is not None:
                    alpha_socket.default_value = parameter['val3']


def load_texture_image(filepath, filename, slot_name, texture_cache):
    if filename in texture_cache:
        return texture_cache[filename]

    model_directory = os.path.dirname(filepath)
    candidates = (
        os.path.join(model_directory, '..', 'HD-TEXTURE', filename),
        os.path.join(model_directory, '..', 'TEXTURE', filename),
    )
    image = None
    last_error = None
    for candidate in candidates:
        try:
            image = bpy.data.images.load(candidate)
            break
        except RuntimeError as error:
            last_error = error

    if image is None:
        print(f"Failed to load texture '{filename}': {last_error}")
        return None

    texture_cache[filename] = image
    image.alpha_mode = 'CHANNEL_PACKED'
    if 'albedo' not in slot_name and 'diffuse' not in slot_name:
        image.colorspace_settings.name = 'Non-Color'
    return image


def connect_texture_preview(
    material,
    shader_node,
    shader,
    texture_node,
    slot_name,
):
    node_tree = material.node_tree
    color_socket = shader_node.inputs.get(slot_name)
    if color_socket is None:
        return

    if slot_name in ('normal', 'damage_normal'):
        unswizzle_node = node_tree.nodes.new('ShaderNodeGroup')
        unswizzle_node.location[0] = shader_node.location[0] - 350
        unswizzle_node.node_tree = bpy.data.node_groups.get(
            'Normal Unswizzle',
        )
        unswizzle_node.show_options = False
        node_tree.links.new(
            unswizzle_node.inputs['Color'],
            texture_node.outputs['Color'],
        )
        node_tree.links.new(
            unswizzle_node.inputs['Alpha'],
            texture_node.outputs['Alpha'],
        )

        normal_map = node_tree.nodes.new('ShaderNodeNormalMap')
        normal_map.location[0] = shader_node.location[0] - 200
        node_tree.links.new(
            normal_map.inputs['Color'],
            unswizzle_node.outputs['Color'],
        )
        node_tree.links.new(color_socket, normal_map.outputs['Normal'])
    else:
        node_tree.links.new(color_socket, texture_node.outputs['Color'])
        alpha_socket = shader_node.inputs.get(slot_name + '_alpha')
        if alpha_socket is not None:
            node_tree.links.new(alpha_socket, texture_node.outputs['Alpha'])

    mapping = shader.param_map.get(slot_name)
    if mapping is not None and len(mapping) >= 3:
        uv_map = node_tree.nodes.new('ShaderNodeUVMap')
        uv_map.location[0] = texture_node.location[0] - 200
        uv_map.location[1] = texture_node.location[1] - 200
        uv_map.uv_map = 'UVMap' + str(mapping[2] + 1)
        node_tree.links.new(texture_node.inputs['Vector'], uv_map.outputs['UV'])


def add_material_texture(
    material,
    shader_node,
    shader,
    mdb,
    texture,
    binding_index,
    filepath,
    texture_cache,
):
    slot_name = texture['map']
    texture_record = mdb['textures'][texture['texture']]
    filename = texture_record['filename']
    texture_node = material.node_tree.nodes.new('ShaderNodeTexImage')
    texture_node.name = f"MDB Texture {binding_index}: {slot_name}"
    texture_node.label = f"{slot_name}: {filename}"
    texture_node['mdb_texture_binding'] = binding_index
    texture_node['mdb_texture_index'] = texture['texture']
    texture_node['mdb_texture_name'] = texture_record['name']
    texture_node['mdb_texture_filename'] = filename
    texture_node['mdb_texture_slot'] = slot_name
    texture_node['mdb_sampler_flags'] = texture['sampler_flags']
    texture_node['mdb_filter'] = texture['filter']
    texture_node['mdb_address_u'] = texture['address_u']
    texture_node['mdb_address_v'] = texture['address_v']
    texture_node['mdb_address_w'] = texture['address_w']
    texture_node['mdb_max_anisotropy'] = texture['max_anisotropy']
    texture_node['mdb_min_lod'] = texture['min_lod']
    texture_node['mdb_max_lod'] = texture['max_lod']
    texture_node['mdb_lod_bias'] = texture['lod_bias']
    texture_node.image = load_texture_image(
        filepath,
        filename,
        slot_name,
        texture_cache,
    )
    texture_node.location[0] = shader_node.location[0] - 700 + binding_index * 40
    texture_node.location[1] = shader_node.location[1] - binding_index * 40
    connect_texture_preview(
        material,
        shader_node,
        shader,
        texture_node,
        slot_name,
    )


def tag_mdb_source(data_block, source_id, source_path):
    data_block[SOURCE_ID_PROPERTY] = source_id
    data_block[SOURCE_PATH_PROPERTY] = source_path


def create_material(
    mdb,
    mdb_material,
    filepath,
    texture_cache,
    ignore_errors,
    source_id,
    source_path,
):
    material = bpy.data.materials.new(mdb_material['name'])
    tag_mdb_source(material, source_id, source_path)
    material['draw_priority'] = mdb_material['draw_priority']
    material['render_queue_class'] = mdb_material['render_queue_class']
    material['render_participation_flags'] = (
        mdb_material['render_participation_flags']
    )
    material['mdb_name'] = mdb_material['name']
    material['mdb_shader_name'] = mdb_material['shader']
    material['mdb_material_index'] = mdb_material['index']
    material['mdb_texture_table'] = json.dumps(mdb['textures'])

    shader_name = mdb_material['shader']
    lower_shader_name = shader_name.lower()
    if lower_shader_name.endswith(('_alpha', '_hair')):
        material.blend_method = 'HASHED'
    elif lower_shader_name.endswith('_clip'):
        material.blend_method = 'CLIP'

    material.use_nodes = True
    node_tree = material.node_tree
    default_bsdf = next(
        (node for node in node_tree.nodes if node.type == 'BSDF_PRINCIPLED'),
        None,
    )
    if default_bsdf is not None:
        node_tree.nodes.remove(default_bsdf)

    shader = get_shader(shader_name, ignore_errors, mdb_material)
    if shader.has_alpha and material.blend_method == 'OPAQUE':
        material.blend_method = 'HASHED'

    material_output = next(
        node for node in node_tree.nodes
        if node.type == 'OUTPUT_MATERIAL'
    )
    shader_node = node_tree.nodes.new('ShaderNodeGroup')
    shader_node.node_tree = shader.shader_tree
    shader_node['mdb_shader_name'] = shader_name
    shader_node['mdb_parameters'] = json.dumps(mdb_material['params'])
    shader_node.show_options = False
    shader_node.width = 240
    shader_node.location[1] = material_output.location[1]
    node_tree.links.new(
        material_output.inputs['Surface'],
        shader_node.outputs['Surface'],
    )
    add_material_editing_note(node_tree, shader_node)
    set_material_parameter_values(shader_node, mdb_material)

    for binding_index, texture in enumerate(mdb_material['textures']):
        add_material_texture(
            material,
            shader_node,
            shader,
            mdb,
            texture,
            binding_index,
            filepath,
            texture_cache,
        )

    for node in node_tree.nodes:
        node.select = False
    return material


def create_materials(mdb, filepath, ignore_errors, source_id, source_path):
    texture_cache = {}
    return [
        create_material(
            mdb,
            mdb_material,
            filepath,
            texture_cache,
            ignore_errors,
            source_id,
            source_path,
        )
        for mdb_material in mdb['materials']
    ]


def create_armature(mdb, filepath, context, source_id, source_path):
    armature = bpy.data.armatures.new('Armature')
    tag_mdb_source(armature, source_id, source_path)
    armature_object = bpy.data.objects.new(
        os.path.splitext(os.path.basename(filepath))[0],
        armature,
    )
    tag_mdb_source(armature_object, source_id, source_path)
    context.scene.collection.objects.link(armature_object)
    context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    edit_bones = armature.edit_bones
    created_bones = []
    for mdb_bone in mdb['bones']:
        bone = edit_bones.new(mdb_bone['name'])
        bone.length = 0.25
        if mdb_bone['parent'] >= 0:
            bone.parent = created_bones[mdb_bone['parent']]
            bone.matrix = bone.parent.matrix @ mdb_bone['matrix_local']
        else:
            bone.matrix = bone_up_Y @ mdb_bone['matrix_local']
        bone['participation_metadata'] = mdb_bone['participation_metadata']
        bone['semantic_role'] = mdb_bone['semantic_role']
        bone['normalized_bone_flag'] = mdb_bone['normalized_bone_flag']
        bone['bounds_half_size'] = mdb_bone['bounds_half_size']
        bone['bounds_center'] = mdb_bone['bounds_center']
        created_bones.append(bone)

    bpy.ops.object.mode_set(mode='OBJECT')
    return armature_object


def create_mesh_geometry(mesh, mdb_mesh):
    vertices = mdb_mesh['vertices']
    faces = [
        tuple(mdb_mesh['indices'][index:index + 3])
        for index in range(0, len(mdb_mesh['indices']), 3)
    ]
    positions = [
        (
            vertex['position0'][0],
            -vertex['position0'][2],
            vertex['position0'][1],
        )
        for vertex in vertices
    ]
    mesh.from_pydata(positions, [], faces)
    mesh.polygons.foreach_set('use_smooth', (True,) * len(faces))


def apply_mesh_normals(mesh, vertices, object_name):
    if not vertices or 'normal0' not in vertices[0]:
        print(f'No normals found for mesh {object_name}')
        return

    normals = []
    for vertex in vertices:
        normal = vertex['normal0'].astype(float)
        magnitude = np.sqrt(sum(component * component for component in normal[:3]))
        if magnitude > 0:
            normal /= magnitude
            normals.append((normal[0], -normal[2], normal[1]))
        else:
            normals.append((0.0, 0.0, 0.0))
    mesh.normals_split_custom_set_from_vertices(normals)
    if bpy.app.version < (4, 1, 0):
        mesh.use_auto_smooth = True


def apply_mesh_uv_maps(mesh, vertices):
    if not vertices:
        return
    for channel in range(4):
        coordinate_key = f'texcoord{channel}'
        if coordinate_key not in vertices[0]:
            continue
        uv_map = mesh.uv_layers.new(
            name='UVMap' + ('' if channel == 0 else str(channel + 1)),
        )
        for face in mesh.polygons:
            for vertex_index, loop_index in zip(
                face.vertices,
                face.loop_indices,
            ):
                texcoord = vertices[vertex_index][coordinate_key]
                uv_map.data[loop_index].uv[0] = texcoord[0]
                uv_map.data[loop_index].uv[1] = 1.0 - texcoord[1]


def apply_vertex_groups(mesh_object, vertices, mdb_bones, object_name):
    if not vertices or 'blendweight0' not in vertices[0]:
        print(f'No blend weights found for mesh {object_name}')
        return

    groups = [
        mesh_object.vertex_groups.new(name=bone['name'])
        for bone in mdb_bones
    ]
    for vertex_index, vertex in enumerate(vertices):
        for influence_index in range(4):
            weight = vertex['blendweight0'][influence_index]
            if weight == 0:
                continue
            bone_index = vertex['blendindices0'][influence_index]
            groups[bone_index].add([vertex_index], weight, 'ADD')


def create_mesh_object(
    context,
    mdb,
    mdb_object,
    mdb_mesh,
    materials,
    armature_object,
    container,
    source_id,
    source_path,
):
    object_name = mdb_object['name']
    vertices = mdb_mesh['vertices']
    mesh = bpy.data.meshes.new(f'{object_name}_Data')
    tag_mdb_source(mesh, source_id, source_path)
    mesh_object = bpy.data.objects.new(object_name, mesh)
    tag_mdb_source(mesh_object, source_id, source_path)
    create_mesh_geometry(mesh, mdb_mesh)
    apply_mesh_normals(mesh, vertices, object_name)
    apply_mesh_uv_maps(mesh, vertices)
    apply_vertex_groups(mesh_object, vertices, mdb['bones'], object_name)

    armature_modifier = mesh_object.modifiers.new('Armature', 'ARMATURE')
    armature_modifier.object = armature_object
    if mdb_mesh['material_index'] != -1:
        mesh.materials.append(materials[mdb_mesh['material_index']])

    mesh.update()
    context.scene.collection.objects.link(mesh_object)
    mesh_object.parent = container
    return mesh_object


def create_mesh_objects(
    context,
    mdb,
    materials,
    armature_object,
    source_id,
    source_path,
):
    for mdb_object in mdb['objects']:
        object_name = mdb_object['name']
        container = bpy.data.objects.new(object_name, None)
        tag_mdb_source(container, source_id, source_path)
        container['mdb_name'] = object_name
        context.scene.collection.objects.link(container)
        for mdb_mesh in mdb_object['meshes']:
            create_mesh_object(
                context,
                mdb,
                mdb_object,
                mdb_mesh,
                materials,
                armature_object,
                container,
                source_id,
                source_path,
            )


# Main function
def load(operator, context, filepath='', **kwargs):
    del kwargs
    settings = ImportSettings(
        ignore_errors=operator.option_ignore_errors,
        override_version=operator.option_override_version,
    )
    try:
        with open(filepath, 'rb') as stream:
            mdb = parse_mdb(
                stream,
                override_version=settings.override_version,
            )
    except (OSError, MdbFormatError) as error:
        if hasattr(operator, 'report'):
            operator.report({'ERROR'}, str(error))
        print(f'ERROR: {error}')
        return {'CANCELLED'}

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    source_id = uuid.uuid4().hex
    source_path = os.path.abspath(filepath)
    ensure_normal_unswizzle_group()
    materials = create_materials(
        mdb,
        filepath,
        settings.ignore_errors,
        source_id,
        source_path,
    )

    armature_obj = create_armature(
        mdb,
        filepath,
        context,
        source_id,
        source_path,
    )

    create_mesh_objects(
        context,
        mdb,
        materials,
        armature_obj,
        source_id,
        source_path,
    )
    context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    return {'FINISHED'}
