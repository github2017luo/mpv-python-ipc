import sys
from subprocess import PIPE, Popen
from threading  import Thread
import time
from queue import Queue, Empty
import json
from pathlib import Path
import os
from os.path import dirname, realpath
from itertools import chain
mpv_executable = 'mpv'
if os.name == 'nt':
    mpv_executable += '.com'

script_path = Path(dirname(realpath(__file__)))

class MpvStdoutLine(object):

    def __init__(self, raw_line):
        self.raw_line = raw_line
        self.ipc = False
        self.parse_line()

    def parse_line(self):
        try:
            line = self.raw_line.decode()
            if line.startswith("[ipc]"):
                line = json.loads(line.lstrip("[ipc]").strip())
                self.id = line[0]
                self.data = line[1] if line[1:] else None
                self.ipc = True
        except: pass


class MpvProcess(object):

    def __init__(self, debug=False):
        self.debug = debug
        self.process = Popen([mpv_executable,
            '--quiet',
            '--no-term-osd',
            '--input-terminal=no',
            '--input-file=/dev/stdin',
            '--script={}'.format(script_path / 'ipc.lua'),
            '--force-window',
            '--osc=no',
            '--idle'],
            stdout=PIPE, stdin=PIPE, bufsize=1)
        self._init_process()
        self.command_id = 0
        self.data_queues = dict()

    def _init_process(self):
        def enqueue_output(out):
            for line in iter(out.readline, b''):
                parsed_line = MpvStdoutLine(line)
                if parsed_line.ipc and self.data_queues.get(parsed_line.id):
                    self.data_queues[parsed_line.id].put(parsed_line.data)
                if self.debug:
                    print(line)
            out.close()
        t = Thread(target=enqueue_output, args=(self.process.stdout,))
        t.daemon = True
        t.start()

    def _escape_script_binding(self, text):
        allowed_chars = list(chain(
            range(48, 58), # 0-9
            range(65, 91), # A-Z
            range(97, 123), # a-z
        ))
        return ''.join('{{c{}}}'.format(ord(c)) if (ord(c) not in allowed_chars) else c for c in text)

    def slave_command(self, command):
        self.process.stdin.write((command + '\n').encode('utf-8'))
        self.process.stdin.flush()

    def get_property(self, prop, native=False):
        prop = self._escape_script_binding(prop)
        return self._ipc_command('getproperty{}_{}'.format(
            'native' if native else '', prop))

    def get_property_native(self, prop):
        return self.get_property(prop, True)

    def set_property(self, prop, value):
        prop = self._escape_script_binding(prop)
        value = self._escape_script_binding(json.dumps(value))
        return self._ipc_command('setproperty_{}_{}'.format(
            prop, value))

    def _ipc_command(self, command):
        c_id = self.command_id
        self.command_id += 1
        self.data_queues[c_id] = Queue()
        self.process.stdin.write(
            'script_binding {}\n'.format(
                '{}_{}'.format(c_id, command)).encode('utf-8'))
        self.process.stdin.flush()
        try:
            output = self.data_queues[c_id].get(True, 3)
        except Empty:
            output = None
        finally:
            del self.data_queues[c_id]
        return output
