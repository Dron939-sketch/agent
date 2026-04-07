"""Plugin SDK Фреди.

Папка `plugins/` в корне репозитория содержит пользовательские плагины:
по одному Python-файлу. Каждый файл может декорировать функции через
`@tool` из `app.services.tools` — они автоматически попадут в реестр
и станут доступны всем агентам.

Пример (`plugins/myplugin.py`):

    from app.services.tools import tool

    @tool(description="Возвращает приветствие.")
    async def hello(name: str) -> str:
        return f"Привет, {name}!"

`load_plugins()` сканирует папку и импортирует всё подряд (декораторы
сами зарегистрируют tools). Безопасный режим: ошибки одного плагина
не валят остальные.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)


def plugins_dir() -> Path:
    return Config.BASE_DIR / "plugins"


def load_plugins() -> list[str]:
    """Загружает все *.py из plugins/ кроме `_*.py` и `__init__.py`.

    Возвращает список имён успешно загруженных модулей.
    """
    folder = plugins_dir()
    folder.mkdir(parents=True, exist_ok=True)
    loaded: list[str] = []
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"freddy_plugins.{path.stem}", path
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded.append(path.stem)
            logger.info("✅ plugin loaded: %s", path.stem)
        except Exception as exc:
            logger.warning("⚠️ plugin %s failed: %s", path.stem, exc)
    return loaded
