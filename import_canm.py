# CANM Animation importer for blender
# Author: Smileynator

import os
import pprint
import bpy
import math
import mathutils
import numpy as np

from mathutils import Vector
from struct import pack, unpack

# Original model is Y UP, but blender is Z UP by default, we convert that here.
bone_up_Y = mathutils.Matrix(((1.0, 0.0, 0.0, 0.0),
                              (0.0, 0.0, -1.0, 0.0),
                              (0.0, 1.0, 0.0, 0.0),
                              (0.0, 0.0, 0.0, 1.0)))

# Read helper functions
def read_ushort(file):
    return unpack('<H', file.read(2))[0]

def read_short(file):
    return unpack('<h', file.read(2))[0]

def read_int(file):
    return unpack('<i', file.read(4))[0]


def read_uint(file):
    return unpack('<I', file.read(4))[0]


def read_float(file):
    return unpack('<f', file.read(4))[0]

def read_wide_str(file):
    data = bytearray()
    while True:
        char = file.read(2)
        if char == b'\0\0':
            break
        data.extend(char)
    return data.decode('utf-16')


def parse_bone_data(f, bone_data_count, bone_data_offset):
    bone_data = []
    f.seek(bone_data_offset)
    for i in range(bone_data_count):
        data = {}
        base = f.tell()
        data['bone_id'] = read_ushort(f)
        data['point_trans_id'] = read_short(f)
        data['point_rot_id'] = read_short(f)
        data['point_unk1_id'] = read_short(f)
        next = f.tell()
        assert next - base == 0x08
        
        bone_data.append(data)
    return bone_data


def parse_anm_data(f, anm_data_count, anm_data_offset):
    anm_data = []
    f.seek(anm_data_offset)
    for i in range(anm_data_count):
        data = {}
        base = f.tell()
        data['loop'] = read_uint(f)  # TODO confirm if loop boolean
        name = read_int(f)
        data['duration'] = read_float(f)
        data['real_dur'] = read_float(f)
        data['keyframe_count'] = read_uint(f)
        bone_data_count = read_uint(f)
        bone_data_offset = read_uint(f)
        next = f.tell()
        assert next - base == 0x1C

        f.seek(base+name)
        data['name'] = read_wide_str(f)
        
        data['bone_data'] = parse_bone_data(f, bone_data_count, base+bone_data_offset)
        
        f.seek(next)
        anm_data.append(data)
    return anm_data


def parse_keyframes(f, keyframe_count, keyframe_offset):
    keyframes = []
    f.seek(keyframe_offset)
    for i in range(keyframe_count):
        data = {}
        base = f.tell()
        data['max_x'] = np.float(read_ushort(f))
        data['max_y'] = np.float(read_ushort(f))
        data['max_z'] = np.float(read_ushort(f))
        next = f.tell()
        assert next - base == 0x06
        keyframes.append(data)
    return keyframes


def parse_anm_point(f, anm_point_count, anm_point_offset):
    anim_points = []
    f.seek(anm_point_offset)
    for i in range(anm_point_count):
        point = {}
        base = f.tell()
        point['keyframe'] = read_ushort(f) == 1
        keyframe_count = read_ushort(f)
        point['trans_x'] = read_float(f)
        point['trans_y'] = read_float(f)
        point['trans_z'] = read_float(f)
        point['speed_x'] = read_float(f)
        point['speed_y'] = read_float(f)
        point['speed_z'] = read_float(f)
        keyframe_offset = read_int(f)
        next = f.tell()
        assert next - base == 0x20

        point['keyframes'] = []
        if point['keyframe']:
            point['keyframes'] = parse_keyframes(f, keyframe_count, base+keyframe_offset)

        f.seek(next)
        anim_points.append(point)
    return anim_points


def parse_bone_names(f, anm_bone_count, anm_bone_offset):
    bone_names = []
    f.seek(anm_bone_offset)
    for i in range(anm_bone_count):
        base = f.tell()
        name = read_int(f)
        next = f.tell()
        assert next - base == 0x4
        f.seek(base+name)
        bone = read_wide_str(f)
        f.seek(next)
        bone_names.append(bone)
    return bone_names


def parse_canm(f):
    canm = {}
    f.seek(0)
    file_signature = f.read(4)
    version = read_uint(f)
    assert file_signature == b'CANM'
    assert version == 512

    anm_data_count = read_uint(f)
    anm_data_offset = read_uint(f)
    anm_point_count = read_uint(f)
    anm_point_offset = read_uint(f)
    anm_bone_count = read_uint(f)
    anm_bone_offset = read_uint(f)

    canm['animations'] = parse_anm_data(f, anm_data_count, anm_data_offset)
    canm['anm_points'] = parse_anm_point(f, anm_point_count, anm_point_offset)
    canm['bone_names'] = parse_bone_names(f, anm_bone_count, anm_bone_offset)

    return canm


