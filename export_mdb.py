import bpy
import struct
import pprint

from .shader_data import shaders as shader_data


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
    file.write(struct.pack('I', 0))
    
    # Material count and offset
    materials_length = len(materials)
    file.write(struct.pack('I', materials_length))
    file.write(struct.pack('I', 0))
    
    # Texture count and offset
    textures_length = len(textures)
    file.write(struct.pack('I', textures_length))
    file.write(struct.pack('I', 0))


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
        
    for index, name in enumerate(names):
        print(f'String: {index} {name}')
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


# Writes all texture data, total size per texture 0x10 (16)
def write_texture_data(file, textures):
    for index, texture in enumerate(textures):
        # Index
        file.write(struct.pack('I', index))
        # Texture name and filename offset placeholders
        file.write(bytes([0x00]) * 8)
        # 4 empty bytes at the end
        file.write(bytes([0x00]) * 4)


def get_materials(textures):
    materials = []
    valid_materials = []
    # Filter any material that are not recognized by shader_data
    for material in bpy.data.materials:
        if material.use_nodes:
            found_shader_node = False
            for node in material.node_tree.nodes:
                if hasattr(node, 'inputs') and node.type == 'GROUP' and node.node_tree.name in shader_data:
                    found_shader_node = True
                    break
            if found_shader_node:
                valid_materials.append(material)
            else:
                print(f"Warning: Material {material.name} ignored for not having a shader node.")
                    
    # Process the valid materials
    for index, material in enumerate(valid_materials):
        material_data = {
            'index': index,
            'mat_name': material.name.encode('utf-16'),
        }
        parameters = []
        texture_data = []
        # Get all the inputs of the shader group as parameters
        if material.use_nodes:
            for node in material.node_tree.nodes:
                # Filter the one group we are interested in
                if hasattr(node, 'inputs') and node.type == 'GROUP' and node.node_tree.name in shader_data:
                    material_data['shader_name'] = node.node_tree.name.encode('utf-16')
                    for input in node.inputs:
                        # Skip all "extra" inputs
                        if input.name.endswith('_y') or input.name.endswith('_alpha'):
                            continue
                        if is_texture_node(node.node_tree.name, input.name):
                            texture_data.append(get_texture(input, textures))
                        else:
                            parameters.append(get_parameter(node.inputs, input))
                    break
        material_data['parameters'] = parameters
        material_data['parameter_count'] = len(parameters)
        material_data['parameter_offset'] = 0
        material_data['textures'] = texture_data
        material_data['texture_count'] = len(texture_data)
        material_data['texture_offset'] = 0
        #TODO unknown values
        materials.append(material_data)
    return materials


# Return true of this is a texture type parameter, hope there are no name clashes
def is_texture_node(shader, input_name):
    if shader in shader_data:
        properties = shader_data[shader]
        for prop in properties:
            if prop[0] == input_name and prop[1] in ['normal', 'texture', 'texture_alpha']:
                return True
    else:
        print(f"Warning: Shader {shader} not found!")
    return False


# Gets the parameters relevant data for this node input
def get_parameter(all_inputs, input):
    parameter_data = None
    if input.name.endswith('_x'):
        y_input = all_inputs[input.name.replace('_x', '_y')]
        parameter_data = {
            'name': input.name.rstrip('_x'),
            'values': [input.default_value, y_input.default_value],
            'type': 1, #Vector2 type
            'size': 2
        }
    elif input.type == 'RGBA':
        type = 2 #RGB type
        values = [input.default_value[0], input.default_value[1], input.default_value[2]]
        alpha_input = all_inputs.get(input.name+'_alpha', None)
        if alpha_input is not None:
            type = 3 #RGBA type
            values.append(input.default_value[3])
        parameter_data = {
            'name': input.name,
            'values': values,
            'type': type,
            'size': 4
        }
    elif input.type == 'VALUE':
        parameter_data = {
            'name': input.name,
            'values': [input.default_value],
            'type': 0, # Float type
            'size': 1
        }
    else:
        print(f"Unknown parameter type! Not exported! {input.name}, {input.type}")
    # Pad params to 6 values, this makes writing easier
    parameter_data['values'] = parameter_data['values'] + [0.0] * (6-len(parameter_data['values']))
    return parameter_data


