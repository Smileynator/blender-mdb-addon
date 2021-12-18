# MDB loader for Blender

import os
import bpy
import mathutils
import numpy as np

from struct import pack, unpack

from .shader import Shader, get_shader


# Read helper functions
def read_ushort(file):
    return unpack('<H', file.read(2))[0]


def read_int(file):
    return unpack('<i', file.read(4))[0]


def read_uint(file):
    return unpack('<I', file.read(4))[0]


def read_float(file):
    return unpack('<f', file.read(4))[0]


def read_str(file):
    data = bytearray()
    while True:
        char = file.read(1)
        if char == b'\0':
            break
        data.extend(char)
    return data.decode('shift-jis')


def read_wstr(file):
    data = bytearray()
    while True:
        char = file.read(2)
        if char == b'\0\0':
            break
        data.extend(char)
    return data.decode('utf-16')


def read_matrix(file):
    # TODO: Possibly wrong order?
    mat = mathutils.Matrix()
    for y in range(4):
        for x in range(4):
            mat[y][x] = read_float(file)
    return mat

# Parsing functions
def parse_names(f, count, offset):
    names = []
    f.seek(offset)
    for i in range(count):
        base = f.tell()
        str_offset = read_uint(f)
        next = f.tell()
        assert next - base == 4

        if str_offset != 0:
            f.seek(base+str_offset)
            names.append(read_wstr(f))
            f.seek(next)
        else:
            names.append(None)
    return names


def parse_bones(f, count, offset):
    bones = []
    f.seek(offset)
    for i in range(count):
        bone = {}
        base = f.tell()
        # TODO
        bone['index'] = read_uint(f)
        bone['parent'] = read_int(f)
        bone['unk1'] = read_int(f)
        bone['unk2'] = read_int(f)
        bone['index2'] = read_uint(f) # Unused?
        bone['unk3'] = read_uint(f)
        bone['unk4'] = f.read(1)[0]
        bone['unk5'] = f.read(1)[0]
        bone['unk6'] = f.read(1)[0] == 1
        f.read(5) # Always zero

        bone['mat1'] = read_matrix(f)
        bone['mat2'] = read_matrix(f)

        bone['unk7'] = read_float(f)
        bone['unk8'] = read_float(f)
        bone['unk9'] = read_float(f)
        f.read(4) # Always 1.0

        bone['unk10'] = read_float(f)
        bone['unk11'] = read_float(f)
        bone['unk12'] = read_float(f)
        f.read(4) # Always 1.0
        next = f.tell()
        assert next - base == 192

        f.seek(next)
        bones.append(bone)
    return bones


def parse_textures(f, count, offset):
    textures = []
    f.seek(offset)
    for i in range(count):
        texture = {}
        base = f.tell()
        texture['index'] = read_uint(f)
        name = read_uint(f)
        filename = read_uint(f)
        f.read(4) # Always zero
        next = f.tell()
        assert next - base == 16

        f.seek(base+name)
        texture['name'] = read_wstr(f)
        f.seek(base+filename)
        texture['filename'] = read_wstr(f)

        f.seek(next)
        textures.append(texture)
    return textures


def parse_mat_param(f, count, offset):
    mat_params = []
    f.seek(offset)
    for i in range(count):
        mat_param = {}
        base = f.tell()
        mat_param['val0'] = read_float(f)
        mat_param['val1'] = read_float(f)
        mat_param['val2'] = read_float(f)
        mat_param['val3'] = read_float(f)
        f.read(8) # Always zero
        name = read_uint(f)
        mat_param['unk'] = f.read(1)[0]
        mat_param['size'] = f.read(1)[0]
        f.read(2) # Always zero
        next = f.tell()
        assert next - base == 32

        f.seek(base+name)
        mat_param['name'] = read_str(f)

        f.seek(next)
        mat_params.append(mat_param)
    return mat_params


def parse_mat_txr(f, count, offset):
    mat_txrs = []
    f.seek(offset)
    for i in range(count):
        mat_txr = {}
        base = f.tell()
        mat_txr['texture'] = read_uint(f)
        string = read_uint(f)
        mat_txr['unk0'] = read_ushort(f)
        mat_txr['unk1'] = read_ushort(f)
        f.read(12) # Always zero
        mat_txr['unk2'] = read_uint(f)
        next = f.tell()
        assert next - base == 28

        f.seek(base+string)
        mat_txr['map'] = read_str(f)

        f.seek(next)
        mat_txrs.append(mat_txr)
    return mat_txrs


