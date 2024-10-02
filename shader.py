import pprint

import bpy

IS_BPY_V3 = bpy.app.version < (4, 0, 0)

def new_socket(node_tree, name, in_out, socket_type):
    global IS_BPY_V3
    if IS_BPY_V3:
        if in_out == 'INPUT':
            node_tree.inputs.new(socket_type, name)
        elif in_out == 'OUTPUT':
            node_tree.outputs.new(socket_type, name)
        else:
            raise TypeError(f'new_socket(): error with argument in_out - "{in_out}" not "INPUT" or "OUTPUT"')
    else:
        node_tree.interface.new_socket(name, description='', in_out=in_out, socket_type=socket_type)

class Shader:
    def __init__(self, shader_name, shader_data):
        shader_tree = bpy.data.node_groups.new(shader_name, 'ShaderNodeTree')
        group_inputs = shader_tree.nodes.new('NodeGroupInput')
        group_inputs.location[0] = -200
        group_outputs = shader_tree.nodes.new('NodeGroupOutput')
        group_outputs.location[0] = 500
        new_socket(shader_tree, 'Surface', 'OUTPUT', 'NodeSocketShader')

        self.shader_tree = shader_tree
        self.group_inputs = group_inputs
        self.split_map = {}
        self.param_map = {}
        multi_tex={}
        self.multi_tex = multi_tex
        self.has_alpha = False
        self.facing = None

        params = {}
        # Map out multi purpose textures
        for param in shader_data:
            pname, ptype = param[:2]
            self.param_map[pname] = param
            if 'param_' in pname and (ptype == 'texture' or ptype == 'texture_alpha'):
                if pname == 'param_light_mask':
                    multi_tex['lightmask']=(pname, 'R')
                else:
                    comps = pname[pname.find('param_')+6:].split('_')
                    for i in range(min(len(comps), 4)):
                        if comps[i] == 'XXX':
                            continue
                        elif i == 0:
                            multi_tex[comps[i]]=(pname, 'R')
                        elif i == 1:
                            multi_tex[comps[i]]=(pname, 'G')
                        elif i == 2:
                            multi_tex[comps[i]]=(pname, 'B')
                        elif i == 3 and ptype == 'texture_alpha':
                            multi_tex[comps[i]]=(pname + '_alpha',)

        # Setup all shader parameters
        for param in shader_data:
            pname, ptype = param[:2]
            params[pname]=ptype
            # Add inputs to shader
            if ptype == 'normal':
                new_socket(shader_tree, pname, 'INPUT', 'NodeSocketVector')
            elif ptype == 'float4' or ptype == 'texture_alpha':
                new_socket(shader_tree, pname, 'INPUT', 'NodeSocketColor')
                new_socket(shader_tree, pname + '_alpha', 'INPUT', 'NodeSocketFloat')
                group_inputs.outputs[pname].default_value = (1, 1, 1, 1)
                group_inputs.outputs[pname + '_alpha'].default_value = 1
            elif ptype == 'float3' or ptype == 'texture':
                new_socket(shader_tree, pname, 'INPUT', 'NodeSocketColor')
                group_inputs.outputs[pname].default_value = (1, 1, 1, 1)
            elif ptype == 'float2':
                new_socket(shader_tree, pname + '_x', 'INPUT', 'NodeSocketFloat')
                new_socket(shader_tree, pname + '_y', 'INPUT', 'NodeSocketFloat')
            elif ptype == 'float':
                new_socket(shader_tree, pname, 'INPUT', 'NodeSocketFloat')

            # Set up proper defaults
            if len(param) > 2:
                default = param[2]
                if ptype == 'float4':
                    group_inputs.outputs[pname].default_value = (*default[:3], 1)
                    group_inputs.outputs[pname + '_alpha'].default_value = default[3]
                elif ptype == 'float3':
                    group_inputs.outputs[pname].default_value = (*default, 1)
                elif ptype == 'float2':
                    group_inputs.outputs[pname + '_x'].default_value = default[0]
                    group_inputs.outputs[pname + '_y'].default_value = default[1]
                elif ptype == 'float':
                    group_inputs.outputs[pname].default_value = default

        # TODO: Connect inputs to various actual shaders
        bsdf = shader_tree.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location[0] = 200
        shader_tree.links.new(group_outputs.inputs['Surface'], bsdf.outputs['BSDF'])

        # Connect simple inputs
        self.normal = None
        if 'normal' in params:
            self.normal = group_inputs.outputs['normal']
        elif 'damage_normal' in params:
            self.normal = group_inputs.outputs['damage_normal']
        if self.normal is not None:
            shader_tree.links.new(bsdf.inputs['Normal'], self.normal)

        if 'metallic' in params:
            shader_tree.links.new(bsdf.inputs['Metallic'], group_inputs.outputs['metallic'])
        if 'roughness' in params:
            shader_tree.links.new(bsdf.inputs['Roughness'], group_inputs.outputs['roughness'])

        # Setup shader color chain
        color_input=None
        if 'diffuse' in params and 'albedo' in params:
            col_mul = shader_tree.nodes.new('ShaderNodeMixRGB')
            col_mul.blend_type = 'MULTIPLY'
            col_mul.inputs['Fac'].default_value = 1
            shader_tree.links.new(col_mul.inputs['Color1'], group_inputs.outputs['diffuse'])
            shader_tree.links.new(col_mul.inputs['Color2'], group_inputs.outputs['albedo'])
            color_input = col_mul.outputs['Color']
        elif 'diffuse' in params:
            color_input = group_inputs.outputs['diffuse']
        elif 'albedo' in params:
            color_input = group_inputs.outputs['albedo']

        if 'change_color0' in params and 'change_color1' in params and 'cm0' in multi_tex and 'cm1' in multi_tex:
            col1_mix = shader_tree.nodes.new('ShaderNodeMixRGB')
            col1_mix.inputs['Color1'].default_value = (1, 1, 1, 1)
            shader_tree.links.new(col1_mix.inputs['Fac'], self.get_or_split('cm1'))
            shader_tree.links.new(col1_mix.inputs['Color2'], group_inputs.outputs['change_color1'])
            col0_mix = shader_tree.nodes.new('ShaderNodeMixRGB')
            shader_tree.links.new(col0_mix.inputs['Fac'], self.get_or_split('cm0'))
            shader_tree.links.new(col0_mix.inputs['Color1'], col1_mix.outputs['Color'])
            shader_tree.links.new(col0_mix.inputs['Color2'], group_inputs.outputs['change_color0'])
            if color_input is not None:
                col_mul = shader_tree.nodes.new('ShaderNodeMixRGB')
                col_mul.blend_type = 'MULTIPLY'
                col_mul.inputs['Fac'].default_value = 1
                shader_tree.links.new(col_mul.inputs['Color1'], color_input)
                shader_tree.links.new(col_mul.inputs['Color2'], col0_mix.outputs['Color'])
                color_input = col_mul.outputs['Color']
            else:
                color_input = col0_mix.outputs['Color']

        if color_input is not None:
            shader_tree.links.new(bsdf.inputs['Base Color'], color_input)

        # Setup alpha input
        alpha_input = None
        diffuse_alpha = None
        if params.get('diffuse') == 'float4':
            diffuse_alpha = 'diffuse_alpha'
        elif params.get('alpha') == 'float':
            diffuse_alpha = 'alpha'
        if diffuse_alpha is not None and params.get('albedo') == 'texture_alpha':
            alpha_mul = shader_tree.nodes.new('ShaderNodeMath')
            alpha_mul.operation = 'MULTIPLY'
            shader_tree.links.new(alpha_mul.inputs[0], group_inputs.outputs[diffuse_alpha])
            shader_tree.links.new(alpha_mul.inputs[1], group_inputs.outputs['albedo_alpha'])
            alpha_input = alpha_mul.outputs['Value']
        elif diffuse_alpha is not None:
            alpha_input = group_inputs.outputs[diffuse_alpha]
        elif params.get('albedo') == 'texture_alpha':
            alpha_input = group_inputs.outputs['albedo_alpha']
        if alpha_input is not None:
            if 'translucent_fall_off_offset' in params:
                tfo_mul = shader_tree.nodes.new('ShaderNodeMath')
                tfo_mul.operation = 'MULTIPLY'
                shader_tree.links.new(tfo_mul.inputs[0], alpha_input)
                shader_tree.links.new(tfo_mul.inputs[1], self.gen_edge_chain('translucent_'))
                alpha_input = tfo_mul.outputs['Value']
            shader_tree.links.new(bsdf.inputs['Alpha'], alpha_input)
        self.has_alpha = alpha_input is not None

        # Setup emissive light
        light_input=None
        if 'light_color' in params and 'lightmask' in multi_tex:
            light_mul = shader_tree.nodes.new('ShaderNodeMixRGB')
            light_mul.blend_type = 'MULTIPLY'
            light_mul.inputs['Fac'].default_value = 1
            shader_tree.links.new(light_mul.inputs['Color1'], group_inputs.outputs['light_color'])
            if 'hlightmask' in multi_tex:
                mask_mul = shader_tree.nodes.new('ShaderNodeMath')
                mask_mul.operation = 'MULTIPLY'
                shader_tree.links.new(mask_mul.inputs[0], self.get_or_split('lightmask'))
                shader_tree.links.new(mask_mul.inputs[1], self.get_or_split('hlightmask'))
                shader_tree.links.new(light_mul.inputs['Color2'], mask_mul.outputs['Value'])
            else:
                shader_tree.links.new(light_mul.inputs['Color2'], self.get_or_split('lightmask'))
            light_input = light_mul.outputs['Color']
        elif 'light_color' in params:
            light_input = group_inputs.outputs['light_color']
        if light_input is not None:
            if 'light_fall_off_offset' in params:
                lfo_mul = shader_tree.nodes.new('ShaderNodeMixRGB')
                lfo_mul.blend_type = 'MULTIPLY'
                lfo_mul.inputs['Fac'].default_value = 1
                shader_tree.links.new(lfo_mul.inputs['Color1'], light_input)
                shader_tree.links.new(lfo_mul.inputs['Color2'], self.gen_edge_chain('light_'))
                light_input = lfo_mul.outputs['Color']
            emission_input = 'Emission' if IS_BPY_V3 else 'Emission Color'
            shader_tree.links.new(bsdf.inputs[emission_input], light_input)

        # Reflections
        if 'reflect' in multi_tex:
            specular_input = 'Specular' if IS_BPY_V3 else 'Specular IOR Level'
            shader_tree.links.new(bsdf.inputs[specular_input], self.get_or_split('reflect'))
        # TODO: How to handle specular?

        # Deselect all nodes
        for node in shader_tree.nodes:
            node.select = False

    def get_or_split(self, comp):
        tex_comp = self.multi_tex[comp]
        if len(tex_comp) == 1:
            return self.group_inputs.outputs[tex_comp[0]]
        if tex_comp[0] not in self.split_map:
            img_split = self.shader_tree.nodes.new('ShaderNodeSeparateRGB')
            self.split_map[tex_comp[0]] = img_split
            self.shader_tree.links.new(img_split.inputs['Image'], self.group_inputs.outputs[tex_comp[0]])
        return self.split_map[tex_comp[0]].outputs[tex_comp[1]]

    def gen_edge_chain(self, prefix):
        if self.facing is None:
            layer_weight = self.shader_tree.nodes.new('ShaderNodeLayerWeight')
            layer_weight.inputs['Blend'].default_value = 0.05
            if self.normal is not None:
                self.shader_tree.links.new(layer_weight.inputs['Normal'], self.normal)
            self.facing = layer_weight.outputs['Facing']

        scale_mul = self.shader_tree.nodes.new('ShaderNodeMath')
        scale_mul.operation = 'MULTIPLY'
        self.shader_tree.links.new(scale_mul.inputs[0], self.facing)
        self.shader_tree.links.new(scale_mul.inputs[1], self.group_inputs.outputs[prefix + 'fall_off_scale'])

        offset_add = self.shader_tree.nodes.new('ShaderNodeMath')
        offset_add.operation = 'ADD'
        self.shader_tree.links.new(offset_add.inputs[0], scale_mul.outputs['Value'])
        self.shader_tree.links.new(offset_add.inputs[1], self.group_inputs.outputs[prefix + 'fall_off_offset'])
        return offset_add.outputs['Value']


