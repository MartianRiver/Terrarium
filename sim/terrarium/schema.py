# What a brain sees and does, by name and in order. The lists only ever grow at
# the end (docs/releasing.md): a new input or action gets zero weights and a new
# kind a zero embedding, so a brain trained on shorter lists loads and behaves
# the same until training starts using them. Bump VERSION whenever one grows.
#
# The number of rays isn't part of it: each ray is its own token, so a brain
# works with however many the config casts.

VERSION = 15
SELF = ('energy', 'forward_speed', 'side_speed', 'last_thrust', 'last_turn',
        'home_distance', 'home_sin', 'home_cos', 'carrying', 'at_home', 'store', 'light', 'sprinting', 'rested',
        'holding', 'smell', 'smell_sin', 'smell_cos', 'nectar', 'load', 'young',
        'it', 'seeker', 'waiting', 'flag', 'flag_distance', 'flag_sin', 'flag_cos', 'flag_taken',
        'own_flag', 'own_flag_distance', 'own_flag_sin', 'own_flag_cos', 'stamina',
        'heard', 'heard_sin', 'heard_cos', 'dirty', 'dung_load')
RAY = ('distance', 'sin', 'cos', 'nestmate', 'own_nest', 'other_nest', 'it', 'carrier')
# what a ray hit, in vision's order
KINDS = ('nothing', 'wall', 'creature', 'food', 'block', 'flower', 'dung')
ACTIONS = ('thrust', 'turn', 'unload', 'eat', 'sprint', 'grab', 'carry')
# yes when above 0; a new one starts leaning no (brain.py), so it's tried now and then rather than on every other tick
YES_NO = ('unload', 'eat', 'sprint', 'grab', 'carry')

LISTS = ('self', 'ray', 'kinds', 'actions')


class SchemaError(ValueError):
    pass


def current() -> dict:
    return {'version': VERSION, 'self': list(SELF), 'ray': list(RAY), 'kinds': list(KINDS), 'actions': list(ACTIONS)}


def check(saved: dict):
    """Refuse a brain whose lists aren't the start of today's, saying where they part."""
    now = current()
    for key in LISTS:
        old, new = saved[key], now[key]
        for i, (a, b) in enumerate(zip(old, new)):
            if a != b:
                raise SchemaError(f'{key}[{i}] is {a!r} in the brain (schema v{saved["version"]}) but {b!r} here (v{VERSION})')
        if len(old) > len(new):
            raise SchemaError(f'the brain (schema v{saved["version"]}) has {key} this code doesn\'t (v{VERSION}): '
                              f'{", ".join(old[len(new):])}')