def create_action_with_animation(armature_obj, animation, canm):
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='POSE')
    # Create a new action for the animation and set it active
    action = bpy.data.actions.new(name=animation['name'])
    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()
    armature_obj.animation_data.action = action
    # Get the actual max length of the animation
    keyframes = animation["keyframe_count"]
    print(f'Keyframes in {animation["name"]}: {keyframes}')
    # Warn missing bones
    for bone_anim in animation['bone_data']:
        bone_name = canm['bone_names'][bone_anim['bone_id']]
        pose_bone = armature_obj.pose.bones.get(bone_name)
        # Skip bones not found TODO figure out how to store these anyway
        if not pose_bone:
            print(f'Could not find bone: {bone_name}')
            continue
    # For each keyframe, generate entire bone structure from the root upward
    for i in range(keyframes):
        # Reset all bone poses
        for pose_bone in armature_obj.pose.bones:
            pose_bone.matrix_basis = mathutils.Matrix.Identity(4)
        # Read from this frame
        bpy.context.scene.frame_set(i)
        # Go over every bone in the armature
        for pose_bone in armature_obj.pose.bones:
            try:
                bone_index = canm['bone_names'].index(pose_bone.name)
            except ValueError:
                continue  # Skip the bone, no animations
            bone_anim = animation['bone_data'][bone_index]

            # Get animation data for this bone
            pos_anim = None
            if bone_anim['point_trans_id'] != -1:
                pos_anim = canm['anm_points'][bone_anim['point_trans_id']]
            rot_anim = None
            if bone_anim['point_rot_id'] != -1:
                rot_anim = canm['anm_points'][bone_anim['point_rot_id']]
            unk_anim = None
            if bone_anim['point_unk1_id'] != -1:
                unk_anim = canm['anm_points'][bone_anim['point_unk1_id']]
            # Generate matrix for this bone
            # Position
            pos_mat = mathutils.Matrix.Identity(4)
            set_pos = False
            if pos_anim and len(pos_anim['keyframes']) > i:
                x = pos_anim['trans_x'] + pos_anim['keyframes'][i]['max_x'] * pos_anim['speed_x']
                y = pos_anim['trans_y'] + pos_anim['keyframes'][i]['max_y'] * pos_anim['speed_y']
                z = pos_anim['trans_z'] + pos_anim['keyframes'][i]['max_z'] * pos_anim['speed_z']
                pos_mat = mathutils.Matrix.Translation(Vector((x, y, z)))
                set_pos = True
            # Rotation
            rot_mat = mathutils.Matrix.Identity(4)
            set_rot = False
            if rot_anim and len(rot_anim['keyframes']) > i:
                x = mathutils.Matrix.Rotation(rot_anim['trans_x'] + rot_anim['keyframes'][i]['max_x'] * rot_anim['speed_x'], 4, 'X')
                y = mathutils.Matrix.Rotation(rot_anim['trans_y'] + rot_anim['keyframes'][i]['max_y'] * rot_anim['speed_y'], 4, 'Y')
                z = mathutils.Matrix.Rotation(rot_anim['trans_z'] + rot_anim['keyframes'][i]['max_z'] * rot_anim['speed_z'], 4, 'Z')
                rot_mat = x @ y @ z
                set_rot = True
            # Final local offset matrix
            new_bone_matrix = pos_mat @ rot_mat
            # Get the parent bone matrix
            if pose_bone.parent:
                bpy.context.scene.frame_set(i)
                parent_bone_matrix = pose_bone.parent.matrix
            else:
                # Correcting the root for correct UP
                parent_bone_matrix = bone_up_Y
            # Set bone matrix and save keyframes
            pose_bone.matrix = parent_bone_matrix @ new_bone_matrix
            if set_pos:
                pose_bone.keyframe_insert(data_path='location', frame=i)
            if set_rot:
                pose_bone.keyframe_insert(data_path='rotation_quaternion', frame=i)

    # Reset all bone poses
    for pose_bone in armature_obj.pose.bones:
        pose_bone.matrix_basis = mathutils.Matrix.Identity(4)

    # Add action to NLA track and clear the current track
    track = armature_obj.animation_data.nla_tracks.new()
    track.strips.new(action.name, 1, action)
    track.name = animation['name']
    armature_obj.animation_data.action = None


def load(operator, context, filepath='', **kwargs):
    # Parse CANM file
    with open(filepath, 'rb') as f:
        canm = parse_canm(f)
    # Find existing armature to add animation to
    armature = bpy.data.armatures[0]
    if not armature:
        return
    armature_object = None
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and obj.data == armature:
            armature_object = obj
            break

    # Create animation timelines for each animation
    for index, animation in enumerate(canm['animations']):
        if index >= 25:
            break
        print(f'Adding animation {animation["name"]}')
        # Create action for animation
        create_action_with_animation(armature_object, animation, canm)
    return {'FINISHED'}
