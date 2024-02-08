# MDB Exporter for Blender
# Author: Smileynator

import bpy
import struct
import pprint
import numpy as np

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
            'blender_material': material,
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
        #print(f'Writing material: {material["mat_name"]} at {material["base_pos"]}')
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
        #print(f'Writing parameters: {material["mat_name"]} at {parameters_pos}')
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
        #print(f'Writing textures: {material["mat_name"]} at {textures_pos}')
        rewrite_offset(file, material['texture_pos'], textures_pos, material['base_pos'])
        for texture in material['textures']:
            texture['base_pos'] = file.tell()
            file.write(struct.pack('i', texture['texture_index']))
            texture['type_pos'] = file.tell()
            file.write(struct.pack('i', 0))
            file.write(bytes([0x00]) * 20)  # Unknown values

# Seeks to the target, writes a file offset relative to the given base, returns to original position
def rewrite_offset(file, rewrite_target, current_position, target_base_offset):
    file.seek(rewrite_target)
    offset = current_position - target_base_offset
    file.write(struct.pack('I', offset))
    file.seek(current_position)


# Gathers all objects and their underlying data
def get_objects(names, materials):
    objects = []
    obj_index = 0
    for obj in bpy.data.objects:
        if obj.data is not None:
            continue
        object_data = {
            'index': obj_index,
            'name_index': names.index(obj.name),
        }
        # Get all meshes
        mesh_objects = [child for child in obj.children if child.type == 'MESH']
        object_data['mesh_count'] = len(mesh_objects)
        object_data['mesh_data'] = []
        for index, mesh_object in enumerate(mesh_objects):
            object_data['mesh_data'].append(get_mesh_data(index, mesh_object, materials))

        obj_index += 1
        objects.append(object_data)
    return objects


# Gathers mesh info data
def get_mesh_data(index, mesh_object, materials):
    mesh = mesh_object.data
    material_index = -1
    # Get the material used for this mesh
    for mat in materials:
        if mesh.materials[0] == mat['blender_material']:
            material_index = mat['index']
            break
    # Get max bone weights to a single vertex
    bone_weights = 0
    for vert in mesh.vertices:
        current_weights = 0
        for group in vert.groups:
            if group.weight > 0:
                current_weights += 1
        if current_weights > bone_weights:
            bone_weights = current_weights
    is_skinned = any(mod.type == 'ARMATURE' for mod in mesh_object.modifiers)
    mesh_data = {
        'skinned_mesh': int(is_skinned),
        'bones_per_vertex': bone_weights,
        # TODO who wants to bet there is a 2nd material option at 0x08?
        'material_index': material_index,
        'vertices_count': len(mesh.vertices),
        'mesh_index': index,
        'vertices_data': get_vertices_data(mesh, is_skinned),
        'indices_count': len(mesh.loops),
        'indice_data': [loop.vertex_index for loop in mesh.loops],  # get vertex index from each loop to form indices
    }
    # Total data size per vertex?
    data_size = 0
    for data in mesh_data['vertices_data']:
        data_size += data['size']
    mesh_data['vertices_data_size'] = data_size
    mesh_data['layout_count'] = len(mesh_data['vertices_data'])
    return mesh_data

