# CANM Exporter for Blender
# Author: Smileynator

import pprint
import bpy
import mathutils
import numpy as np

from mathutils import Vector
from struct import pack


def get_bone_names():
    bone_names = set()
    # Iterate over all NLA tracks to get the bones inside
    for track in bpy.context.object.animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action:
                for fcurve in strip.action.fcurves:
                    if "pose.bones" in fcurve.data_path:
                        bone_name = fcurve.data_path.split('"')[1]
                        bone_names.add(bone_name)
    return list(bone_names)


def get_bone_data(action, bone_names):
    bones = []
    for bone_name in bone_names:
        bone = {}
        bone['bone_name'] = bone_name
        bone['index'] = bone_names.index(bone['bone_name'])
        data_path_loc = f'pose.bones["{bone_name}"].location'
        data_path_rot = f'pose.bones["{bone_name}"].rotation_quaternion'
        data_path_scale = f'pose.bones["{bone_name}"].scale'
        # Position
        loc_x = action.fcurves.find(data_path_loc, index=0)
        loc_y = action.fcurves.find(data_path_loc, index=1)
        loc_z = action.fcurves.find(data_path_loc, index=2)
        if loc_x and loc_y and loc_z:
            bone['position'] = [loc_x, loc_y, loc_z]
        # Rotation
        rot_x = action.fcurves.find(data_path_rot, index=0)
        rot_y = action.fcurves.find(data_path_rot, index=1)
        rot_z = action.fcurves.find(data_path_rot, index=2)
        rot_w = action.fcurves.find(data_path_rot, index=3)
        if rot_x and rot_y and rot_z and rot_w:
            bone['rotation'] = [rot_x, rot_y, rot_z, rot_w]
        # Scale
        scale_x = action.fcurves.find(data_path_scale, index=0)
        scale_y = action.fcurves.find(data_path_scale, index=1)
        scale_z = action.fcurves.find(data_path_scale, index=2)
        if scale_x and scale_y and scale_z:
            bone['scale'] = [scale_x, scale_y, scale_z]
        # Only append a bone if curves were found
        if any(key in bone for key in ('position', 'rotation', 'scale')):
            bones.append(bone)
    return bones


def get_animations(bone_names):
    actions = []
    for track in bpy.context.object.animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action:
                actions.append(strip.action)
    animations = []
    for action in actions:
        anim = {}
        anim['name'] = action.name
        anim['duration'] = action['duration']
        anim['loop'] = action['loop']
        # Get the max keyframe in action as integer
        max_keyframe = 0
        for fcurve in action.fcurves:
            kf = fcurve.keyframe_points[-1]
            max_keyframe = max(max_keyframe, kf.co[0])
        anim['keyframes'] = round(max_keyframe)
        anim['between_keyframes'] = anim['duration'] / (anim['keyframes'] - 1)
        anim['bone_data'] = get_bone_data(action, bone_names)
        animations.append(anim)
    return animations

def append_channel_from_curve( bone, fcurve, channels):
    channel = {}
    

def get_channels(animations):
    channels = []
    for animation in animations:
        for bone in animation['bone_data']:
            if 'position' in bone:
                append_channel_from_curve(bone, bone['position'], channels)
            if 'rotation' in bone:
                append_channel_from_curve(bone, bone['rotation'], channels)
            if 'scale' in bone:
                append_channel_from_curve(bone, bone['scale'], channels)
    return channels


def write_header(file, bone_names, animations):
    file.write(b'CANM')
    file.write(pack('I', 512))
    # Animation Data
    file.write(pack('I', len(animations)))
    file.write(pack('I', 0))
    # Animation Channels
    channels = 0
    for anim in animations:
        for bone in anim['bone_data']:
            if 'position' in bone:
                channels += 1
            if 'rotation' in bone:
                channels += 1
            if 'scale' in bone:
                channels += 1
    file.write(pack('I', channels))
    file.write(pack('I', 0))
    # Bone names
    file.write(pack('I', len(bone_names)))
    file.write(pack('I', 0))



def save(operator, context, filepath="", **kwargs):
    # Gather all the file parts
    bone_names = get_bone_names()
    animations = get_animations(bone_names)
    channels = get_channels(animations)
    
    with open(filepath, 'wb') as file:
        # Header
        write_header(file, bone_names, animations)
        # Write all Channels
        
        
    return {'FINISHED'}
