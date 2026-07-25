# CANM Exporter for Blender
# Author: Smileynator

import bpy
import mathutils

from struct import pack


def get_bone_names(missing_bones):
    bone_names = set()
    # Iterate over all NLA tracks to get the bones inside
    for track in bpy.context.object.animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action:
                for fcurve in strip.action.fcurves:
                    if "pose.bones" in fcurve.data_path:
                        bone_name = fcurve.data_path.split('"')[1]
                        bone_names.add(bone_name)
    if missing_bones:
        for bone_name in missing_bones:
            bone_names.add(bone_name)
    bone_names = list(sorted(bone_names))
    return bone_names


def get_pose_bones(bone_names, armature_object):
    bones = []
    for bone_name in bone_names:
        bones.append(armature_object.pose.bones.get(bone_name))
    return bones


def get_bone_data(action, bone_names, pose_bones):
    bones = []
    for bone_name in bone_names:
        bone = {}
        bone['bone_name'] = bone_name
        bone['index'] = bone_names.index(bone['bone_name'])
        bone['pose_bone'] = pose_bones[bone['index']]
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
        if not any(key in bone for key in ('position', 'rotation', 'scale')):
            bone['is_empty'] = True
        else:
            bone['is_empty'] = False
        # Append bone
        bones.append(bone)
    return bones


def calculate_frame_interval(duration, keyframe_count):
    if keyframe_count <= 0:
        raise ValueError('CANM animations must contain at least one keyframe')
    if keyframe_count == 1:
        return duration
    return duration / (keyframe_count - 1)


def encode_channel_index(index):
    if index == -1:
        return 0xFFFF
    if not 0 <= index < 0xFFFF:
        raise ValueError(
            f'CANM channel index {index} is outside the usable '
            'unsigned 16-bit range 0..65534'
        )
    return index


def validate_channel_count(channels):
    if len(channels) > 0xFFFF:
        raise ValueError(
            f'CANM contains {len(channels)} unique channels; the format '
            'can reference at most 65,535'
        )


def get_animations(bone_names, pose_bones):
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
        anim['keyframes'] = action['keyframes']
        anim['between_keyframes'] = calculate_frame_interval(
            anim['duration'],
            anim['keyframes'],
        )
        anim['bone_data'] = get_bone_data(action, bone_names, pose_bones)
        animations.append(anim)
    return animations


def convert_to_ushort(array, min, diff):
    if diff == 0:
        # Divide by zero makes no sense, we return zero instead, since there is no animation
        return [0 for val in array]
    return [int(((val - min) * 0xFFFF)/diff) for val in array]


def check_duplicate_channel(channels, channel):
    channel_type = channel.get('type')
    if channel_type in (2, 3):
        for index, existing in enumerate(channels):
            if existing.get('type') != channel_type:
                continue
            if channel_type == 2:
                if all(
                    channel[name] == existing[name]
                    for name in ('base_x', 'base_y', 'base_z', 'base_w')
                ):
                    return index
            elif channel['frames'] == existing['frames']:
                return index
        return -1
    if channel['has_frames'] == False:
        for i in range(len(channels)):
            if channels[i].get('type') != channel_type:
                continue
            if channel['base_x'] == channels[i]['base_x'] and \
                channel['base_y'] == channels[i]['base_y'] and \
                channel['base_z'] == channels[i]['base_z']:
                return i
    else:
        for i in range(len(channels)):
            if channels[i].get('type') != channel_type:
                continue
            if channel['base_x'] == channels[i]['base_x'] and \
                channel['base_y'] == channels[i]['base_y'] and \
                channel['base_z'] == channels[i]['base_z'] and \
                channel['speed_x'] == channels[i]['speed_x'] and \
                channel['speed_y'] == channels[i]['speed_y'] and \
                channel['speed_z'] == channels[i]['speed_z'] and \
                channel['offsets_x'] == channels[i]['offsets_x'] and \
                channel['offsets_y'] == channels[i]['offsets_y'] and \
                channel['offsets_z'] == channels[i]['offsets_z']:
                return i
    return -1


