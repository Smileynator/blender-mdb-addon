# CANM Exporter for Blender
# Author: Smileynator

import bpy
import mathutils
import numpy as np

from mathutils import Vector
from struct import pack


def get_bone_names():
    #TODO get all the bones that were used in all animations
    pass


def save(operator, context, filepath="", **kwargs):
    # Gather all the file parts
    bone_names = get_bone_names()
    #animations = get_animations()
    #animation_channels = get_channels()
    #with open(filepath, 'wb') as file:
    #    file.write(bytes([0x01, 0x02, 0x03, 0x04]))
    return {'FINISHED'}
