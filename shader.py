import re

import bpy


IS_BPY_V3 = bpy.app.version < (4, 0, 0)
IS_BPY_V5 = bpy.app.version >= (5, 0, 0)

# MDB does not store the UV set consumed by a shader texture. Common numbered
# slots are inferable; genuinely exceptional shaders can be added here without
# affecting material schema discovery or export.
UV_EXCEPTIONS = {
    ('snd_Chara_Basic_Light_damage', 'param_light_mask'): 1,
    ('snd_Dino_LightScroll', 'param_occ_XXX_XXX_XXX'): 2,
    ('snd_Dino_LightScroll_damage', 'param_occ_XXX_XXX_XXX'): 2,
    ('snd_Map_Build_Basic', 'dirt'): 2,
    ('snd_Map_Build_Basic', 'param_occlusion'): 1,
    ('snd_Map_Build_Basic_NC', 'dirt'): 2,
    ('snd_Map_Build_Basic_NC', 'param_occlusion'): 1,
    ('snd_Map_Build_Basic_Parallax_NC', 'dirt'): 2,
    ('snd_Map_Build_Basic_Parallax_NC', 'param_occlusion'): 1,
    ('snd_Map_Build_DirtScroll', 'dirt'): 2,
    ('snd_Map_Build_DirtScroll', 'param_occlusion'): 1,
    ('snd_Map_Build_DirtScroll_NC', 'dirt'): 2,
    ('snd_Map_Build_DirtScroll_NC', 'param_occlusion'): 1,
    ('snd_Map_Build_DirtScroll_Parallax_NC', 'dirt'): 2,
    ('snd_Map_Build_DirtScroll_Parallax_NC', 'param_occlusion'): 1,
    ('snd_Map_Build_Light_NC', 'dirt'): 2,
    ('snd_Map_Build_Light_NC', 'param_occlusion'): 1,
    ('snd_Map_Build_NoOcc', 'dirt'): 1,
    ('snd_Map_Build_Simple_Alpha', 'param_occlusion'): 1,
    ('snd_Map_Build_Simple_Clip', 'param_occlusion'): 1,
    ('snd_Map_Build_Window', 'interior_texture'): 1,
    ('snd_Map_Build_Window', 'window_normal'): 2,
    ('snd_Map_Cave_NoOcc', 'dirt'): 1,
    ('snd_Map_Field_Basic', 'dirt'): 1,
    ('snd_Map_Field_Parallax', 'dirt'): 1,
    ('snd_Map_Object', 'param_occlusion'): 1,
    ('snd_Map_Object_NoAO_Dirt', 'dirt'): 1,
    ('snd_Map_Object_NoAO_Light', 'param_occlusion'): 1,
    ('snd_Map_Object_NoCC', 'param_occlusion'): 1,
    ('snd_Mech', 'param_occ_XXX_XXX_XXX'): 1,
    ('snd_Mech_Catapillar', 'param_occlusion'): 1,
    ('snd_Mech_Light', 'param_occlusion'): 1,
    ('snd_Mech_Light_damage', 'param_occlusion'): 1,
    ('snd_Mech_damage', 'param_occ_XXX_XXX_XXX'): 1,
    ('snd_SoftMech', 'param_occ_XXX_XXX_XXX'): 1,
    ('snd_UI_Clipping_UVAnim', 'albedo1'): 1,
    ('snd_UI_GaugeBar', 'bar_mask'): 1,
    ('snd_e505_Flare', 'mask0'): 1,
    ('snd_e505_Flare', 'albedo1'): 2,
    ('snd_e505_Flare', 'mask1'): 3,
    ('snd_Chara_VirtualDome', 'albedo2'): 1,
    ('snd_e616_Venus_Shield', 'light1_tex'): 1,
}

shader_cache = {}


def new_socket(node_tree, name, in_out, socket_type):
    if IS_BPY_V3:
        if in_out == 'INPUT':
            node_tree.inputs.new(socket_type, name)
        elif in_out == 'OUTPUT':
            node_tree.outputs.new(socket_type, name)
        else:
            raise TypeError(f'Unsupported socket direction: {in_out}')
    else:
        node_tree.interface.new_socket(
            name,
            description='',
            in_out=in_out,
            socket_type=socket_type,
        )


def new_separate_rgb(node_tree):
    """Create an RGB channel separator across Blender node API versions.

    Blender 5 removed ``ShaderNodeSeparateRGB`` in favour of the more general
    ``ShaderNodeSeparateColor``.  The latter must be put in RGB mode and uses
    descriptive socket names, so callers should use ``separate_rgb_input``
    and ``separate_rgb_output`` rather than accessing sockets directly.
    """
    if IS_BPY_V5:
        node = node_tree.nodes.new('ShaderNodeSeparateColor')
        node.mode = 'RGB'
        return node
    return node_tree.nodes.new('ShaderNodeSeparateRGB')