# Generate a matrix for every frame of the animation to read out later
def get_matrix_channel_from_curves(animation, bone, version):
    matrix_channels = {}
    matrix_channels['position'] = []
    matrix_channels['rotation'] = []
    matrix_channels['scale'] = []
    
    keyframes = animation['keyframes']
    pos_curves = None
    pos_has_frames = False
    rot_curves = None
    rot_has_frames = False
    scl_curves = None
    scl_has_frames = False
    if 'position' in bone:
        pos_curves = bone['position']
        pos_has_frames = not(len(pos_curves[0].keyframe_points) == 1 and pos_curves[0].keyframe_points[0].co.x == 1.0)
        matrix_channels['position_frames'] = pos_has_frames
    if 'rotation' in bone:
        rot_curves = bone['rotation']
        rot_has_frames = not(len(rot_curves[0].keyframe_points) == 1 and rot_curves[0].keyframe_points[0].co.x == 1.0)
        matrix_channels['rotation_frames'] = rot_has_frames
    if 'scale' in bone:
        scl_curves = bone['scale']
        scl_has_frames = not(len(scl_curves[0].keyframe_points) == 1 and scl_curves[0].keyframe_points[0].co.x == 1.0)
        matrix_channels['scale_frames'] = scl_has_frames

    # Create actual matrix per frame
    last_euler = None
    last_quaternion = None
    for i in range(keyframes):
        pos = mathutils.Vector((0.0, 0.0, 0.0))
        rot = mathutils.Quaternion()
        scl = mathutils.Vector((1.0, 1.0, 1.0))
        if pos_curves is not None:
            if not pos_has_frames:
                x = pos_curves[0].evaluate(1)
                y = pos_curves[1].evaluate(1)
                z = pos_curves[2].evaluate(1)
            else:
                x = pos_curves[0].evaluate(i+1)
                y = pos_curves[1].evaluate(i+1)
                z = pos_curves[2].evaluate(i+1)
            pos = mathutils.Vector((x, y, z))
        if rot_curves is not None:
            if not rot_has_frames:
                w = rot_curves[0].evaluate(1)
                x = rot_curves[1].evaluate(1)
                y = rot_curves[2].evaluate(1)
                z = rot_curves[3].evaluate(1)
            else:
                w = rot_curves[0].evaluate(i+1)
                x = rot_curves[1].evaluate(i+1)
                y = rot_curves[2].evaluate(i+1)
                z = rot_curves[3].evaluate(i+1)
            rot = mathutils.Quaternion((w, x, y, z))
        if scl_curves is not None:
            if not scl_has_frames:
                x = scl_curves[0].evaluate(1)
                y = scl_curves[1].evaluate(1)
                z = scl_curves[2].evaluate(1)
            else:
                x = scl_curves[0].evaluate(i+1)
                y = scl_curves[1].evaluate(i+1)
                z = scl_curves[2].evaluate(i+1)
            scl = mathutils.Vector((x, y, z))
        # Get bone local base matrix
        if bone['pose_bone'] is not None:
            bone_local_matrix = bone['pose_bone'].bone.matrix_local
            if bone['pose_bone'].parent is not None:
                bone_local_matrix = bone['pose_bone'].parent.bone.matrix_local.inverted() @ bone_local_matrix
            # offset from pose
            offset_matrix = mathutils.Matrix.LocRotScale(pos, rot, scl)
            # pose + offset
            final_matrix = bone_local_matrix @ offset_matrix
            p,r,s = final_matrix.decompose()
            # Append final X Y Z values for pos/rot/scl
            if 'position' in bone:
                matrix_channels['position'].append(p)
            if 'rotation' in bone:
                if version == 6:
                    if last_quaternion is not None and r.dot(last_quaternion) < 0:
                        r = -r
                    last_quaternion = r.copy()
                    matrix_channels['rotation'].append(r)
                else:
                    if last_euler:
                        last_euler = r.to_euler('XYZ', last_euler)
                    else:
                        last_euler = r.to_euler('XYZ')
                    matrix_channels['rotation'].append(last_euler)
            if 'scale' in bone:
                matrix_channels['scale'].append(s)
        else:
            # Just an empty matrix for the fake bone
            # TODO: If fake bones do have animations, this needs to be fixed here as well
            matrix_channels['position'].append(pos)
            if version == 6:
                matrix_channels['rotation'].append(rot)
            else:
                matrix_channels['rotation'].append(rot.to_euler('XYZ'))
            matrix_channels['position_frames'] = False
            matrix_channels['rotation_frames'] = False
            # No scale required for these
    return matrix_channels


def round_precision(value):
    return round(value / 2e-06) * 2e-06


# Generate channel data from array of vectors
def vector_to_channel(vector_array, has_frames):
    channel = {}
    channel['has_frames'] = has_frames
    if not has_frames:
        # Handle no keyframes
        channel['keyframes'] = 1
        channel['base_x'] = round_precision(vector_array[0].x)
        channel['base_y'] = round_precision(vector_array[0].y)
        channel['base_z'] = round_precision(vector_array[0].z)
        channel['speed_x'] = 0.0
        channel['speed_y'] = 0.0
        channel['speed_z'] = 0.0
        # Empty, cause no keyframes
        channel['offsets_x'] = []
        channel['offsets_y'] = []
        channel['offsets_z'] = []
    else:
        length = len(vector_array)
        channel['keyframes'] = length
        x_values = []
        y_values = []
        z_values = []
        for i in range(length):
            x_values.append(round_precision(vector_array[i].x))
            y_values.append(round_precision(vector_array[i].y))
            z_values.append(round_precision(vector_array[i].z))

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


