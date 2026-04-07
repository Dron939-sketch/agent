"""Минимальные smoke-тесты для нового пакета `app/`."""

from app import __version__
from app.core import Config, get_logger, get_settings, setup_logging


def test_version() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_settings_singleton() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b
    assert isinstance(a, Config)


def test_config_paths_exist() -> None:
    Config.ensure_dirs()
    assert Config.DATA_DIR.exists()
    assert Config.LOGS_DIR.exists()


def test_logger_setup() -> None:
    setup_logging()
    log = get_logger("freddy.test")
    log.info("smoke")