def create_shader_data(mdb_material):
    shader_data = []
    # generate all param data
    for param in mdb_material['params']:
        param_type = param['type'] + 1
        if param_type == 1:
            data = (param['name'], 'float', param['val0'])
            shader_data.append(data)
        else:
            default_values = tuple(param[f'val{i}'] for i in range(param_type))
            float_size = f'float{param_type}'
            data = (param['name'], float_size, default_values)
            shader_data.append(data)
    # generate all material data
    texture_types = {
        '_dist': 'texture',
        'diffuse': 'texture',
        'light0': 'texture',
        'light1': 'texture',
        'normal': 'normal',
        'albedo': 'texture_alpha',
        'specint_occ': 'texture_alpha'
    }
    # Todo expand on this list above and test if they consistently work or not to replace the shader_data list
    for texture in mdb_material['textures']:
        texture_name = texture['map']
        found = False
        for sub, value in texture_types.items():
            if sub in texture_name:
                found = True
                shader_data.append((texture_name, value))
                break
        if not found:
            # raise TypeError(f'Texture type not found for: {texture_name} !')
            print(f'Texture type not found for: {texture_name} !')
    # pprint.pprint(shader_data)
    return shader_data


def get_shader(mdb_material, option_ignore_errors):
    global ignore_errors;
    ignore_errors = option_ignore_errors
    shader_name = mdb_material['shader']
    shader_data = create_shader_data(mdb_material)
    shader = Shader(shader_name, shader_data)
    return shader
