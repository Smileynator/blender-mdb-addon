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
        rot_w = action.fcurves.find(data_path_rot, index=0)
        rot_x = action.fcurves.find(data_path_rot, index=1)
        rot_y = action.fcurves.find(data_path_rot, index=2)
        rot_z = action.fcurves.find(data_path_rot, index=3)
        if rot_x and rot_y and rot_z and rot_w:
            bone['rotation'] = [rot_w, rot_x, rot_y, rot_z]
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


def get_curve_values(fcurve, frames):
    values = []
    for i in range(frames):
        values.append(fcurve.evaluate(i+1))
    return values


def convert_to_ushort(array, min, diff):
    if diff == 0:
        # Divide by zero makes no sense, we return zero instead, since there is no animation
        return [0 for val in array]
    return [int(((val - min) * 0xFFFF)/diff) for val in array]


def get_channel_from_curve(animation, fcurves):
    channel = {}
    channel['has_frames'] = True
    channel['keyframes'] = animation['keyframes']
    if len(fcurves[0].keyframe_points) == 1 and fcurves[0].keyframe_points[0].co.x == 1.0:
        # Handle no keyframes
        channel['has_frames'] = False
        channel['keyframes'] = 1
        if len(fcurves) == 4:
            # Quaternion needs to be decomposed
            w = fcurves[0].evaluate(1)
            x = fcurves[1].evaluate(1)
            y = fcurves[2].evaluate(1)
            z = fcurves[3].evaluate(1)
            euler = mathutils.Quaternion((w, x, y, z)).to_euler('XYZ')
            channel['base_x'] = euler.x
            channel['base_y'] = euler.y
            channel['base_z'] = euler.z
        else:
            # Just X Y Z
            channel['base_x'] = fcurves[0].evaluate(1)
            channel['base_y'] = fcurves[1].evaluate(1)
            channel['base_z'] = fcurves[2].evaluate(1)
        channel['speed_x'] = 0.0
        channel['speed_y'] = 0.0
        channel['speed_z'] = 0.0
        # Empty, cause no keyframes
        channel['offsets_x'] = []
        channel['offsets_y'] = []
        channel['offsets_z'] = []
    else:
        # Handle with keyframes
        if len(fcurves) == 4:
            # Quaternion needs to be decomposed
            w = get_curve_values(fcurves[0], channel['keyframes'])
            x = get_curve_values(fcurves[1], channel['keyframes'])
            y = get_curve_values(fcurves[2], channel['keyframes'])
            z = get_curve_values(fcurves[3], channel['keyframes'])
            x_values = []
            y_values = []
            z_values = []
            for i in range(len(w)):
                euler = mathutils.Quaternion((w[i], x[i], y[i], z[i])).to_euler('XYZ')
                x_values.append(euler.x)
                y_values.append(euler.y)
                z_values.append(euler.z)
        else:
            x_values = get_curve_values(fcurves[0], channel['keyframes'])
            y_values = get_curve_values(fcurves[1], channel['keyframes'])
            z_values = get_curve_values(fcurves[2], channel['keyframes'])

        # Process Keyframes per axis now that they are normalized
        values = x_values
        min_val = min(values)
        max_val = max(values)
        diff = max_val - min_val
        channel['base_x'] = min_val
        channel['speed_x'] = diff / 0xFFFF
        channel['offsets_x'] = convert_to_ushort(values, min_val, diff)
        
        values = y_values
        min_val = min(values)
        max_val = max(values)
        diff = max_val - min_val
        channel['base_y'] = min_val
        channel['speed_y'] = diff / 0xFFFF
        channel['offsets_y'] = convert_to_ushort(values, min_val, diff)
        
        values = z_values
        min_val = min(values)
        max_val = max(values)
        diff = max_val - min_val
        channel['base_z'] = min_val
        channel['speed_z'] = diff / 0xFFFF
        channel['offsets_z'] = convert_to_ushort(values, min_val, diff)
    return channel

dupes = 0
ezdupes = 0
harddupes = 0

def are_close(value1, value2, tolerance=1e-6):
    return abs(value1 - value2) < tolerance

def check_duplicate_channel(channels, channel):
    global dupes
    global ezdupes
    global harddupes
    if channel['has_frames'] == False:
        for i in range(len(channels)):
            if are_close(channel['base_x'],channels[i]['base_x']) and \
                are_close(channel['base_y'], channels[i]['base_y']) and \
                are_close(channel['base_z'], channels[i]['base_z']):
                dupes += 1
                ezdupes += 1
                return i
    else:
        for i in range(len(channels)):
            if are_close(channel['base_x'],channels[i]['base_x']) and \
                are_close(channel['base_y'], channels[i]['base_y']) and \
                are_close(channel['base_z'], channels[i]['base_z']) and \
                are_close(channel['speed_x'], channels[i]['speed_x']) and \
                are_close(channel['speed_y'], channels[i]['speed_y']) and \
                are_close(channel['speed_z'], channels[i]['speed_z']) and \
                channel['offsets_x'] == channels[i]['offsets_x'] and \
                channel['offsets_y'] == channels[i]['offsets_y'] and \
                channel['offsets_z'] == channels[i]['offsets_z']:
                dupes += 1
                harddupes += 1
                return i
    return -1


