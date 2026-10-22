# [LEVEL] [module] message {data}, to stderr. TERRARIUM_LOG sets the level
# (TRACE, DEBUG, INFO, WARN, ERROR); INFO when unset.

import json
import logging
import os
import sys

TRACE = 5
logging.addLevelName(TRACE, 'TRACE')
logging.addLevelName(logging.WARNING, 'WARN')

_root = logging.getLogger('terrarium')


class _Format(logging.Formatter):
    def format(self, record):
        line = f'[{record.levelname}] [{record.name.removeprefix("terrarium.")}] {record.getMessage()}'
        data = getattr(record, 'data', None)
        if data:
            line += ' ' + json.dumps(data, default=str)
        if record.exc_info:
            line += '\n' + self.formatException(record.exc_info)
        return line


def _setup():
    if _root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Format())
    _root.addHandler(handler)
    _root.propagate = False
    name = os.environ.get('TERRARIUM_LOG', 'INFO').upper()
    _root.setLevel(logging.getLevelNamesMapping().get(name, logging.INFO))


class Logger:
    def __init__(self, module: str):
        _setup()
        self._log = logging.getLogger(f'terrarium.{module}')

    def _emit(self, level, message, data, exc=False):
        if self._log.isEnabledFor(level):
            self._log.log(level, message, extra={'data': data}, exc_info=exc)

    def trace(self, message, **data):
        self._emit(TRACE, message, data)

    def debug(self, message, **data):
        self._emit(logging.DEBUG, message, data)

    def info(self, message, **data):
        self._emit(logging.INFO, message, data)

    def warn(self, message, **data):
        self._emit(logging.WARNING, message, data)

    def error(self, message, exc=False, **data):
        self._emit(logging.ERROR, message, data, exc)
