# Kinematic input shaper to minimize motion vibrations in XY plane
#
# Copyright (C) 2019-2020  Kevin O'Connor <kevin@koconnor.net>
# Copyright (C) 2020  Dmitry Butyugin <dmbutyugin@google.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import collections
import chelper
from . import shaper_defs

class InputShaperParams:
    def __init__(self, axis, config):
        self.axis = axis
        self.shapers = {s.name : s.init_func for s in shaper_defs.INPUT_SHAPERS}
        shaper_type = config.get('shaper_type', 'mzv')
        self.shaper_type = config.get('shaper_type_' + axis, shaper_type)
        sconfig = shaper_defs.get_shaper_cfg(self.shaper_type)
        if sconfig is None:
            raise config.error(
                    'Unsupported shaper type: %s' % (self.shaper_type,))
        self.damping_ratio = config.getfloat(
                'damping_ratio_' + axis,
                shaper_defs.DEFAULT_DAMPING_RATIO, minval=0.,
                maxval=sconfig.max_damping_ratio)
        self.shaper_freq = config.getfloat('shaper_freq_' + axis, 0., minval=0.)
        # Validate input shaper
        self.get_shaper(error=config.error)
    def update(self, gcmd):
        axis = self.axis.upper()
        shaper_type = gcmd.get('SHAPER_TYPE', None)
        if shaper_type is None:
            shaper_type = gcmd.get('SHAPER_TYPE_' + axis, self.shaper_type)
        sconfig = shaper_defs.get_shaper_cfg(shaper_type.lower())        
        if sconfig is None:
            raise gcmd.error('Unsupported shaper type: %s' % (shaper_type,))
        damping_ratio = gcmd.get_float('DAMPING_RATIO_' + axis,
                                       self.damping_ratio, minval=0.)
        if damping_ratio > sconfig.max_damping_ratio:
            raise gcmd.error(
                    'Too high value of damping_ratio=%.3f for shaper %s'
                    ' on axis %c' % (damping_ratio, shaper_type, axis))
        shaper_freq = gcmd.get_float('SHAPER_FREQ_' + axis,
                                     self.shaper_freq, minval=0.)
        # Validate input shaper
        self.get_shaper(shaper_type.lower(), shaper_freq, damping_ratio,
                        gcmd.error)
        self.damping_ratio = damping_ratio
        self.shaper_type = shaper_type.lower()
        self.shaper_freq = shaper_freq
    def get_shaper(self, shaper_type=None, shaper_freq=None,
                   damping_ratio=None, error=None):
        use_freq = shaper_freq if shaper_freq is not None else self.shaper_freq
        use_damping = damping_ratio if damping_ratio is not None else self.damping_ratio
        if not use_freq:
            A, T = shaper_defs.get_none_shaper()
        else:
            A, T = shaper_defs.init_shaper(shaper_type or self.shaper_type,
                                           use_freq,
                                           use_damping,
                                           error=error)
        return len(A), A, T
    def get_status(self):
        return collections.OrderedDict([
            ('shaper_type', self.shaper_type),
            ('shaper_freq', '%.3f' % (self.shaper_freq,)),
            ('damping_ratio', '%.6f' % (self.damping_ratio,))])

class AxisInputShaper:
    def __init__(self, axis, config):
        self.axis = axis
        self.params = InputShaperParams(axis, config)
        self.n, self.A, self.T = self.params.get_shaper()
        self.saved = None
    def get_name(self):
        return 'shaper_' + self.axis
    def get_shaper(self):
        return self.n, self.A, self.T
    def update(self, gcmd):
        self.params.update(gcmd)
        old_n, old_A, old_T = self.n, self.A, self.T
        self.n, self.A, self.T = self.params.get_shaper()
        return (old_n, old_A, old_T) != (self.n, self.A, self.T)
    def set_shaper_kinematics(self, sk):
        ffi_main, ffi_lib = chelper.get_ffi()
        success = ffi_lib.input_shaper_set_shaper_params(
                sk, self.axis.encode(), self.n, self.A, self.T) == 0
        if not success:
            self.disable_shaping()
            # Retry with shaping disabled
            success = ffi_lib.input_shaper_set_shaper_params(
                    sk, self.axis.encode(), self.n, self.A, self.T) == 0
        return success
    def is_enabled(self):
        return self.n > 0
    def get_step_generation_window(self):
        ffi_main, ffi_lib = chelper.get_ffi()
        return ffi_lib.input_shaper_get_step_generation_window(self.n,
                                                               self.A, self.T)
    def disable_shaping(self):
        if self.saved is None and self.n:
            self.saved = (self.n, self.A, self.T)
        A, T = shaper_defs.get_none_shaper()
        self.n, self.A, self.T = len(A), A, T
    def enable_shaping(self):
        if self.saved is None:
            # Input shaper was not disabled
            return
        self.n, self.A, self.T = self.saved
        self.saved = None
    def report(self, gcmd):
        info = ' '.join(["%s_%s:%s" % (key, self.axis, value)
                         for (key, value) in self.params.get_status().items()])
        gcmd.respond_info(info)