# A channel is X Y Z values of postion, rotation or scale
def get_channels(animations):
    channels = []
    for animation in animations:
        for bone in animation['bone_data']:
            if 'position' in bone:
                channel = get_channel_from_curve(animation, bone['position'])
                bone['channel_index_pos'] = check_duplicate_channel(channels, channel)
                if bone['channel_index_pos'] == -1:
                    bone['channel_index_pos'] = len(channels)
                    channels.append(channel)
            else:
                bone['channel_index_pos'] = -1
            if 'rotation' in bone:
                channel = get_channel_from_curve(animation, bone['rotation'])
                bone['channel_index_rot'] = check_duplicate_channel(channels, channel)
                if bone['channel_index_rot'] == -1:
                    bone['channel_index_rot'] = len(channels)
                    channels.append(channel)
            else:
                bone['channel_index_rot'] = -1
            if 'scale' in bone:
                channel = get_channel_from_curve(animation, bone['scale'])
                bone['channel_index_scale'] = check_duplicate_channel(channels, channel)
                if bone['channel_index_scale'] == -1:
                    bone['channel_index_scale'] = len(channels)
                    channels.append(channel)
            else:
                bone['channel_index_scale'] = -1
        print(f'Chans: {len(channels)} Dupes: {dupes} EZ: {ezdupes} HARD: {harddupes}')
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


def write_channels(file, channels):
    # Write Animatio Channel Data
    for chan in channels:
        chan['base_pos'] = file.tell()
        if chan['has_frames'] == True:
            file.write(pack('h', 0x01))
        else:
            file.write(pack('h', 0x00))
        file.write(pack('H', chan['keyframes']))
        file.write(pack('f', chan['base_x']))
        file.write(pack('f', chan['base_y']))
        file.write(pack('f', chan['base_z']))
        file.write(pack('f', chan['speed_x']))
        file.write(pack('f', chan['speed_y']))
        file.write(pack('f', chan['speed_z']))
        chan['frames_pos'] = file.tell()
        file.write(pack('I', 0))
    # Write the keyframe data for any animations that have them
    for chan in channels:
        if chan['has_frames'] == False:
            continue
        # Replace frame_pos with correct value
        rewrite_offset(file, chan['frames_pos'], file.tell(), chan['base_pos'])
        # Write all keyframes
        for i in range(chan['keyframes']):
            file.write(pack('H', chan['offsets_x'][i]))
            file.write(pack('H', chan['offsets_y'][i]))
            file.write(pack('H', chan['offsets_z'][i]))

# Seeks to the target, writes a file offset relative to the given base, returns to original position
def rewrite_offset(file, rewrite_target, current_position, target_base_offset):
    file.seek(rewrite_target)
    offset = current_position - target_base_offset
    file.write(pack('I', offset))
    file.seek(current_position)


def write_animations(file, animations):
    # Animation data table
    for anim in animations:
        anim['base_pos'] = file.tell()
        file.write(pack('I', anim['loop']))
        anim['name_pos'] = file.tell()
        file.write(pack('I', 0))
        file.write(pack('f', anim['duration']))
        file.write(pack('f', anim['between_keyframes']))
        file.write(pack('I', anim['keyframes']))
        file.write(pack('I', len(anim['bone_data'])))
        anim['bone_data_pos'] = file.tell()
        file.write(pack('I', 0))
    # Bone data table
    for anim in animations:
        # Replace bone_data_pos with correct value
        rewrite_offset(file, anim['bone_data_pos'], file.tell(), anim['base_pos'])
        for bone in anim['bone_data']:
            file.write(pack('h', bone['index']))
            file.write(pack('h', bone['channel_index_pos']))
            file.write(pack('h', bone['channel_index_rot']))
            file.write(pack('h', bone['channel_index_scale']))


def write_bone_names(file, bone_names):
    base_positions = []
    for string in bone_names:
        base_positions.append(file.tell())
        file.write(bytes([0x00, 0x00, 0x00, 0x00]))
    for index, string in enumerate(bone_names):
        # Correct the pointer
        rewrite_offset(file, base_positions[index], file.tell(), base_positions[index])
        # Write string
        file.write(string.encode('UTF-16LE'))
        file.write(bytes([0x00, 0x00]))  # Terminate string


def write_animation_names(file, animations):
    for anim in animations:
        # Replace name_pos with correct value
        rewrite_offset(file, anim['name_pos'], file.tell(), anim['base_pos'])
        # Write string
        file.write(anim['name'].encode('UTF-16LE'))
        file.write(bytes([0x00, 0x00]))  # Terminate string


def save(operator, context, filepath="", **kwargs):
    # Gather all the file parts
    bone_names = get_bone_names()
    animations = get_animations(bone_names)
    channels = get_channels(animations)
    
    with open(filepath, 'wb') as file:
        # Header
        write_header(file, bone_names, animations)
        # Write header Channel Offset
        rewrite_offset(file, 0x14, file.tell(), 0x00)
        # Write all Channels
        write_channels(file, channels)
        # Write header Animations Offset
        rewrite_offset(file, 0x0C, file.tell(), 0x00)
        # Write all Animations
        write_animations(file, animations)
        # Write header Bone Name Offset
        rewrite_offset(file, 0x1C, file.tell(), 0x00)
        # Write All Bone Names
        write_bone_names(file, bone_names)
        # Write All Animation Names
        write_animation_names(file, animations)
    return {'FINISHED'}