def parse_materials(f, count, offset, name_table):
    materials = []
    f.seek(offset)
    for i in range(count):
        material = {}
        base = f.tell()
        material['index'] = read_ushort(f)
        material['unk0'] = read_ushort(f)
        material_name = read_uint(f)
        shader = read_uint(f)
        param_offset = read_uint(f)
        param_count = read_uint(f)
        txr_offset = read_uint(f)
        txr_count = read_uint(f)
        material['unk1'] = read_uint(f)
        next = f.tell()
        assert next - base == 32

        material['name'] = name_table[material_name]
        f.seek(base+shader)
        material['shader'] = read_wstr(f)

        material['params'] = parse_mat_param(f, param_count, base+param_offset)
        material['textures'] = parse_mat_txr(f, txr_count, base+txr_offset)

        f.seek(next)
        materials.append(material)
    return materials


def parse_vertex_layout(f, count, offset):
    layout = []
    f.seek(offset)
    for i in range(count):
        element = {}
        base = f.tell()
        element['type'] = read_uint(f)
        element['offset'] = read_uint(f)
        element['channel'] = read_uint(f)
        name = read_uint(f)
        next = f.tell()
        assert next - base == 16

        f.seek(base+name)
        element['name'] = read_str(f)

        f.seek(next)
        layout.append(element)
    return layout


def parse_indices(f, count, offset):
    indices = []
    f.seek(offset)
    for i in range(count):
        indices.append(read_ushort(f))
    return indices


def parse_vertices(f, count, offset, layout, vertex_size):
    vertices = []
    f.seek(offset)
    for i in range(count):
        vertex = {}
        for j in range(len(layout)):
            elem = layout[j]
            array = []
            type = elem['type']
            if type == 1: #float4
                array = unpack("ffff", f.read(16))
            elif type == 4: #float3
                array = unpack("fff", f.read(12))
            elif type == 7: #half4
                array = np.frombuffer(f.read(8), dtype=np.half)
            elif type == 12: #float2
                array = unpack("ff", f.read(8))
            elif type == 21: #ubyte4
                array = unpack("BBBB", f.read(4))
            else:
                print("Unknown vertex layout type: " + str(type))
                if j < len(layout) - 1:
                    f.seek(layout[j+1]['offset'] - elem['offset'])
                else:
                    f.seek(vertex_size - elem['offset'])
            vertex[elem['name'] + str(elem['channel'])] = array
        vertices.append(vertex)
    return vertices


def parse_meshes(f, count, offset):
    meshes = []
    f.seek(offset)
    for i in range(count):
        mesh = {}
        base = f.tell()
        mesh['unk0'] = read_uint(f)
        mesh['material'] = read_int(f)
        f.read(4) # Always zero
        layout_offset = read_uint(f)
        mesh['vertex_size'] = read_ushort(f)
        layout_count = read_ushort(f)
        vertex_count = read_uint(f)
        mesh['index'] = read_uint(f)
        vertex_offset = read_uint(f)
        indice_count = read_uint(f)
        indice_offset = read_uint(f)
        next = f.tell()
        assert next - base == 40

        mesh['layout'] = parse_vertex_layout(f, layout_count, base+layout_offset)
        mesh['indices'] = parse_indices(f, indice_count, base+indice_offset)
        mesh['vertices'] = parse_vertices(f, vertex_count, base+vertex_offset, mesh['layout'], mesh['vertex_size'])

        f.seek(next)
        meshes.append(mesh)
    return meshes


def parse_objects(f, count, offset, name_table):
    objects = []
    f.seek(offset)
    for i in range(count):
        object = {}
        base = f.tell()
        object['index'] = read_uint(f)
        name = read_uint(f)
        mesh_count = read_uint(f)
        mesh_offset = read_uint(f)
        next = f.tell()
        assert next - base == 16

        object['name'] = name_table[name]
        object['meshes'] = parse_meshes(f, mesh_count, base+mesh_offset)

        f.seek(next)
        objects.append(object)
    return objects


def parse_mdb(f):
    mdb = {}
    f.seek(0)
    magic = f.read(4)
    version = read_uint(f)
    name_count = read_uint(f)
    name_offset = read_uint(f)
    bone_count = read_uint(f)
    bone_offset = read_uint(f)
    object_count = read_uint(f)
    object_offset = read_uint(f)
    material_count = read_uint(f)
    material_offset = read_uint(f)
    texture_count = read_uint(f)
    texture_offset = read_uint(f)

    assert magic == b'MDB0'
    assert version == 0x14

    mdb['names'] = parse_names(f, name_count, name_offset)
    mdb['bones'] = parse_bones(f, bone_count, bone_offset)
    mdb['textures'] = parse_textures(f, texture_count, texture_offset)
    mdb['materials'] = parse_materials(f, material_count, material_offset, mdb['names'])
    mdb['objects'] = parse_objects(f, object_count, object_offset, mdb['names'])
    return mdb


