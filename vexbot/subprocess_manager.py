import sys
import atexit
import signal
from subprocess import Popen, DEVNULL

from sqlalchemy import inspect as _sql_inspect
import sqlalchemy as _alchy
import sqlalchemy.orm as _orm

from vexbot.sql_helper import Base
from vexbot.models import RobotModel


class SubprocessManager:
    def __init__(self, settings_manager=None):
        # this is going to be a list of filepaths
        self._registered = {}
        self._settings = {}
        # these will be subprocesses
        self._subprocess = {}
        atexit.register(self._close_subprocesses)
        signal.signal(signal.SIGINT, self._handle_close_signal)
        signal.signal(signal.SIGTERM, self._handle_close_signal)
        self.blacklist = ['shell', ]
        self._settings_manager = settings_manager

    def _handle_close_signal(self, signum=None, frame=None):
        self._close_subprocesses()
        sys.exit()

    def _close_subprocesses(self):
        """
        signum and frame are part of the signal lib
        """
        for process in self._subprocess.values():
            process.terminate()

    def registered_subprocesses(self):
        """
        returns all possible subprocesses that can be launched
        """
        return tuple(self._registered.keys())

    def register(self, key: str, value, settings: dict=None):
        if settings is None:
            settings = {}
        if self._settings.get(key):
            self._settings[key].update(settings)
        else:
            self._settings[key] = settings
        if key in self.blacklist:
            return
        self._registered[key] = value

    def set_settings_class(self, name, kls):
        update_dict = {'settings_class': kls}
        if self._settings.get(name):
            self._settings[name].update(update_dict)
        else:
            self._settings[name] = update_dict

    # FIXME: API broken
    def update_setting_value(self,
                             name: str,
                             setting_name: str,
                             setting_value):

        try:
            self._settings[name][setting_name] = setting_value
        except KeyError:
            pass

    def get_settings(self, key: str):
        """
        trys to get the settings information for a given subprocess. Passes
        silently when there is no information
        """
        settings = self._settings.get(key)
        return settings

    def _get_dict_from_settings(self, kls=None, configuration=None):
        result = {}
        if configuration is None or kls is None:
            return result

        for attribute in _sql_inspect(kls).attrs:
            key = attribute.key
            if not key in ('filepath', 'args'):
                key = '--' + key

            result[attribute.key] = attribute.value

        return result

    # TODO: add this functionality
    """
    def start_one(self, key, context=None):
        pass
    """

    def start(self, keys: list, context=None):
        """
        starts subprocesses. Can pass in multiple subprocess to start
        """
        for key in keys:
            executable = self._registered.get(key)
            if executable is None:
                continue

            dict_list = [executable, ]
            settings = self._settings.get(key)
            # TODO: Find better way todo this
            settings_class = settings.pop('settings_class')
            setting_values = {}
            if settings_class is not None:
                get_adapter_settings = self._settings_manager.get_adapter_settings
                setting_values = get_adapter_settings(settings_class, context)
                if setting_values is None or not setting_values:
                    continue

            filepath = settings.get('filepath')
            if filepath:
                dict_list.append(filepath)

            args = settings.get('args', [])
            if args:
                dict_list.extend(args)

            # NOTE: want to make sure I'm not messing with the state of 
            # the original dict that's tracked by the subprocess manager
            # TODO: check if recreating dict is neccesairy
            settings = dict(settings)
            # Not sure if this will work
            settings.update(setting_values)

            for k, v in settings.items():
                if k in ('filepath', '_sa_instance_state', 'id', 'robot_id'):
                    continue
                if not k[2:] == '--':
                    k = '--' + k
                dict_list.append(k)
                dict_list.append(v)

            process = Popen(dict_list, stdout=DEVNULL)
            return_code = process.poll()
            if return_code is None:
                self._subprocess[key] = process

    def restart(self, values: list):
        """
        restarts subprocesses managed by the subprocess manager
        """
        for value in values:
            try:
                process = self._subprocess[value]
            except KeyError:
                continue

            process.terminate()
            self.start((value, ))

    def kill(self, values: list):
        """
        kills subprocess that is managed by the subprocess manager.
        If value does not match, quietly passes for now
        """
        for value in values:
            try:
                process = self._subprocess[value]
            except KeyError:
                continue
            process.kill()

    def terminate(self, values: list):
        for value in values:
            try:
                process = self._subprocess[value]
            except KeyError:
                continue
            process.terminate()

    def killall(self):
        """
        Kills every registered subprocess
        """
        for subprocess in self._subprocess.values():
            subprocess.kill()

    def running_subprocesses(self):
        """
        returns all running subprocess names
        """
        results = []
        killed = []
        for name, subprocess in self._subprocess.items():
            poll = subprocess.poll()
            if poll is None:
                results.append(name)
            else:
                killed.append(name)
        if killed:
            for killed_subprocess in killed:
                self._subprocess.pop(killed_subprocess)
        return results