def separate_rgb_input(node):
    return node.inputs.get('Image') or node.inputs['Color']


def separate_rgb_output(node, channel):
    legacy_names = {'R': 'Red', 'G': 'Green', 'B': 'Blue'}
    return node.outputs.get(channel) or node.outputs[legacy_names[channel]]


def new_combine_rgb(node_tree):
    """Create an RGB combiner across Blender node API versions."""
    if IS_BPY_V5:
        node = node_tree.nodes.new('ShaderNodeCombineColor')
        node.mode = 'RGB'
        return node
    return node_tree.nodes.new('ShaderNodeCombineRGB')


def combine_rgb_input(node, channel):
    modern_names = {'R': 'Red', 'G': 'Green', 'B': 'Blue'}
    return node.inputs.get(channel) or node.inputs[modern_names[channel]]


def combine_rgb_output(node):
    return node.outputs.get('Image') or node.outputs['Color']


def new_color_mix(node_tree):
    """Create a colour mix node across Blender node API versions."""
    if IS_BPY_V5:
        node = node_tree.nodes.new('ShaderNodeMix')
        node.data_type = 'RGBA'
        return node
    return node_tree.nodes.new('ShaderNodeMixRGB')


def socket_by_identifier(sockets, identifier):
    return next(socket for socket in sockets if socket.identifier == identifier)


def color_mix_factor_input(node):
    return node.inputs.get('Fac') or socket_by_identifier(
        node.inputs,
        'Factor_Float',
    )


def color_mix_color_input(node, index):
    legacy_names = {1: 'Color1', 2: 'Color2'}
    modern_names = {1: 'A_Color', 2: 'B_Color'}
    return node.inputs.get(legacy_names[index]) or socket_by_identifier(
        node.inputs,
        modern_names[index],
    )


def color_mix_output(node):
    return node.outputs.get('Color') or socket_by_identifier(
        node.outputs,
        'Result_Color',
    )


def infer_uv_channel(shader_name, slot_name):
    exception = UV_EXCEPTIONS.get((shader_name, slot_name))
    if exception is not None:
        return exception

    match = re.fullmatch(r'light(\d+)_(?:scroll|tex)', slot_name)
    if match:
        return int(match.group(1)) + 1

    match = re.fullmatch(r'(?:normal|parallax)_map(\d+)', slot_name)
    if match:
        return max(0, int(match.group(1)) - 1)

    return 0


def material_signature(material):
    if material is None:
        return (), (), 0
    parameters = tuple(
        (parameter['name'], parameter['type'], parameter['size'])
        for parameter in material['params']
    )
    textures = tuple(texture['map'] for texture in material['textures'])
    return parameters, textures, material.get('render_queue_class', 0)