def warnparam(input, material, param):
    if input is None:
        print('Warning: Material ' + material['name'] + ' references missing parameter ' + material['shader'] + '.' + param['name'])
    return input


# Main function
def load(operator, context, filepath='', **kwargs):
    # Parse MDB
    with open(filepath, 'rb') as f:
        mdb = parse_mdb(f)

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    # Texture cache
    textures = {}

    # Create materials
    materials = []
    for mdb_material in mdb['materials']:
        lshader = mdb_material['shader'].lower()
        material = bpy.data.materials.new(mdb_material['name'])
        if lshader.endswith('_alpha') or lshader.endswith('_hair'):
            material.blend_method = 'HASHED'
        material.use_nodes = True
        mat_nodes = material.node_tree
        bsdf = mat_nodes.nodes['Principled BSDF']
        mat_nodes.nodes.remove(bsdf)
        unhandled = 0

        mat_out = mat_nodes.nodes['Material Output']
        shader_node = material.node_tree.nodes.new('ShaderNodeGroup')
        shader = get_shader(mdb_material['shader'])
        shader_node.node_tree = shader.shader_tree
        shader_node.show_options = False
        shader_node.width = 240
        shader_node.location[1] = mat_out.location[1]
        mat_nodes.links.new(mat_out.inputs['Surface'], shader_node.outputs['Surface'])

        # Set up material parameters
        for param in mdb_material['params']:
            if param['size'] == 1:
                input_node = warnparam(shader_node.inputs.get(param['name']), mdb_material, param)
                if input_node is not None:
                    input_node.default_value = param['val0']
            elif param['size'] == 2:
                input_x = warnparam(shader_node.inputs.get(param['name'] + '_x'), mdb_material, param)
                if input_x is not None:
                    input_y = shader_node.inputs.get(param['name'] + '_y')
                    input_x.default_value = param['val0']
                    input_y.default_value = param['val1']
            elif param['size'] == 4:
                input_col = warnparam(shader_node.inputs.get(param['name']), mdb_material, param)
                if input_col is not None:
                    input_alpha = shader_node.inputs.get(param['name'] + '_alpha')
                    input_col.default_value = (param['val0'], param['val1'], param['val2'], 1)
                    # It's okay for alpha to be missing, there are no parameters of size 3
                    if input_alpha is not None:
                        input_alpha.default_value = param['val3']

        # Add all material textures
        for texture in mdb_material['textures']:
            txr_map = texture['map']
            texImage = mat_nodes.nodes.new('ShaderNodeTexImage')
            filename = mdb['textures'][texture['texture']]['filename']
            if filename in textures:
                texImage.image = textures[filename]
            else:
                try:
                    image = bpy.data.images.load(os.path.join(os.path.dirname(filepath), '..', 'HD-TEXTURE', filename))
                    texImage.image = image
                    textures[filename] = image
                    if 'albedo' not in txr_map and 'diffuse' not in txr_map:
                        image.colorspace_settings.name = 'Non-Color'
                    if txr_map == 'normal' or txr_map == 'damage_normal':
                        np_pxl = np.empty(len(image.pixels), dtype=np.float32)
                        image.pixels.foreach_get(np_pxl)
                        np_pxl.shape = (len(image.pixels) // image.channels, image.channels)
                        np_pxl[:, 0] *= np_pxl[:, 3] # Reconstruct X
                        np_pxl[:, 1] = 1 - np_pxl[:, 1] # Flip Y (DX -> GL)
                        np_pxl[:, 2] = (np.sqrt(1 - np.clip(np.square(np_pxl[:, 0] * 2. - 1.) + np.square(np_pxl[:, 1] * 2. - 1.), 0., 1.)) + 1.) * .5 # Reconstruct Z
                        np_pxl[:, 3] = 1 # Blank Alpha
                        np_pxl.shape = (len(image.pixels))

                        # I do not understand why, but setting, packing, and setting again, makes the changes actually apply.
                        image.pixels.foreach_set(np_pxl)
                        image.pack()
                        image.pixels.foreach_set(np_pxl)
                except RuntimeError as e: # Ignore texture import error
                    print(e)

            texImage.location[0] = shader_node.location[0] - 700 + unhandled * 40
            texImage.location[1] = shader_node.location[1] - unhandled * 40
            unhandled += 1
            input_col = shader_node.inputs.get(txr_map)
            if input_col is not None:
                if txr_map == 'normal' or txr_map == 'damage_normal':
                    normalMap = mat_nodes.nodes.new('ShaderNodeNormalMap')
                    normalMap.location[0] = shader_node.location[0] - 200
                    mat_nodes.links.new(normalMap.inputs['Color'], texImage.outputs['Color'])
                    mat_nodes.links.new(input_col, normalMap.outputs['Normal'])
                else:
                    input_alpha = shader_node.inputs.get(txr_map + '_alpha')
                    mat_nodes.links.new(input_col, texImage.outputs['Color'])
                    if input_alpha is not None:
                        mat_nodes.links.new(input_alpha, texImage.outputs['Alpha'])
                param = shader.param_map[txr_map]
                if len(param) >= 3:
                    uvmap = mat_nodes.nodes.new('ShaderNodeUVMap')
                    uvmap.location[0] = texImage.location[0] - 200
                    uvmap.location[1] = texImage.location[1] - 200
                    uvmap.uv_map = 'UVMap' + str(param[2]+1)
                    mat_nodes.links.new(texImage.inputs['Vector'], uvmap.outputs['UV'])

        # Deselect all nodes
        for node in mat_nodes.nodes:
            node.select = False

        materials.append(material)

    # Add armature and bones
    armature = bpy.data.armatures.new('Armature')
    armature_obj = bpy.data.objects.new(os.path.splitext(os.path.basename(filename))[0], armature)
    context.scene.collection.objects.link(armature_obj)

    context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    edit_bones = armature.edit_bones
    bones = []
    for mdb_bone in mdb['bones']:
        bone = edit_bones.new(mdb['names'][mdb_bone['index']])
        bone.tail.z = 0.2
        bones.append(bone)
        if mdb_bone['parent'] >= 0:
            bone.parent = bones[mdb_bone['parent']]
        # TODO: Everything.
    bpy.ops.object.mode_set(mode='OBJECT')

    # Add meshes
    for object in mdb['objects']:
        name = object['name']
        empty = bpy.data.objects.new(name, None)
        context.scene.collection.objects.link(empty)
        for mdb_mesh in object['meshes']:
            vertices = mdb_mesh['vertices']

            # Read indices
            faces = []
            indices = mdb_mesh['indices']
            for i in range(0, len(indices), 3):
                faces.append((indices[i+0], indices[i+1], indices[i+2]))

            # Read vertices
            vertex = []
            for vert in vertices:
                x = vert['position0'][0]
                y = vert['position0'][1]
                z = vert['position0'][2]
                vertex.append((x, -z, y))

            # Add basic mesh
            mesh = bpy.data.meshes.new('%s_Data' % name)
            mesh_obj = bpy.data.objects.new(name, mesh)
            mesh_obj.data = mesh

            mesh.from_pydata(vertex, [], faces)
            mesh.polygons.foreach_set('use_smooth', (True,)*len(faces))

            # Read normals
            if 'normal0' in vertices[0]:
                normals = []
                for vert in vertices:
                    x = vert['normal0'][0]
                    y = vert['normal0'][1]
                    z = vert['normal0'][2]
                    normals.append((x, -z, y))
                mesh.normals_split_custom_set_from_vertices(normals)
                mesh.use_auto_smooth = True # Enable custom normals

            # TODO: Binormals and tangents?

            # Add UV map
            for i in range(4):
                coordstr = 'texcoord' + str(i)
                if coordstr in vertices[0]:
                    uvmap = mesh.uv_layers.new(name='UVMap' + ('' if i == 0 else str(i+1)))
                    for face in mesh.polygons:
                        for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                            texcoord = vertices[vert_idx][coordstr]
                            uvmap.data[loop_idx].uv[0] = texcoord[0]
                            uvmap.data[loop_idx].uv[1] = 1.0 - texcoord[1]

            # Add vertex groups
            if 'BLENDWEIGHT0' in vertices[0]:
                groups = []
                for n in range(len(mdb['bones'])):
                    groups.append(mesh_obj.vertex_groups.new(name=mdb['names'][n])) # TODO: Bone name
                for i, vert in enumerate(vertices):
                    for n in range(4):
                        if vert['BLENDWEIGHT0'][n] != 0:
                            groups[vert['BLENDINDICES0'][n]].add([i], vert['BLENDWEIGHT0'][n], 'ADD')

            mod = mesh_obj.modifiers.new("Armature", 'ARMATURE')
            mod.object = armature_obj

            # Assign material
            if mdb_mesh['material'] != -1:
                mesh.materials.append(materials[mdb_mesh['material']])

            mesh.update()

            context.scene.collection.objects.link(mesh_obj)
            mesh_obj.parent = empty
    return {'FINISHED'}
