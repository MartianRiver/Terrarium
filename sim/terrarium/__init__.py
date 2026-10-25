# Lazy, so the coordinator runs on a bare python without numpy or torch
from typing import TYPE_CHECKING

__all__ = ['Config', 'ConfigError', 'World', 'load']

if TYPE_CHECKING:
    from .config import Config, ConfigError, load
    from .world import World


def __getattr__(name):
    if name in ('Config', 'ConfigError', 'load'):
        from . import config
        return getattr(config, name)
    if name == 'World':
        from .world import World
        return World
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
