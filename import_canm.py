# CANM Animation importer for blender
# Author: Smileynator

import bpy
import mathutils

from mathutils import Vector
from struct import unpack

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
        data['point_scale_id'] = read_short(f)
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
        data['loop'] = True if read_uint(f) == 1 else False
        name = read_int(f)
        data['duration'] = read_float(f)
        data['frame_duration'] = read_float(f)
        data['keyframes'] = read_uint(f)
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
        data['x'] = float(read_ushort(f))
        data['y'] = float(read_ushort(f))
        data['z'] = float(read_ushort(f))
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
        point['base_x'] = read_float(f)
        point['base_y'] = read_float(f)
        point['base_z'] = read_float(f)
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
    file_version = read_uint(f)
    anm_data_count = read_uint(f)
    anm_data_offset = read_uint(f)
    anm_point_count = read_uint(f)
    anm_point_offset = read_uint(f)
    anm_bone_count = read_uint(f)
    anm_bone_offset = read_uint(f)
    
    assert file_signature == b'CANM'

    if override_version != 0:
        file_version = override_version
    else:
        assert file_version == 512


    canm['animations'] = parse_anm_data(f, anm_data_count, anm_data_offset)
    canm['anm_points'] = parse_anm_point(f, anm_point_count, anm_point_offset)
    canm['bone_names'] = parse_bone_names(f, anm_bone_count, anm_bone_offset)

    return canm


def get_bone_matrix_of_frame(canm, bone_anim, i):
    # Get animation data for this bone
    pos_anim = None
    if bone_anim['point_trans_id'] != -1:
        pos_anim = canm['anm_points'][bone_anim['point_trans_id']]
    rot_anim = None
    if bone_anim['point_rot_id'] != -1:
        rot_anim = canm['anm_points'][bone_anim['point_rot_id']]
    scale_anim = None
    if bone_anim['point_scale_id'] != -1:
        scale_anim = canm['anm_points'][bone_anim['point_scale_id']]
    # Generate matrix for this bone
    pos_mat = mathutils.Matrix.Identity(4)
    set_pos = False
    rot_mat = mathutils.Matrix.Identity(4)
    set_rot = False
    scale_mat = mathutils.Matrix.Identity(4)
    set_scale = False
    if i == 0:  # First frame is just the fixed position for most bones, it overrides if it has keyframes
        # Position
        if pos_anim:
            x = pos_anim['base_x']
            y = pos_anim['base_y']
            z = pos_anim['base_z']
            pos_mat = mathutils.Matrix.Translation(Vector((x, y, z)))
            set_pos = True
        # Rotation
        if rot_anim:
            x = mathutils.Matrix.Rotation(rot_anim['base_x'], 4, 'X')
            y = mathutils.Matrix.Rotation(rot_anim['base_y'], 4, 'Y')
            z = mathutils.Matrix.Rotation(rot_anim['base_z'], 4, 'Z')
            rot_mat = z @ y @ x
            set_rot = True
        # Scale (untested!)
        if scale_anim:
            x = scale_anim['base_x']
            y = scale_anim['base_y']
            z = scale_anim['base_z']
            scale_mat = mathutils.Matrix.Scale(1, 4, Vector((x, y, z)))
            set_scale = True
    # If keyframes are present we override frame 0
    # Position
    if pos_anim and len(pos_anim['keyframes']) > i:
        x = pos_anim['base_x'] + pos_anim['keyframes'][i]['x'] * pos_anim['speed_x']
        y = pos_anim['base_y'] + pos_anim['keyframes'][i]['y'] * pos_anim['speed_y']
        z = pos_anim['base_z'] + pos_anim['keyframes'][i]['z'] * pos_anim['speed_z']
        pos_mat = mathutils.Matrix.Translation(Vector((x, y, z)))
        set_pos = True
    # Rotation
    if rot_anim and len(rot_anim['keyframes']) > i:
        x = mathutils.Matrix.Rotation(rot_anim['base_x'] + rot_anim['keyframes'][i]['x'] * rot_anim['speed_x'], 4, 'X')
        y = mathutils.Matrix.Rotation(rot_anim['base_y'] + rot_anim['keyframes'][i]['y'] * rot_anim['speed_y'], 4, 'Y')
        z = mathutils.Matrix.Rotation(rot_anim['base_z'] + rot_anim['keyframes'][i]['z'] * rot_anim['speed_z'], 4, 'Z')
        rot_mat = z @ y @ x
        set_rot = True
    # Scale (untested!)
    if scale_anim and len(scale_anim['keyframes']) > i:
        x = scale_anim['base_x'] + scale_anim['keyframes'][i]['x'] * scale_anim['speed_x']
        y = scale_anim['base_y'] + scale_anim['keyframes'][i]['y'] * scale_anim['speed_y']
        z = scale_anim['base_z'] + scale_anim['keyframes'][i]['z'] * scale_anim['speed_z']
        scale_mat = mathutils.Matrix.Scale(1, 4, Vector((x, y, z)))
        set_scale = True
    # Final local offset matrix
    return_object = {
        'matrix': (pos_mat @ rot_mat @ scale_mat),
        'pos': set_pos,
        'rot': set_rot,
        'scale': set_scale
    }
    return return_object


