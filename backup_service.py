# backup_service.py
import shutil
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

class BackupService:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)
    
    def backup_user_data(self, user_id: str, data: Dict) -> str:
        """Создаёт резервную копию данных пользователя"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{user_id}_{timestamp}.json"
        
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return str(backup_path)
    
    def restore_user_data(self, user_id: str, backup_file: str) -> Dict:
        """Восстанавливает данные пользователя из бэкапа"""
        backup_path = self.backup_dir / backup_file
        with open(backup_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def cleanup_old_backups(self, days: int = 30):
        """Удаляет старые бэкапы"""
        cutoff = datetime.now().timestamp() - (days * 86400)
        for backup in self.backup_dir.glob("*.json"):
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
