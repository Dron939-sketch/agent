"""Сервис резервного копирования SQLite-БД."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from app.core.config import Config
from app.core.logging import get_logger
from app.db import BackupRepository, session_scope

logger = get_logger(__name__)


class BackupService:
    """Копирует data/assistant.db в backups/ и фиксирует запись в БД."""

    def __init__(self, db_path: Path | None = None, backup_dir: Path | None = None) -> None:
        self.db_path = db_path or Config.DATABASE_PATH
        self.backup_dir = backup_dir or Config.BACKUP_DIR

    async def create(self) -> str | None:
        if not self.db_path.exists():
            logger.warning("Backup skipped, source DB missing: %s", self.db_path)
            return None
        Config.ensure_dirs()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.backup_dir / f"backup_{timestamp}.db"
        shutil.copy2(self.db_path, target)
        size = target.stat().st_size

        async with session_scope() as session:
            await BackupRepository(session).add(str(target), size)

        logger.info("Backup created: %s (%d bytes)", target, size)
        return str(target)

    def cleanup(self, days: int = 30) -> int:
        """Удаляет файлы старше N дней."""
        if not self.backup_dir.exists():
            return 0
        threshold = datetime.now().timestamp() - days * 86400
        removed = 0
        for path in self.backup_dir.glob("backup_*.db"):
            if path.stat().st_mtime < threshold:
                path.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.info("Removed %d old backups", removed)
        return removed