class Shader:
    def __init__(self, shader_name, material):
        self.name = shader_name
        self.material = material or {'params': [], 'textures': [], 'render_queue_class': 0}
        self.parameters = {
            parameter['name']: parameter
            for parameter in self.material['params']
        }
        self.textures = {
            texture['map']
            for texture in self.material['textures']
        }
        self.param_map = {}
        self.split_map = {}
        self.packed_components = {}
        self.has_alpha = False
        self.facing = None

        shader_tree = bpy.data.node_groups.new(shader_name, 'ShaderNodeTree')
        self.shader_tree = shader_tree
        self.group_inputs = shader_tree.nodes.new('NodeGroupInput')
        self.group_inputs.location[0] = -500
        self.group_outputs = shader_tree.nodes.new('NodeGroupOutput')
        self.group_outputs.location[0] = 500
        new_socket(shader_tree, 'Surface', 'OUTPUT', 'NodeSocketShader')

        self.ensure_material_schema()
        self.map_packed_textures()
        self.build_preview()

        for node in shader_tree.nodes:
            node.select = False

    def ensure_material_schema(self):
        for parameter in self.material['params']:
            name = parameter['name']
            parameter_type = parameter['type']
            size = parameter['size']
            if size == 1:
                self.ensure_input(name, 'NodeSocketFloat')
            elif size == 2:
                self.ensure_input(name + '_x', 'NodeSocketFloat')
                self.ensure_input(name + '_y', 'NodeSocketFloat')
            else:
                self.ensure_input(name, 'NodeSocketColor')
                if parameter_type == 3:
                    self.ensure_input(name + '_alpha', 'NodeSocketFloat')

        for texture in self.material['textures']:
            name = texture['map']
            socket_type = 'NodeSocketVector' if 'normal' in name.lower() else 'NodeSocketColor'
            self.ensure_input(name, socket_type)
            self.ensure_input(name + '_alpha', 'NodeSocketFloat')
            uv_channel = infer_uv_channel(self.name, name)
            if uv_channel:
                self.param_map[name] = (name, 'texture', uv_channel)
            else:
                self.param_map[name] = (name, 'texture')

    def ensure_input(self, name, socket_type):
        if self.group_inputs.outputs.get(name) is None:
            new_socket(self.shader_tree, name, 'INPUT', socket_type)

    def input(self, name):
        return self.group_inputs.outputs.get(name)

    def build_preview(self):
        bsdf = self.shader_tree.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location[0] = 250
        self.shader_tree.links.new(self.group_outputs.inputs['Surface'], bsdf.outputs['BSDF'])

        normal = self.input('normal') or self.input('damage_normal')
        if normal is not None:
            self.shader_tree.links.new(bsdf.inputs['Normal'], normal)

        metallic = self.input('metallic')
        if metallic is not None:
            self.shader_tree.links.new(bsdf.inputs['Metallic'], metallic)

        roughness = self.input('roughness')
        if roughness is not None:
            self.shader_tree.links.new(bsdf.inputs['Roughness'], roughness)

        color = self.build_base_color()
        if color is not None:
            self.shader_tree.links.new(bsdf.inputs['Base Color'], color)

        alpha = self.build_alpha()
        if alpha is not None:
            self.shader_tree.links.new(bsdf.inputs['Alpha'], alpha)
            self.has_alpha = True

        emission, emission_strength = self.build_emission()
        if emission is not None:
            emission_input = 'Emission' if IS_BPY_V3 else 'Emission Color'
            self.shader_tree.links.new(bsdf.inputs[emission_input], emission)
        if emission_strength is not None:
            self.shader_tree.links.new(
                bsdf.inputs['Emission Strength'],
                emission_strength,
            )

        specular = self.component('reflect') or self.component('specint')
        if specular is not None:
            specular_input = 'Specular' if IS_BPY_V3 else 'Specular IOR Level'
            self.shader_tree.links.new(bsdf.inputs[specular_input], specular)

    def build_base_color(self):
        diffuse = self.input('diffuse')
        albedo = self.input('albedo')
        color = self.multiply_color(diffuse, albedo)

        change0 = self.input('change_color0')
        change1 = self.input('change_color1')
        mask0 = self.component('cm0')
        mask1 = self.component('cm1')
        change_color = None
        if change1 is not None and mask1 is not None:
            change_color = self.mix_color(None, change1, mask1)
        if change0 is not None and mask0 is not None:
            change_color = self.mix_color(change_color, change0, mask0)
        if change_color is not None:
            color = self.multiply_color(color, change_color)

        damage_color = self.input('damage_diffuse') or self.input('damage_albedo')
        damage_mask = self.input('damage_dist')
        if damage_color is not None and damage_mask is not None:
            color = self.mix_color(color, damage_color, damage_mask)

        # Packed EDF6 maps conventionally reserve B ("occ") for material
        # occlusion.  It darkens the diffuse preview only; it is neither
        # transparency nor part of the emissive mask.
        occlusion = self.component('occ')
        if color is not None and occlusion is not None:
            color = self.multiply_color(color, occlusion)

        return color

    def build_alpha(self):
        alpha = self.input('alpha')
        diffuse = self.parameters.get('diffuse')
        if diffuse is not None and diffuse['type'] == 3:
            alpha = self.multiply_value(alpha, self.input('diffuse_alpha'))

        uses_transparency = (
            self.material.get('render_queue_class') == 2
            or self.name.lower().endswith(('_alpha', '_hair', '_clip'))
            or alpha is not None
        )
        if uses_transparency and 'albedo' in self.textures:
            alpha = self.multiply_value(alpha, self.input('albedo_alpha'))

        if alpha is not None and self.has_inputs(
            'translucent_fall_off_scale',
            'translucent_fall_off_offset',
        ):
            alpha = self.multiply_value(alpha, self.gen_edge_chain('translucent_'))
        return alpha

    def build_emission(self):
        light_color = self.input('light_color')
        # EDF6 character materials pack roughness, metallic, occlusion, and
        # the emissive mask into param_r_m_occ_light.  Its alpha is a mask for
        # light_color, not opacity for the material itself.
        light_mask = self.component('light') or self.component('lightmask')
        if light_color is not None:
            emission = light_color
            emission_strength = light_mask
        else:
            emission = None
            emission_strength = None

        for index in range(4):
            color = self.input(f'light{index}_color')
            texture = (
                self.input(f'light{index}_scroll')
                or self.input(f'light{index}_tex')
            )
            contribution = self.multiply_color(color, texture)
            # These legacy scrolling-light contributions encode their mask in
            # the colour texture.  Keep them in the colour path so they are
            # not incorrectly gated by the character light mask.
            if emission_strength is not None and contribution is not None:
                emission = self.add_color(
                    self.multiply_color(emission, emission_strength),
                    contribution,
                )
                emission_strength = None
                continue
            emission = self.add_color(emission, contribution)

        if emission is not None and self.has_inputs(
            'light_fall_off_scale',
            'light_fall_off_offset',
        ):
            falloff = self.gen_edge_chain('light_')
            if emission_strength is not None:
                emission_strength = self.multiply_value(emission_strength, falloff)
            else:
                emission = self.multiply_color(emission, falloff)
        return emission, emission_strength

    def map_packed_textures(self):
        for texture in self.material['textures']:
            name = texture['map']
            if name == 'param_light_mask':
                self.packed_components['lightmask'] = (name, 'R')
                continue
            if not name.startswith('param_'):
                continue
            components = name[6:].split('_')
            for index, component in enumerate(components[:4]):
                if component == 'XXX':
                    continue
                channel = ('R', 'G', 'B', 'A')[index]
                self.packed_components[component] = (name, channel)

    def component(self, name):
        mapping = self.packed_components.get(name)
        if mapping is None:
            return None
        texture_name, channel = mapping
        if channel == 'A':
            return self.input(texture_name + '_alpha')
        if texture_name not in self.split_map:
            split = new_separate_rgb(self.shader_tree)
            self.shader_tree.links.new(
                separate_rgb_input(split),
                self.input(texture_name),
            )
            self.split_map[texture_name] = split
        return separate_rgb_output(self.split_map[texture_name], channel)

    def multiply_color(self, first, second):
        if first is None:
            return second
        if second is None:
            return first
        node = new_color_mix(self.shader_tree)
        node.blend_type = 'MULTIPLY'
        color_mix_factor_input(node).default_value = 1.0
        self.shader_tree.links.new(color_mix_color_input(node, 1), first)
        self.shader_tree.links.new(color_mix_color_input(node, 2), second)
        return color_mix_output(node)

    def add_color(self, first, second):
        if first is None:
            return second
        if second is None:
            return first
        node = new_color_mix(self.shader_tree)
        node.blend_type = 'ADD'
        color_mix_factor_input(node).default_value = 1.0
        self.shader_tree.links.new(color_mix_color_input(node, 1), first)
        self.shader_tree.links.new(color_mix_color_input(node, 2), second)
        return color_mix_output(node)

    def mix_color(self, first, second, factor):
        node = new_color_mix(self.shader_tree)
        color_mix_color_input(node, 1).default_value = (1.0, 1.0, 1.0, 1.0)
        if first is not None:
            self.shader_tree.links.new(color_mix_color_input(node, 1), first)
        self.shader_tree.links.new(color_mix_color_input(node, 2), second)
        self.shader_tree.links.new(color_mix_factor_input(node), factor)
        return color_mix_output(node)

    def multiply_value(self, first, second):
        if first is None:
            return second
        if second is None:
            return first
        node = self.shader_tree.nodes.new('ShaderNodeMath')
        node.operation = 'MULTIPLY'
        self.shader_tree.links.new(node.inputs[0], first)
        self.shader_tree.links.new(node.inputs[1], second)
        return node.outputs['Value']

    def has_inputs(self, *names):
        return all(self.input(name) is not None for name in names)

    def gen_edge_chain(self, prefix):
        if self.facing is None:
            layer_weight = self.shader_tree.nodes.new('ShaderNodeLayerWeight')
            layer_weight.inputs['Blend'].default_value = 0.05
            normal = self.input('normal') or self.input('damage_normal')
            if normal is not None:
                self.shader_tree.links.new(layer_weight.inputs['Normal'], normal)
            self.facing = layer_weight.outputs['Facing']

        scale = self.shader_tree.nodes.new('ShaderNodeMath')
        scale.operation = 'MULTIPLY'
        self.shader_tree.links.new(scale.inputs[0], self.facing)
        self.shader_tree.links.new(scale.inputs[1], self.input(prefix + 'fall_off_scale'))

        offset = self.shader_tree.nodes.new('ShaderNodeMath')
        offset.operation = 'ADD'
        self.shader_tree.links.new(offset.inputs[0], scale.outputs['Value'])
        self.shader_tree.links.new(offset.inputs[1], self.input(prefix + 'fall_off_offset'))
        return offset.outputs['Value']


def get_shader(shader_name, option_ignore_errors, material=None):
    del option_ignore_errors  # Unknown shaders are safe now; all schemas come from MDB.
    cache_key = (shader_name, material_signature(material))
    shader = shader_cache.get(cache_key)
    if shader is not None and not str(shader.shader_tree).endswith(' invalid>'):
        return shader
    shader = Shader(shader_name, material)
    shader_cache[cache_key] = shader
    return shader