# Gets the texture relevant data for this node input
def get_texture(input, textures):
    image_node = find_parent_texture_node(input)
    texture_data = {
        'texture_index': textures.index(image_node.image.name),
        'type': input.name.encode('ascii'),
        # TODO a lot of unknown data to be filled here
    }
    return texture_data


# Recursively finds the source node which supplies the texture to this node input
def find_parent_texture_node(input):
    
    for link in input.links:
        if link.from_node.type == 'TEX_IMAGE':
            return link.from_node
        for input in link.from_node.inputs:
            result = find_parent_texture_node(input)
            if result:
                return result


# Writes all material data, total size per material 0x20 (32)
def write_material_data(file, materials):
    # Write the main material data
    for material in materials:
        material['base_pos'] = file.tell()
        print(f'Writing material: {material["mat_name"]} at {material["base_pos"]}')
        file.write(struct.pack('H', material['index']))
        file.write(bytes([0x00]) * 2)   # unknown bytes
        # Material name and Shader name offset placeholders
        file.write(bytes([0x00]) * 8)
        material['parameter_pos'] = file.tell()
        file.write(struct.pack('i', 0))
        file.write(struct.pack('i', material['parameter_count']))
        material['texture_pos'] = file.tell()
        file.write(struct.pack('i', 0))
        file.write(struct.pack('i', material['texture_count']))
        file.write(struct.pack('i', 0x03)) # Unknown but usually 3
        
    # Write the parameter and texture data per material
    for material in materials:
        # Parameters
        parameters_pos = file.tell()
        print(f'Writing parameters: {material["mat_name"]} at {parameters_pos}')
        rewrite_offset(file, material['parameter_pos'], parameters_pos, material['base_pos'])
        for parameter in material['parameters']:
            parameter['base_pos'] = file.tell()
            file.write(struct.pack('6f', *parameter['values']))
            parameter['name_pos'] = file.tell()
            file.write(struct.pack('i', 0))
            file.write(struct.pack('B', parameter['type']))
            file.write(struct.pack('B', parameter['size']))
            file.write(bytes([0x00]) * 2)  # padding
        # Textures
        textures_pos = file.tell()
        print(f'Writing textures: {material["mat_name"]} at {textures_pos}')
        rewrite_offset(file, material['texture_pos'], textures_pos, material['base_pos'])
        for texture in material['textures']:
            texture['base_pos'] = file.tell()
            file.write(struct.pack('i', texture['texture_index']))
            texture['type_pos'] = file.tell()
            file.write(struct.pack('i', 0))
            file.write(bytes([0x00]) * 20)  # Unknown values


def rewrite_offset(file, rewrite_target, current_position, target_base_offset):
    file.seek(rewrite_target)
    offset = current_position - target_base_offset
    file.write(struct.pack('I', offset))
    file.seek(current_position)

def save(operator, context, filepath="", **kwargs):
    # Current assumption is that the whole scene is what you want to export
    
    # Get the name table
    names = get_unique_names()
    # Get all bones in the rig(s)
    bones = get_bone_data(names)
    # Get all textures used
    texture_names = get_textures()
    # Get Material Data
    materials = get_materials(texture_names)
    # Get Object Data
    objects = {}#TODO
    
    with open(filepath, 'wb') as file:
        
        # Write header
        write_header(file, names, bones, objects, materials, texture_names)
        # Write name pointers placeholder
        file.write(bytes([0x01, 0x02, 0x03, 0x04]) * len(names))
        # Write Bone Data
        write_bone_data(file, bones)
        # Write header Texture offset
        rewrite_offset(file, 0x2C, file.tell(), 0x00)
        # Write Texture data
        write_texture_data(file, texture_names)
        # Write header Material offset
        rewrite_offset(file, 0x24, file.tell(), 0x00)
        # Write Material data
        write_material_data(file, materials)
        # Write header Object offset
        rewrite_offset(file, 0x1C, file.tell(), 0x00)
        # Write Object data
        # TODO
        
    return {'FINISHED'}
