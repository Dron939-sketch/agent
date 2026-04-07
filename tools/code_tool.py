# tools/code_tool.py
"""
Инструмент для выполнения кода (в песочнице)
"""

import subprocess
import tempfile
import os
import asyncio
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

CODE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": "Execute Python code in a sandboxed environment. Use this when the user wants to run code, test something, or see output.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum execution time in seconds (default 10)",
                    "default": 10
                }
            },
            "required": ["code"]
        }
    }
}


class CodeTool:
    """Инструмент для выполнения кода в песочнице"""
    
    async def execute(self, code: str, timeout_seconds: int = 10) -> Dict[str, Any]:
        """Выполняет код и возвращает результат"""
        
        # Создаём временный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Запускаем процесс с таймаутом
            process = await asyncio.create_subprocess_exec(
                'python3', temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024  # 1MB лимит вывода
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds
                )
                
                return {
                    "success": process.returncode == 0,
                    "stdout": stdout.decode('utf-8', errors='replace')[:10000],
                    "stderr": stderr.decode('utf-8', errors='replace')[:5000],
                    "return_code": process.returncode
                }
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": f"Код выполнялся дольше {timeout_seconds} секунд и был остановлен",
                    "stdout": "",
                    "stderr": ""
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": ""
            }
        finally:
            # Удаляем временный файл
            try:
                os.unlink(temp_file)
            except:
                pass


# Глобальный экземпляр
code_tool = CodeTool()
