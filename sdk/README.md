# Freddy SDK — умная говорилка как API

Подключи AI-ассистента Фреди к любому проекту — чат, голос, напоминания.

## Установка

```bash
pip install -e ./sdk
# или из другого проекта:
pip install git+https://github.com/Dron939-sketch/agent.git#subdirectory=sdk
```

## Быстрый старт

```python
from freddy import Freddy

f = Freddy("https://agent-ynlg.onrender.com")
f.login("myuser", "mypassword")

# Текст → умный ответ
reply = f.chat_text("Какая погода завтра?")
print(reply)

# Текст → голос Джарвиса (аудио файл)
f.speak_to_file("Добрый вечер, сэр", "jarvis.ogg")

# Напоминание
f.remind("через 2 часа позвонить маме")
```

## Async

```python
import asyncio
from freddy import AsyncFreddy

async def main():
    async with AsyncFreddy("https://agent-ynlg.onrender.com") as f:
        await f.login("user", "pass")
        
        reply = await f.chat_text("Привет!")
        print(reply)
        
        audio = await f.speak("Системы работают в штатном режиме")
        with open("output.ogg", "wb") as file:
            file.write(audio)

asyncio.run(main())
```

## API

| Метод | Описание |
|---|---|
| `f.chat(msg)` | Текст → умный ответ (dict) |
| `f.chat_text(msg)` | Текст → только текст ответа |
| `f.speak(text)` | Текст → аудио bytes |
| `f.speak_to_file(text, path)` | Текст → аудио файл |
| `f.transcribe(audio_path)` | Аудио → текст (STT) |
| `f.voice_loop(audio_path)` | Аудио → STT → LLM → ответ |
| `f.remind(text)` | NLP-напоминание ("через 2 часа...") |
| `f.list_reminders()` | Список напоминаний |
| `f.set_goal(title)` | Создать цель |
| `f.list_goals()` | Список целей |
| `f.list_habits()` | Список привычек |
| `f.voices()` | Доступные голоса |
| `f.ping()` | Проверка сервера |

## Голоса

```python
# Джарвис (русский, Yandex)
audio = f.speak("Привет", voice="jarvis")

# Джарвис (Fish Audio, облачный)
audio = f.speak("Привет", voice="jarvis_fish")

# Стандартный (Madirus)
audio = f.speak("Привет", voice="madirus")
```

## Пример: Telegram бот с Фреди

```python
from freddy import Freddy
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

f = Freddy("https://agent-ynlg.onrender.com")
f.login("bot_user", "bot_password")

async def handle(update: Update, context):
    reply = f.chat_text(update.message.text)
    await update.message.reply_text(reply)

app = Application.builder().token("BOT_TOKEN").build()
app.add_handler(MessageHandler(filters.TEXT, handle))
app.run_polling()
```
