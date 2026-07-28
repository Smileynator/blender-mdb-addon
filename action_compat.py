"""Compatibility helpers for Blender's legacy and slotted Action APIs."""

import bpy


def action_fcurves(action):
    """Return the action's sole CANM curve collection."""
    if hasattr(action, "fcurves"):
        return action.fcurves
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type == 'KEYFRAME' and strip.channelbags:
                return strip.channelbags[0].fcurves
    raise ValueError(f"Action {action.name!r} has no CANM curve channel bag")


def initialize_action_fcurves(action, target):
    """Create and return the curve collection used for an imported action."""
    if hasattr(action, "fcurves"):
        return action.fcurves
    slot = action.slots.new('OBJECT', target.name)
    layer = action.layers.new('CANM')
    strip = layer.strips.new(type='KEYFRAME')
    return strip.channelbags.new(slot).fcurves


def new_fcurve(curves, data_path, index, action_group=None):
    if action_group is None:
        return curves.new(data_path, index=index)
    try:
        return curves.new(data_path, index=index, action_group=action_group)
    except TypeError:
        return curves.new(data_path, index=index)
