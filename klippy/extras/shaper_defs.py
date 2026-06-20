# Definitions of the supported input shapers
#
# Copyright (C) 2020-2021  Dmitry Butyugin <dmbutyugin@google.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import collections, math, re

SHAPER_VIBRATION_REDUCTION=20.
DEFAULT_DAMPING_RATIO = 0.1

InputShaperCfg = collections.namedtuple(
        'InputShaperCfg', ('name', 'init_func', 'min_freq', 'max_damping_ratio'))

class ShaperError(Exception):
    pass

def get_none_shaper():
    return ([], [])

def get_zv_shaper(shaper_freq, damping_ratio):
    df = math.sqrt(1. - damping_ratio**2)
    K = math.exp(-damping_ratio * math.pi / df)
    t_d = 1. / (shaper_freq * df)
    A = [1., K]
    T = [0., .5*t_d]
    return (A, T)

def get_zvd_shaper(shaper_freq, damping_ratio):
    df = math.sqrt(1. - damping_ratio**2)
    K = math.exp(-damping_ratio * math.pi / df)
    t_d = 1. / (shaper_freq * df)
    A = [1., 2.*K, K**2]
    T = [0., .5*t_d, t_d]
    return (A, T)

def get_mzv_shaper(shaper_freq, damping_ratio):
    df = math.sqrt(1. - damping_ratio**2)
    K = math.exp(-.75 * damping_ratio * math.pi / df)
    t_d = 1. / (shaper_freq * df)

    a1 = 1. - 1. / math.sqrt(2.)
    a2 = (math.sqrt(2.) - 1.) * K
    a3 = a1 * K * K

    A = [a1, a2, a3]
    T = [0., .375*t_d, .75*t_d]
    return (A, T)

def get_ei_shaper(shaper_freq, damping_ratio):
    v_tol = 1. / SHAPER_VIBRATION_REDUCTION # vibration tolerance
    df = math.sqrt(1. - damping_ratio**2)
    K = math.exp(-damping_ratio * math.pi / df)
    t_d = 1. / (shaper_freq * df)

    a1 = .25 * (1. + v_tol)
    a2 = .5 * (1. - v_tol) * K
    a3 = a1 * K * K

    A = [a1, a2, a3]
    T = [0., .5*t_d, t_d]
    return (A, T)

def get_2hump_ei_shaper(shaper_freq, damping_ratio):
    v_tol = 1. / SHAPER_VIBRATION_REDUCTION # vibration tolerance
    df = math.sqrt(1. - damping_ratio**2)
    K = math.exp(-damping_ratio * math.pi / df)
    t_d = 1. / (shaper_freq * df)

    V2 = v_tol**2
    X = pow(V2 * (math.sqrt(1. - V2) + 1.), 1./3.)
    a1 = (3.*X*X + 2.*X + 3.*V2) / (16.*X)
    a2 = (.5 - a1) * K
    a3 = a2 * K
    a4 = a1 * K * K * K

    A = [a1, a2, a3, a4]
    T = [0., .5*t_d, t_d, 1.5*t_d]
    return (A, T)

def get_3hump_ei_shaper(shaper_freq, damping_ratio):
    v_tol = 1. / SHAPER_VIBRATION_REDUCTION # vibration tolerance
    df = math.sqrt(1. - damping_ratio**2)
    K = math.exp(-damping_ratio * math.pi / df)
    t_d = 1. / (shaper_freq * df)

    K2 = K*K
    a1 = 0.0625 * (1. + 3. * v_tol + 2. * math.sqrt(2. * (v_tol + 1.) * v_tol))
    a2 = 0.25 * (1. - v_tol) * K
    a3 = (0.5 * (1. + v_tol) - 2. * a1) * K2
    a4 = a2 * K2
    a5 = a1 * K2 * K2

    A = [a1, a2, a3, a4, a5]
    T = [0., .5*t_d, t_d, 1.5*t_d, 2.*t_d]
    return (A, T)

def get_shaper_cfg(shaper_name):
    m = re.match(r"(\w+)\s*\((.*)\)$", shaper_name)
    if m:
        shaper_name = m.group(1)
    for s in INPUT_SHAPERS:
        if shaper_name == s.name:
            return s
    return None

def init_shaper(shaper_name, shaper_freq, damping_ratio, error=None):
    try:
        m = re.match(r"(\w+)\s*\((.*)\)$", shaper_name)
        args_l = []
        args_kv = {}
        if m:
            shaper_name = m.group(1)
            args = m.group(2)
            if args:
                parsed_args = re.findall(r"(?:(\w+)\s*=\s*)?\s*([\d.]+)", args)
                def parse_val(s):
                    if '.' in s:
                        return float(s)
                    return int(s)
                args_l = [parse_val(v) for k, v in parsed_args if not k]
                args_kv = {k: parse_val(v) for k, v in parsed_args if k}
                if args_l and args_kv:
                    raise ShaperError("Mixing named and non-named shaper"
                                      " parameters is not supported")
        for s in INPUT_SHAPERS:
            if shaper_name == s.name:
                return s.init_func(shaper_freq, damping_ratio,
                                   *args_l, **args_kv)
    except ShaperError as e:
        if error is None:
            raise
        raise error("Failed to initialize shaper: %s" % str(e))
    return None

# min_freq for each shaper is chosen to have projected max_accel ~= 1500
INPUT_SHAPERS = [
    InputShaperCfg('zv', get_zv_shaper, min_freq=21., max_damping_ratio=0.99),
    InputShaperCfg('mzv', get_mzv_shaper, min_freq=23., max_damping_ratio=0.99),
    InputShaperCfg('zvd', get_zvd_shaper, min_freq=29., max_damping_ratio=0.99),
    InputShaperCfg('ei', get_ei_shaper, min_freq=29., max_damping_ratio=0.4),
    InputShaperCfg('2hump_ei', get_2hump_ei_shaper, min_freq=39., max_damping_ratio=0.3),
    InputShaperCfg('3hump_ei', get_3hump_ei_shaper, min_freq=48., max_damping_ratio=0.2),
]
