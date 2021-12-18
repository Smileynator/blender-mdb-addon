import bpy

from .shader_data import shaders as shader_data

shader_cache={}

class Shader:
    def __init__(self, shader):
        shader_tree = bpy.data.node_groups.new(shader, 'ShaderNodeTree')
        group_inputs = shader_tree.nodes.new('NodeGroupInput')
        group_inputs.location[0] = -200
        group_outputs = shader_tree.nodes.new('NodeGroupOutput')
        group_outputs.location[0] = 500
        shader_tree.outputs.new('NodeSocketShader', 'Surface')
        self.shader_tree = shader_tree
        self.group_inputs = group_inputs
        self.split_map = {}
        self.param_map = {}

        if shader in shader_data:
            params={}

            # Map out multi purpose textures
            multi_tex={}
            self.multi_tex = multi_tex
            for param in shader_data[shader]:
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
                                multi_tex[comps[i]]=(pname + '_alpha')

            # Setup all shader parameters
            for param in shader_data[shader]:
                pname, ptype = param[:2]
                params[pname]=ptype
                # Add inputs to shader
                if ptype == 'normal':
                    shader_tree.inputs.new('NodeSocketVector', pname)
                elif ptype == 'float4' or ptype == 'texture_alpha':
                    shader_tree.inputs.new('NodeSocketColor', pname)
                    shader_tree.inputs.new('NodeSocketFloat', pname + '_alpha')
                    shader_tree.inputs[pname].default_value = (1, 1, 1, 1)
                    shader_tree.inputs[pname + '_alpha'].default_value = 1
                elif ptype == 'float3' or ptype == 'texture':
                    shader_tree.inputs.new('NodeSocketColor', pname)
                    shader_tree.inputs[pname].default_value = (1, 1, 1, 1)
                elif ptype == 'float2':
                    shader_tree.inputs.new('NodeSocketFloat', pname + '_x')
                    shader_tree.inputs.new('NodeSocketFloat', pname + '_y')
                elif ptype == 'float':
                    shader_tree.inputs.new('NodeSocketFloat', pname)

                # Set up proper defaults
                if len(param) > 2:
                    default = param[2]
                    if ptype == 'float4':
                        shader_tree.inputs[pname].default_value = (*default[:3], 1)
                        shader_tree.inputs[pname + '_alpha'].default_value = default[3]
                    elif ptype == 'float3':
                        shader_tree.inputs[pname].default_value = (*default, 1)
                    elif ptype == 'float2':
                        shader_tree.inputs[pname + '_x'].default_value = default[0]
                        shader_tree.inputs[pname + '_y'].default_value = default[1]
                    elif ptype == 'float':
                        shader_tree.inputs[pname].default_value = default

            # TODO: Connect inputs to various actual shaders
            bsdf = shader_tree.nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location[0] = 200
            shader_tree.links.new(group_outputs.inputs['Surface'], bsdf.outputs['BSDF'])

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
            alpha_input=None
            if params.get('diffuse') == 'float4' and params.get('albedo') == 'texture_alpha':
                alpha_mul = shader_tree.nodes.new('ShaderNodeMath')
                alpha_mul.operation = 'MULTIPLY'
                shader_tree.links.new(alpha_mul.inputs[0], group_inputs.outputs['diffuse_alpha'])
                shader_tree.links.new(alpha_mul.inputs[1], group_inputs.outputs['albedo_alpha'])
                alpha_input = alpha_mul.outputs['Value']
            elif params.get('diffuse') == 'float4':
                alpha_input = group_inputs.outputs['diffuse_alpha']
            elif params.get('albedo') == 'texture_alpha':
                alpha_input = group_inputs.outputs['albedo_alpha']
            if alpha_input is not None:
                shader_tree.links.new(bsdf.inputs['Alpha'], alpha_input)

            # Setup emissive light
            light_input=None
            if 'light_color' in params and 'lightmask' in multi_tex:
                light_mul = shader_tree.nodes.new('ShaderNodeMixRGB')
                light_mul.blend_type = 'MULTIPLY'
                light_mul.inputs['Fac'].default_value = 1
                shader_tree.links.new(light_mul.inputs['Color1'], group_inputs.outputs['light_color'])
                shader_tree.links.new(light_mul.inputs['Color2'], self.get_or_split('lightmask'))
                light_input = light_mul.outputs['Color']
            elif 'light_color' in params:
                light_input = group_inputs.outputs['light_color']
            if light_input is not None:
                shader_tree.links.new(bsdf.inputs['Emission'], light_input)

            # Reflections
            if 'reflect' in multi_tex:
                shader_tree.links.new(bsdf.inputs['Specular'], self.get_or_split('reflect'))
            # TODO: How to handle specular?

            # Connect simple inputs
            if 'normal' in params:
                shader_tree.links.new(bsdf.inputs['Normal'], group_inputs.outputs['normal'])
            elif 'damage_normal' in params:
                shader_tree.links.new(bsdf.inputs['Normal'], group_inputs.outputs['damage_normal'])

            if 'metallic' in params:
                shader_tree.links.new(bsdf.inputs['Metallic'], group_inputs.outputs['metallic'])
            if 'roughness' in params:
                shader_tree.links.new(bsdf.inputs['Roughness'], group_inputs.outputs['roughness'])
        else:
            print('Warning: MDB uses unknown shader ' + shader)

        # Deselect all nodes
        for node in shader_tree.nodes:
            node.select = False

        self.shader_tree = shader_tree

    def get_or_split(self, comp):
        tex_comp = self.multi_tex[comp]
        if len(tex_comp) == 1:
            return self.group_inputs.outputs[tex_comp[0]]
        if tex_comp[0] not in self.split_map:
            img_split = self.shader_tree.nodes.new('ShaderNodeSeparateRGB')
            self.split_map[tex_comp[0]] = img_split
            self.shader_tree.links.new(img_split.inputs['Image'], self.group_inputs.outputs[tex_comp[0]])
        return self.split_map[tex_comp[0]].outputs[tex_comp[1]]


def get_shader(shader_name):
    if shader_name in shader_cache:
        return shader_cache[shader_name]
    shader = Shader(shader_name)
    shader_cache[shader_name] = shader
    return shader