# Gathers all the data per vertices and returns the object
def get_vertices_data(mesh, is_skinned):
    vertex_loops = {}
    for loop in mesh.loops:
        if loop.vertex_index not in vertex_loops:
            vertex_loops[loop.vertex_index] = {}
            vertex_loops[loop.vertex_index]['loops'] = []
        vertex_loops[loop.vertex_index]['loops'].append(loop)
    
    vertices_data = []
    # Due to the nature of this data, it makes sense to just generate it as i saw in example files
    # We cannot be certain for each of these if they exist or not until proven otherwise in practice
    position_data = {
        'name': 'position',
        'type': 7,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertices_data.append(position_data)
    normal_data = {
        'name': 'normal',
        'type': 7,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertices_data.append(normal_data)
    binormal_data = {
        'name': 'binormal',
        'type': 7,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertices_data.append(binormal_data)
    tangent_data = {
        'name': 'tangent',
        'type': 7,
        'size': 8,
        'channel': 0,
        'data': []
    }
    vertices_data.append(tangent_data)
    if is_skinned:
        blend_weight_data = {
            'name': 'BLENDWEIGHT',
            'type': 1,
            'size': 16,
            'channel': 0,
            'data': []
        }
        vertices_data.append(blend_weight_data)
        blend_indices_data = {
            'name': 'BLENDINDICES',
            'type': 21,
            'size': 4,
            'channel': 0,
            'data': []
        }
        vertices_data.append(blend_indices_data)
    # We store a UV array seperately just for easy access when looping over indices.
    uv_data = []
    for channel, uv in enumerate(mesh.uv_layers):
        texcoord_data = {
            'name': 'texcoord',
            'type': 12,
            'size': 8,
            'channel': channel,
            'data': []
        }
        uv_data.append(texcoord_data)
        vertices_data.append(texcoord_data)
    # Finally we go over all the vertices and populate the data arrays in each of the above data channels
    uv_count = len(mesh.uv_layers)
    for vert in mesh.vertices:
        loop = vertex_loops[vert.index]['loops'][0] # Get the first loop this vertex is part of
        position_data['data'].append([vert.co[0], vert.co[1], vert.co[2], 0.0])
        normal_data['data'].append([vert.normal[0], vert.normal[1], vert.normal[2], 0.0])
        # TODO figure out calculating binormal and tangent instead of taking first blindly
        binormal_data['data'].append([loop.bitangent[0], loop.bitangent[1], loop.bitangent[2], 0.0])
        tangent_data['data'].append([loop.tangent[0], loop.tangent[1], loop.tangent[2], 0.0])
        # UVs
        for i in range(uv_count):
            uv_vector = mesh.uv_layers[i].data[loop.index].uv
            uv_data[i]['data'].append([uv_vector[0], uv_vector[1]])
        # Skinned mesh
        if is_skinned:
            weights = []
            indices = []
            for index, bone in enumerate(vert.groups):
                if bone.weight > 0:
                    weights.append(bone.weight)
                    indices.append(index) #TODO incorrect?
                    if len(weights) == 4:
                        break # No need to keep looping, we got all 4 which is the maximum
            while len(weights) < 4:
                weights.append(0.0)
                indices.append(0)
            blend_weight_data['data'].append([weights[0], weights[1], weights[2], weights[3]])
            blend_indices_data['data'].append([indices[0], indices[1], indices[2], indices[3]])
    # Set offsets in data
    offset = 0
    for layout in vertices_data:
        layout['offset'] = offset
        offset += layout['size']
    return vertices_data


def write_object_data(file, objects):
    for object in objects:
        # Write object info
        object['base_pos'] = file.tell()
        file.write(struct.pack('I', object['index']))
        file.write(struct.pack('i', object['name_index']))
        file.write(struct.pack('I', object['mesh_count']))
        object['mesh_pos'] = file.tell()
        file.write(struct.pack('I', 0))
    for object in objects:
        # Replace mesh_pos in object data
        rewrite_offset(file, object['mesh_pos'], file.tell(), object['base_pos'])
        write_mesh_data(file, object)

def write_mesh_data(file, object):
    # Write Mesh info
    for mesh in object['mesh_data']:
        mesh['base_pos'] = file.tell()
        file.write(bytes([0x00]))  # Unknown bool
        file.write(struct.pack('B', mesh['skinned_mesh']))
        file.write(struct.pack('B', mesh['bones_per_vertex']))
        file.write(bytes([0x00]))  # Alignment
        file.write(struct.pack('i', mesh['material_index']))
        file.write(struct.pack('i', 0))  # Unknown value always 0?
        mesh['vertex_layout_pos'] = file.tell()
        file.write(struct.pack('i', 0))
        file.write(struct.pack('H', mesh['vertices_data_size']))
        file.write(struct.pack('H', mesh['layout_count']))
        file.write(struct.pack('I', mesh['vertices_count']))
        file.write(struct.pack('I', mesh['mesh_index']))
        mesh['vertex_data_pos'] = file.tell()
        file.write(struct.pack('i', 0))
        file.write(struct.pack('I', mesh['indices_count']))
        mesh['indice_data_pos'] = file.tell()
        file.write(struct.pack('i', 0))
    for mesh in object['mesh_data']:
        # Replace vertex_layout_pos in mesh data
        rewrite_offset(file, mesh['vertex_layout_pos'], file.tell(), mesh['base_pos'])
        # Write Vertex Layer Info
        for layout in mesh['vertices_data']:
            layout['base_pos'] = file.tell()
            file.write(struct.pack('I', layout['type']))
            file.write(struct.pack('I', layout['offset']))
            file.write(struct.pack('I', layout['channel']))
            layout['name_pos'] = file.tell()
            file.write(struct.pack('I', 0))
    for mesh in object['mesh_data']:
        # Replace indice_data_pos in mesh data
        rewrite_offset(file, mesh['indice_data_pos'], file.tell(), mesh['base_pos'])
        # Write all indices
        for indice in mesh['indice_data']:
            file.write(struct.pack('H', indice))
    for mesh in object['mesh_data']:
        # Replace vertex_data_pos in mesh data
        rewrite_offset(file, mesh['vertex_data_pos'], file.tell(), mesh['base_pos'])
        # Write all Vertex data
        for i in range(mesh['vertices_count']):
            for layout in mesh['vertices_data']:
                type = layout['type']
                vert_data = layout['data'][i]
                if type == 1: #float4
                    file.write(struct.pack('4f', *vert_data))
                elif type == 4: #float3
                    file.write(struct.pack('3f', *vert_data))
                elif type == 7: #half4
                    half_array = np.array(vert_data, dtype=np.float32).astype(np.half)
                    file.write(half_array.tobytes())
                elif type == 12: #float2
                    file.write(struct.pack('2f', *vert_data))
                elif type == 21: #ubyte4
                    file.write(struct.pack('4B', *vert_data))
                else:
                    print("Unknown vertex layout type: " + str(type))
            
            


def save(operator, context, filepath="", **kwargs):
    # Get the name table
    indexed_strings = get_unique_names()
    # Gather all the different parts we need
    bones = get_bone_data(indexed_strings)
    texture_names = get_textures()
    materials = get_materials(texture_names)
    objects = get_objects(indexed_strings, materials)
    
    with open(filepath, 'wb') as file:
        # Write header
        write_header(file, indexed_strings, bones, objects, materials, texture_names)
        # Write name pointers placeholder
        file.write(bytes([0x01, 0x02, 0x03, 0x04]) * len(indexed_strings))
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
        write_object_data(file, objects)
        # Write all strings
        #write_strings(file, indexed_strings)
        
        #TODO all the string replacement
    #pprint.pprint(objects[0]['mesh_data'])
    return {'FINISHED'}
