import bpy
import struct
import pprint


def write_header(file, names, bones, objects, materials, textures):
    file.write(b'MDB0')
    file.write(struct.pack('I', 0x14))  # Version
    
    # Name Table Size and offset
    name_length = len(names)
    file.write(struct.pack('I', name_length))
    file.write(struct.pack('I', 0x30)) # fixed end of header
    
    # Bone count and offset
    bone_length = len(bones)
    file.write(struct.pack('I', bone_length))
    boneOffset = 0x30 + name_length * 0x04
    file.write(struct.pack('I', boneOffset))
    
    # Object count and offset
    objects_length = len(objects)
    file.write(struct.pack('I', objects_length))
    objectOffset = boneOffset + bone_length * 0xC0
    file.write(struct.pack('I', objectOffset))
    
    # Material count and offset
    materials_length = len(materials)
    file.write(struct.pack('I', materials_length))
    material_offset = objectOffset + objects_length * 0x10
    file.write(struct.pack('I', material_offset))
    
    # Texture count and offset
    textures_length = len(textures)
    file.write(struct.pack('I', textures_length))
    texture_offset = material_offset + textures_length * 0x10
    file.write(struct.pack('I', texture_offset))


def get_unique_names():
    names = set()
    # Get all object names
    for object in bpy.data.objects:
        if object.data is None:
            names.add(object.name)

    # Get all bone names
    for bone in bpy.data.armatures[0].bones:
        names.add(bone.name)

    # Get all material names
    for material in bpy.data.materials:
        names.add(material.name)
        
    for name in names:
        print(name)
    return list(names)

def get_bone_data(names):
    bones = []
    armature = bpy.data.armatures[0]
    if not armature:
        return
    for index, bone in enumerate(armature.bones):
        bone_data = {}
        # TODO unknown data actually filling here
        bone_data['bl_bone'] = bone # To do some lookups with INDEX
        bone_data['index'] = index
        #bone_data['parent'] = ??? if bone.parent else -1
        '''bone_data['next_sibling'] = -1
        # Find next sibling if any
        if bone.parent:
            foundSelf = False
            for sibling in bone.parent.children:
                if sibling.index == bone.index:
                    foundSelf = True
                    continue
                if foundSelf:
                    bone_data['next_sibling'] = sibling.index
        # Find first child if i have any
        bone_data['first_child'] = bone.children[0].index if bone.children[0] else -1'''
        bone_data['name_index'] = names.index(bone.name)
        bone_data['child_count'] = len(bone.children)

        # Unpack the 4x4 matrices into a flat list of 16 float values
        # TODO these matrixes seem to not be local, and if they are, they are fucked. Fix that i suppose.
        bone_data['local_matrix'] = [element for row in bone.matrix_local for element in row]
        bone_data['inverse_bind_matrix'] = [element for row in bone.matrix_local.inverted() for element in row]
        # Debug print to inspect created data
        '''if True: #index < 5:
            print(bone.name +" ---")
            pprint.pprint(bone.matrix)
            print(bone.name +" -----")
            pprint.pprint(bone)
            print(bone.name + " data ---")
            pprint.pprint(bone_data)'''
        # Append the bone data to the list
        bones.append(bone_data)
    return bones

# Writes all bone data, total size per bone 0xC0 (192)
def write_bone_data(f, bones):
    for bone in bones:
        f.write(struct.pack('I', bone['index']))
        f.write(struct.pack('i', -1))#bone['parent']))
        f.write(struct.pack('i', -1))#bone['next_sibling']))
        f.write(struct.pack('i', -1))#bone['first_child']))
        f.write(struct.pack('I', bone['name_index']))
        f.write(struct.pack('I', 0))#bone['child_count']))
        # Unknown bytes
        f.write(bytes([0x00, 0x00, 0x00]))
        # Padding previous bytes to 8
        f.write(bytes([0x00, 0x00, 0x00, 0x00, 0x00]))
        # Matrices
        f.write(struct.pack('16f', *bone['local_matrix']))
        f.write(struct.pack('16f', *bone['inverse_bind_matrix']))
        # 2 Unknown float4's, last value always 1
        f.write(struct.pack('4f', 0.0, 0.0, 0.0, 1.0))
        f.write(struct.pack('4f', 0.0, 0.0, 0.0, 1.0))


def get_textures():
    unique_textures = set()
    # Get the textures of all materials
    for material in bpy.data.materials:
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    # Add the texture name to the set
                    unique_textures.add(node.image.name)
    return list(unique_textures)


def write_texture_data(file, textures):
    for index, texture in enumerate(textures):
        # Index
        file.write(struct.pack('I', index))
        # Texture name and filename offset placeholders
        file.write(bytes([0x00]) * 8)
        # 4 empty bytes at the end
        file.write(bytes([0x00]) * 4)


def save(operator, context, filepath="", **kwargs):
    # Current assumption is that the whole scene is what you want to export
    
    # Get the name table
    names = get_unique_names()
    # Get all bones in the rig(s)
    bones = get_bone_data(names)
    # Get all textures used
    texture_names = get_textures()
    
    with open(filepath, 'wb') as file:
        objects = {}
        materials = {}
        
        # Write header
        write_header(file, names, bones, objects, materials, texture_names)
        # Write name pointers placeholder
        file.write(bytes([0x01, 0x02, 0x03, 0x04]) * len(names))
        # Write Bone Data
        write_bone_data(file, bones)
        # Write Texture data
        write_texture_data(file, texture_names)
        
    return {'FINISHED'}
