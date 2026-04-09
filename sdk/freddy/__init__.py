"""Freddy SDK — умная говорилка как API.

Подключи Фреди к любому проекту:

    from freddy import Freddy

    f = Freddy(url="https://agent-ynlg.onrender.com")
    f.login("user", "password")

    # Текст → умный ответ
    reply = f.chat("Привет!")

    # Текст → голос Джарвиса (bytes)
    audio = f.speak("Добрый вечер, сэр")

    # Голос → ответ голосом
    reply, audio = f.voice_loop("question.wav")
"""

from .client import Freddy, AsyncFreddy

__version__ = "1.0.0"
__all__ = ["Freddy", "AsyncFreddy"]