def quaternion_to_channel(quaternions, has_frames):
    """Build an EDF6 static or animated quaternion channel."""
    channel = {
        'has_frames': has_frames,
        'type': 3 if has_frames else 2,
        'keyframes': len(quaternions) if has_frames else 1,
        'frames': [],
        'base_x': round_precision(quaternions[0].x),
        'base_y': round_precision(quaternions[0].y),
        'base_z': round_precision(quaternions[0].z),
        'base_w': round_precision(quaternions[0].w),
        'speed_x': 0.0,
        'speed_y': 0.0,
        'speed_z': 0.0,
        'speed_w': 0.0,
    }
    if has_frames:
        channel['frames'] = [
            (
                round_precision(quaternion.x),
                round_precision(quaternion.y),
                round_precision(quaternion.z),
                round_precision(quaternion.w),
            )
            for quaternion in quaternions
        ]
    return channel


# A channel is X Y Z values of postion, rotation or scale
def get_channels(animations, version):
    channels = []
    # Always add the empty position/scale channel first.
    chan = {'has_frames': False, 'keyframes': 1, 'base_x': 0, 'base_y': 0, 'base_z': 0, 'speed_x': 0.0, 'speed_y': 0.0,
            'speed_z': 0.0, 'offsets_x': [], 'offsets_y': [], 'offsets_z': []}
    if version == 6:
        chan.update({
            'type': 0,
            'base_w': 1.0,
            'speed_w': 0.0,
        })
    channels.append(chan)
    if version == 6:
        channels.append({
            'has_frames': False,
            'type': 2,
            'keyframes': 1,
            'frames': [],
            'base_x': 0.0,
            'base_y': 0.0,
            'base_z': 0.0,
            'base_w': 1.0,
            'speed_x': 0.0,
            'speed_y': 0.0,
            'speed_z': 0.0,
            'speed_w': 0.0,
        })
    # Now cover all animation channels
    for animation in animations:
        for bone in animation['bone_data']:
            matrix_channel = get_matrix_channel_from_curves(animation, bone, version)
            # Is we have position, or is_empty, we add the channel.
            # If is_empty AND we have pose bone, we need to ignore the bone, because they omitted data on purpose.
            if 'position' in bone or (bone['is_empty'] and bone['pose_bone'] is None):
                channel = vector_to_channel(matrix_channel['position'], matrix_channel['position_frames'])
                if version == 6:
                    channel.update({
                        'type': 1 if channel['has_frames'] else 0,
                        'base_w': 1.0,
                        'speed_w': 0.0,
                    })
                bone['channel_index_pos'] = check_duplicate_channel(channels, channel)
                if bone['channel_index_pos'] == -1:
                    bone['channel_index_pos'] = len(channels)
                    channels.append(channel)
            else:
                bone['channel_index_pos'] = -1

            if 'rotation' in bone or (bone['is_empty'] and bone['pose_bone'] is None):
                if version == 6:
                    channel = quaternion_to_channel(
                        matrix_channel['rotation'],
                        matrix_channel['rotation_frames'],
                    )
                else:
                    channel = vector_to_channel(
                        matrix_channel['rotation'],
                        matrix_channel['rotation_frames'],
                    )
                bone['channel_index_rot'] = check_duplicate_channel(channels, channel)
                if bone['channel_index_rot'] == -1:
                    bone['channel_index_rot'] = len(channels)
                    channels.append(channel)
            else:
                bone['channel_index_rot'] = -1

            if 'scale' in bone:
                channel = vector_to_channel(matrix_channel['scale'], matrix_channel['scale_frames'])
                if version == 6:
                    channel.update({
                        'type': 1 if channel['has_frames'] else 0,
                        'base_w': 1.0,
                        'speed_w': 0.0,
                    })
                bone['channel_index_scale'] = check_duplicate_channel(channels, channel)
                if bone['channel_index_scale'] == -1:
                    bone['channel_index_scale'] = len(channels)
                    channels.append(channel)
            else:
                bone['channel_index_scale'] = -1
    return channels


def write_header(file, file_version, bone_names, animations, channels):
    file.write(b'CANM')
    file.write(pack('I', file_version))
    # Animation Data
    file.write(pack('I', len(animations)))
    file.write(pack('I', 0))
    # Animation Channels
    file.write(pack('I', len(channels)))
    file.write(pack('I', 0))
    # Bone names
    file.write(pack('I', len(bone_names)))
    file.write(pack('I', 0))


def write_channels(file, channels):
    # Write Animation Channel Data
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
    # Padding to nearest 4
    padding_needed = (4 - (file.tell() % 4)) % 4
    file.write(b'\0' * padding_needed)


