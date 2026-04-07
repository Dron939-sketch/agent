"""Tools subsystem: registry + builtin tools.

Импорт `app.services.tools` автоматически регистрирует встроенные tools.
"""

from . import builtin  # noqa: F401  - регистрирует декораторы при импорте
from .registry import Tool, ToolRegistry, default_registry, tool

__all__ = ["Tool", "ToolRegistry", "default_registry", "tool"]
