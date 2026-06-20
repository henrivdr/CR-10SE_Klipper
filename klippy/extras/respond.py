# Add 'RESPOND' and 'M118' commands for sending messages to the host
#
# Copyright (C) 2018  Alec Plumb <alec@etherwalker.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

respond_types = {
    'echo': 'echo:',
    'command': '//',
    'error' : '!!',
}

respond_types_no_space = {
    'echo_no_space': 'echo:',
}

class HostResponder:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        # Determine default prefix: allow choice by type key or explicit
        # prefix override. Normalize to the actual marker string.
        default_type = config.getchoice('default_type', respond_types, 'echo')
        raw_prefix = config.get('default_prefix', default_type)
        if raw_prefix in respond_types:
            self.default_prefix = respond_types[raw_prefix]
        elif raw_prefix in respond_types_no_space:
            self.default_prefix = respond_types_no_space[raw_prefix]
        else:
            # allow user to specify an explicit marker
            self.default_prefix = raw_prefix
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('M118', self.cmd_M118, True)
        gcode.register_command('RESPOND', self.cmd_RESPOND, True,
                               desc=self.cmd_RESPOND_help)
    def cmd_M118(self, gcmd):
        msg = gcmd.get_raw_command_parameters()
        if msg:
            gcmd.respond_raw("%s %s" % (self.default_prefix, msg))
        else:
            gcmd.respond_raw(self.default_prefix)
    cmd_RESPOND_help = ("Echo the message prepended with a prefix")
    def cmd_RESPOND(self, gcmd):
        no_space = False
        respond_type = gcmd.get('TYPE', None)
        prefix = self.default_prefix
        if respond_type is not None:
            respond_type = respond_type.lower()
            if respond_type in respond_types:
                prefix = respond_types[respond_type]
            elif respond_type in respond_types_no_space:
                prefix = respond_types_no_space[respond_type]
                no_space = True
            else:
                raise gcmd.error(
                    '{"code": "key309", "msg": "RESPOND TYPE \"%s\" is invalid. Must be one of \'echo\', \'command\', or \'error\'", "values":["%s"]}' % (
                        respond_type, respond_type))
        # Allow explicit PREFIX override; if a key name is provided, map to marker
        prefix = gcmd.get('PREFIX', prefix)
        if prefix in respond_types:
            prefix = respond_types[prefix]
        elif prefix in respond_types_no_space:
            prefix = respond_types_no_space[prefix]
            no_space = True
        msg = gcmd.get('MSG', '')
        if no_space:
            gcmd.respond_raw("%s%s" % (prefix, msg))
        else:
            if msg:
                gcmd.respond_raw("%s %s" % (prefix, msg))
            else:
                gcmd.respond_raw(prefix)

def load_config(config):
    return HostResponder(config)