def write_channels6(file, channels):
    """Write EDF6 0x30-byte channels and their grouped keyframe blocks."""
    for channel in channels:
        channel['base_pos'] = file.tell()
        file.write(pack('f', channel['base_x']))
        file.write(pack('f', channel['base_y']))
        file.write(pack('f', channel['base_z']))
        file.write(pack('f', channel['base_w']))
        file.write(pack('f', channel['speed_x']))
        file.write(pack('f', channel['speed_y']))
        file.write(pack('f', channel['speed_z']))
        file.write(pack('f', channel['speed_w']))
        channel['frames_pos'] = file.tell()
        file.write(pack('I', 0))
        file.write(pack('i', channel['type']))
        file.write(pack('i', channel['keyframes']))
        file.write(pack('i', 0))

    for channel in channels:
        if channel['keyframes'] <= 1 or channel['type'] != 1:
            continue
        rewrite_offset(
            file,
            channel['frames_pos'],
            file.tell(),
            channel['base_pos'],
        )
        for index in range(channel['keyframes']):
            file.write(pack('H', channel['offsets_x'][index]))
            file.write(pack('H', channel['offsets_y'][index]))
            file.write(pack('H', channel['offsets_z'][index]))

    # EDF6 begins the absolute quaternion block at a 16-byte aligned
    # absolute file offset.
    padding_needed = (16 - (file.tell() % 16)) % 16
    file.write(b'\0' * padding_needed)
    for channel in channels:
        if channel['keyframes'] <= 1 or channel['type'] != 3:
            continue
        rewrite_offset(
            file,
            channel['frames_pos'],
            file.tell(),
            channel['base_pos'],
        )
        for quaternion in channel['frames']:
            file.write(pack('4f', *quaternion))


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
            file.write(pack('H', encode_channel_index(bone['channel_index_pos'])))
            file.write(pack('H', encode_channel_index(bone['channel_index_rot'])))
            file.write(pack('H', encode_channel_index(bone['channel_index_scale'])))


def write_all_strings(file, bone_names, animations):
    base_positions = []
    # Create string table for bones
    for string in bone_names:
        base_positions.append(file.tell())
        file.write(bytes([0x00, 0x00, 0x00, 0x00]))
    # Create fill list with offsets
    name_list = []
    for index, string in enumerate(bone_names):
        name_obj = {}
        name_obj['string'] = string
        name_obj['base'] = base_positions[index]
        name_obj['replace'] = base_positions[index]
        name_list.append(name_obj)
    for anim in animations:
        name_obj = {}
        name_obj['string'] = anim['name']
        name_obj['base'] = anim['base_pos']
        name_obj['replace'] = anim['name_pos']
        name_list.append(name_obj)

    # Sort the list
    sorted_list = sorted(name_list, key=lambda x: x['string'])

    def write_str_obj(file, obj):
        # Replace name_pos with correct value
        rewrite_offset(file, obj['replace'], file.tell(), obj['base'])
        # Write string
        file.write(obj['string'].encode('UTF-16LE'))
        file.write(bytes([0x00, 0x00]))  # Terminate string

    # Write to file, scene root first
    for obj in sorted_list:
        if obj['string'] != 'Scene_Root':
            continue
        write_str_obj(file, obj)
    for obj in sorted_list:
        if obj['string'] == 'Scene_Root':
            continue
        write_str_obj(file, obj)


def save(operator, context, filepath="", version=0, **kwargs):
    assert version in (5, 6)
    file_version = 512 if version == 5 else 768
    # Get the armature
    armature = bpy.data.armatures[0]
    if not armature:
        print("Armature not found")
        return {'CANCELLED'}
    armature_object = None
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and obj.data == armature:
            armature_object = obj
            break
    if armature_object is None:
        print("Armature Object not found")
        return {'CANCELLED'}
    # Gather all the file parts
    missing_bones = armature_object.get('missing_bones')
    bone_names = get_bone_names(missing_bones)
    pose_bones = get_pose_bones(bone_names, armature_object)
    animations = get_animations(bone_names, pose_bones)
    channels = get_channels(animations, version)
    validate_channel_count(channels)
    with open(filepath, 'wb') as file:
        # Header
        write_header(file, file_version, bone_names, animations, channels)
        # Write header Channel Offset
        rewrite_offset(file, 0x14, file.tell(), 0x00)
        # Write all Channels
        if version == 6:
            write_channels6(file, channels)
        else:
            write_channels(file, channels)
        # Write header Animations Offset
        rewrite_offset(file, 0x0C, file.tell(), 0x00)
        # Write all Animations
        write_animations(file, animations)
        # Write header Bone Name Offset
        rewrite_offset(file, 0x1C, file.tell(), 0x00)
        # Write All strings
        write_all_strings(file, bone_names, animations)
    return {'FINISHED'}