class InputShaper:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.printer.register_event_handler("klippy:connect", self.connect)
        self.toolhead = None
        self.shapers = [AxisInputShaper('x', config),
                        AxisInputShaper('y', config)]
        self.stepper_kinematics = []
        self.orig_stepper_kinematics = []
        # Register gcode commands
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command("SET_INPUT_SHAPER",
                               self.cmd_SET_INPUT_SHAPER,
                               desc=self.cmd_SET_INPUT_SHAPER_help)
        gcode.register_command("UPDATE_INPUT_SHAPER",
                               self.cmd_UPDATE_INPUT_SHAPER,
                               desc=self.cmd_UPDATE_INPUT_SHAPER_help)
    def get_shapers(self):
        return self.shapers
    def connect(self):
        self.toolhead = self.printer.lookup_object("toolhead")
        kin = self.toolhead.get_kinematics()
        # Lookup stepper kinematics
        ffi_main, ffi_lib = chelper.get_ffi()
        steppers = kin.get_steppers()
        # Reset stepper kinematics lists to avoid duplicates on reconnect
        self.stepper_kinematics = []
        self.orig_stepper_kinematics = []
        for s in steppers:
            sk = ffi_main.gc(ffi_lib.input_shaper_alloc(), ffi_lib.free)
            orig_sk = s.set_stepper_kinematics(sk)
            res = ffi_lib.input_shaper_set_sk(sk, orig_sk)
            if res < 0:
                s.set_stepper_kinematics(orig_sk)
                continue
            self.stepper_kinematics.append(sk)
            self.orig_stepper_kinematics.append(orig_sk)
        # Configure initial values
        self.old_delay = 0.
        self._update_input_shaping(error=self.printer.config_error)
    def _update_input_shaping(self, error=None):
        self.toolhead.flush_step_generation()
        new_delay = max([s.get_step_generation_window() for s in self.shapers])
        self.toolhead.note_step_generation_scan_time(new_delay,
                                                     old_delay=self.old_delay)
        failed = []
        for sk in self.stepper_kinematics:
            for shaper in self.shapers:
                if shaper in failed:
                    continue
                if not shaper.set_shaper_kinematics(sk):
                    failed.append(shaper)
        if failed:
            error = error or self.printer.command_error
            raise error("""{"code":"key25", "msg":"Failed to configure shaper(s) %s with given parameters", "values": ["%s"]}"""
                        % (', '.join([s.get_name() for s in failed]), ', '.join([s.get_name() for s in failed])))
        # Store the new delay for next _update_input_shaping call
        self.old_delay = new_delay
    def disable_shaping(self):
        for shaper in self.shapers:
            shaper.disable_shaping()
        self._update_input_shaping()
    def enable_shaping(self):
        for shaper in self.shapers:
            shaper.enable_shaping()
        self._update_input_shaping()
    cmd_SET_INPUT_SHAPER_help = "Set cartesian parameters for input shaper"
    def cmd_SET_INPUT_SHAPER(self, gcmd):
        updated = False
        if gcmd.get_command_parameters():
            for shaper in self.shapers:
                updated |= shaper.update(gcmd)
            if updated:
                self._update_input_shaping()
        for shaper in self.shapers:
            shaper.report(gcmd)
    cmd_UPDATE_INPUT_SHAPER_help = "cmd_UPDATE_INPUT_SHAPER parameters for input shaper"
    def cmd_UPDATE_INPUT_SHAPER(self, gcmd):
        # Re-apply shaper settings without reconnecting hardware
        self._update_input_shaping(error=self.printer.command_error)

def load_config(config):
    return InputShaper(config)
