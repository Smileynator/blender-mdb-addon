# MDB loader for Blender

import os
import bpy
import mathutils

from struct import pack, unpack


# Helper functions
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


def read_half(file):
    return f16_to_f32(unpack('<h', file.read(2))[0])


def f16_to_f32(float16):
    s = int((float16 >> 15) & 0b1)  # sign
    e = int((float16 >> 10) & 0x0000001f)  # exponent
    f = int(float16 & 0x000003ff)  # fraction

    if e == 0 and f != 0:
        while not (f & 0x00000400):
            f = f << 1
            e -= 1
        e += 1
        f &= ~0x00000400

    if (not (e == 0 and f == 0)) and e != 31:
        e = e + (127 - 15)
        e = e << 23

    elif (e == 31):
        e = 0x7f800000

    if not ((e == 0 or e == 31) and f == 0):
        f = f << 13

    s = (s << 31)

    int_var = int(s | e | f)
    float_var = unpack('<f', pack('<I', int_var))[0]

    return float_var


def read_matrix(file):
    # TODO: Possibly wrong order?
    mat = mathutils.Matrix()
    for y in range(4):
        for x in range(4):
            mat[y][x] = read_float(file)
    return mat

# Main functions
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


def parse_mat_sub1(f, count, offset):
    mat_sub1s = []
    f.seek(offset)
    for i in range(count):
        mat_sub1 = {}
        base = f.tell()
        mat_sub1['unk0'] = read_float(f)
        mat_sub1['unk1'] = read_float(f)
        mat_sub1['unk2'] = read_float(f)
        mat_sub1['unk3'] = read_float(f)
        f.read(8) # Always zero
        string = read_uint(f)
        mat_sub1['unk4'] = read_uint(f)
        next = f.tell()
        assert next - base == 32

        f.seek(base+string)
        mat_sub1['string'] = read_str(f)

        f.seek(next)
        mat_sub1s.append(mat_sub1)
    return mat_sub1s


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
        sound_name = read_uint(f)
        sub1_offset = read_uint(f)
        sub1_count = read_uint(f)
        sub2_offset = read_uint(f)
        sub2_count = read_uint(f)
        material['unk1'] = read_uint(f)
        next = f.tell()
        assert next - base == 32

        material['name'] = name_table[material_name]
        f.seek(base+sound_name)
        material['sound_name'] = read_wstr(f)

        material['sub1'] = parse_mat_sub1(f, sub1_count, base+sub1_offset)
        material['textures'] = parse_mat_txr(f, sub2_count, base+sub2_offset)

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
                for n in range(4):
                    array.append(read_float(f))
            elif type == 4: #float3
                for n in range(3):
                    array.append(read_float(f))
            elif type == 7: #half4
                for n in range(4):
                    array.append(read_half(f))
            elif type == 12: #float2
                for n in range(2):
                    array.append(read_float(f))
            elif type == 21: #ubyte4
                for n in range(4):
                    array.append(f.read(1)[0])
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
        material = bpy.data.materials.new(mdb_material['name'])
        material.blend_method = 'HASHED'
        material.use_nodes = True
        bsdf = material.node_tree.nodes['Principled BSDF']
        bsdf.inputs['Roughness'].default_value = 1.0 # Remove shine
        for texture in mdb_material['textures']:
            texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
            filename = mdb['textures'][texture['texture']]['filename']
            if filename in textures:
                texImage.image = textures[filename]
            else:
                try:
                    texImage.image = bpy.data.images.load(os.path.join(os.path.dirname(filepath), '..', 'HD-TEXTURE', filename))
                    textures[filename] = texImage.image
                except RuntimeError as e: # Ignore texture import error
                    print(e)
            if texture['map'] == 'albedo':
                texImage.location[0] = bsdf.location[0] - 300
                texImage.location[1] = bsdf.location[1]
                material.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])
                material.node_tree.links.new(bsdf.inputs['Alpha'], texImage.outputs['Alpha'])
            elif texture['map'] == 'normal':
                if texImage.image is not None:
                    texImage.image.colorspace_settings.name = 'Linear'
                texImage.location[0] = bsdf.location[0] - 150 * 12

                # Unswizzle normal map
                splitRGB = material.node_tree.nodes.new('ShaderNodeSeparateRGB')
                splitRGB.location[0] = bsdf.location[0] - 150 * 10
                material.node_tree.links.new(splitRGB.inputs['Image'], texImage.outputs['Color'])

                valR = material.node_tree.nodes.new('ShaderNodeMath')
                valR.location[0] = bsdf.location[0] - 150 * 9
                valR.operation = 'MULTIPLY'
                material.node_tree.links.new(valR.inputs[0], splitRGB.outputs['R'])
                material.node_tree.links.new(valR.inputs[1], texImage.outputs['Alpha'])

                mulR = material.node_tree.nodes.new('ShaderNodeMath')
                mulR.location[0] = bsdf.location[0] - 150 * 8
                mulR.operation = 'MULTIPLY_ADD'
                material.node_tree.links.new(mulR.inputs[0], valR.outputs['Value'])
                mulR.inputs[1].default_value = 2.0
                mulR.inputs[2].default_value = -1.0

                mulG = material.node_tree.nodes.new('ShaderNodeMath')
                mulG.location[0] = bsdf.location[0] - 150 * 8
                mulG.location[1] = mulG.location[1] - 170
                mulG.operation = 'MULTIPLY_ADD'
                material.node_tree.links.new(mulG.inputs[0], splitRGB.outputs['G'])
                mulG.inputs[1].default_value = 2.0
                mulG.inputs[2].default_value = -1.0

                powR = material.node_tree.nodes.new('ShaderNodeMath')
                powR.location[0] = bsdf.location[0] - 150 * 7
                powR.operation = 'MULTIPLY'
                material.node_tree.links.new(powR.inputs[0], mulR.outputs['Value'])
                material.node_tree.links.new(powR.inputs[1], mulR.outputs['Value'])

                powG = material.node_tree.nodes.new('ShaderNodeMath')
                powG.location[0] = bsdf.location[0] - 150 * 7
                powG.location[1] = powG.location[1] - 170
                powG.operation = 'MULTIPLY'
                material.node_tree.links.new(powG.inputs[0], mulG.outputs['Value'])
                material.node_tree.links.new(powG.inputs[1], mulG.outputs['Value'])

                subR = material.node_tree.nodes.new('ShaderNodeMath')
                subR.location[0] = bsdf.location[0] - 150 * 6
                subR.operation = 'SUBTRACT'
                subR.inputs[0].default_value = 1.0
                material.node_tree.links.new(subR.inputs[1], powR.outputs['Value'])

                subG = material.node_tree.nodes.new('ShaderNodeMath')
                subG.location[0] = bsdf.location[0] - 150 * 5
                subG.operation = 'SUBTRACT'
                material.node_tree.links.new(subG.inputs[0], subR.outputs['Value'])
                material.node_tree.links.new(subG.inputs[1], powG.outputs['Value'])

                sqrtB = material.node_tree.nodes.new('ShaderNodeMath')
                sqrtB.location[0] = bsdf.location[0] - 150 * 4
                sqrtB.operation = 'SQRT'
                material.node_tree.links.new(sqrtB.inputs[0], subG.outputs['Value'])

                valB = material.node_tree.nodes.new('ShaderNodeMath')
                valB.location[0] = bsdf.location[0] - 150 * 3
                valB.operation = 'MULTIPLY_ADD'
                material.node_tree.links.new(valB.inputs[0], sqrtB.outputs['Value'])
                valB.inputs[1].default_value = 0.5
                valB.inputs[2].default_value = 0.5

                combineRGB = material.node_tree.nodes.new('ShaderNodeCombineRGB')
                combineRGB.location[0] = bsdf.location[0] - 150 * 2
                material.node_tree.links.new(combineRGB.inputs['R'], valR.outputs['Value'])
                material.node_tree.links.new(combineRGB.inputs['G'], splitRGB.outputs['G'])
                material.node_tree.links.new(combineRGB.inputs['B'], valB.outputs['Value'])

                # Connect fixed normal map
                normalMap = material.node_tree.nodes.new('ShaderNodeNormalMap')
                normalMap.location[0] = bsdf.location[0] - 150 * 1
                material.node_tree.links.new(normalMap.inputs['Color'], combineRGB.outputs['Image'])
                material.node_tree.links.new(bsdf.inputs['Normal'], normalMap.outputs['Normal'])
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
                    normals.append((-x, -z, y))
                mesh.normals_split_custom_set_from_vertices(normals)
                mesh.use_auto_smooth = True # Enable custom normals
            
            # TODO: Binormals and tangents?

            # Add UV map
            if 'texcoord0' in vertices[0]:
                uvmap = mesh.uv_layers.new(name='UVMap')
                for face in mesh.polygons:
                    for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                        texcoord = vertices[vert_idx]['texcoord0']
                        uvmap.data[loop_idx].uv[0] = texcoord[0]
                        uvmap.data[loop_idx].uv[1] = 1.0 - texcoord[1]

            # TODO: Import texcoord1?

            # Add vertex groups
            if 'BLENDWEIGHT0' in vertices[0]:
                groups = []
                for n in range(len(mdb['bones'])):
                    groups.append(mesh_obj.vertex_groups.new(name=mdb['names'][n])) # TODO: Bone name
                for i, vert in enumerate(vertices):
                    for n in range(4):
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