def create_action_with_animation(armature_obj, animation, canm):
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='POSE')
    # Create a new action for the animation and set it active
    action = bpy.data.actions.new(name=animation['name'])
    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()
    armature_obj.animation_data.action = action
    # Set custom properties up
    action['loop'] = animation['loop']
    action['duration'] = animation['duration']
    action['keyframes'] = animation['keyframes']
    # Get the actual max length of the animation
    keyframes = animation["keyframes"]
    # For each keyframe, generate entire bone structure from the root upward
    for i in range(keyframes):
        # Go over every bone in the armature
        for pose_bone in armature_obj.pose.bones:
            # Get the bone ID
            try:
                bone_index = canm['bone_names'].index(pose_bone.name)
            except ValueError:
                continue  # Skip the bone, unknown bone name
            # Get the correct bone data if any
            bone_anim = None
            for bone_data in animation['bone_data']:
                if bone_data['bone_id'] == bone_index:
                    bone_anim = bone_data
                    break
            if bone_anim is None:
                continue  # Skip the bone, no animations
            # Get Bone Matrix
            matrix_result = get_bone_matrix_of_frame(canm, bone_anim, i)
            # Final local offset matrix
            new_bone_matrix = matrix_result['matrix']
            # Get the parent bone matrix
            if pose_bone.parent:
                parent_bone_matrix = pose_bone.parent.matrix
            else:
                parent_bone_matrix = mathutils.Matrix.Identity(4)
            # Set bone matrix and save keyframes
            pose_bone.matrix = parent_bone_matrix @ new_bone_matrix
            # These need +1 because setting frame 0 and frame 1, both result in frame 1 being set.
            if matrix_result['pos']:
                pose_bone.keyframe_insert(data_path='location', frame=i+1, group=pose_bone.name)
            if matrix_result['rot']:
                pose_bone.keyframe_insert(data_path='rotation_quaternion', frame=i+1, group=pose_bone.name)
            if matrix_result['scale']:
                pose_bone.keyframe_insert(data_path='scale', frame=i+1, group=pose_bone.name)
    # Reset all bone poses
    for pose_bone in armature_obj.pose.bones:
        pose_bone.matrix_basis = mathutils.Matrix.Identity(4)
    # Push action to NLA track and clear the current track
    track = armature_obj.animation_data.nla_tracks.new()
    track.strips.new(action.name, 1, action)
    track.name = animation['name']
    armature_obj.animation_data.action = None


def load(operator, context, filepath='', **kwargs):
    global override_version
    override_version = operator.option_override_version
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
    for animation in canm['animations']:
        # Create action for animation
        create_action_with_animation(armature_object, animation, canm)

    # Warn missing bones and append to armature object
    # TODO Currently assumes the missing bones are identical in each animation
    # TODO will these ever have animations? If so we need to store those too.
    missing_bones = []
    for bone_anim in canm['animations'][0]['bone_data']:
        bone_name = canm['bone_names'][bone_anim['bone_id']]
        pose_bone = armature_object.pose.bones.get(bone_name)
        # Skip bones not found
        if not pose_bone:
            print(f'Could not find bone: {bone_name}. Instead stored in Armature Object.')
            missing_bones.append(bone_name)
    armature_object['missing_bones'] = missing_bones
    
    return {'FINISHED'}
