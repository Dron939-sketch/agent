# Интеграция Freddy SDK в Frederick (Фреди-психолог)

## Что делает

Для пользователей **без пройденного теста** (BasicMode) — вместо простого DeepSeek
используется полноценный Freddy AI с памятью, эмоциями, голосом Джарвиса.

## Установка

### 1. Скопируй файл в Frederick

```bash
cp freddy_service.py /path/to/Frederick/backend/services/freddy_service.py
```

### 2. Добавь переменные в .env

```env
# Freddy AI Assistant
FREDDY_URL=https://agent-ynlg.onrender.com
FREDDY_USERNAME=frederick_bot
FREDDY_PASSWORD=пароль_бота
# ИЛИ напрямую токен:
# FREDDY_TOKEN=eyJhbGci...
```

### 3. Добавь в render.yaml (envVars секция backend)

```yaml
- key: FREDDY_URL
  value: https://agent-ynlg.onrender.com
- key: FREDDY_USERNAME
  sync: false
- key: FREDDY_PASSWORD
  sync: false
```

### 4. Измени main.py — заменить BasicMode на Freddy

В файле `backend/main.py`, в функции `chat()` (строка ~1322), замени:

**Было:**
```python
if not has_profile:
    mode_name = "basic"
    logger.info(f"🎭 User {data.user_id} has no profile → BasicMode")
```

**Стало:**
```python
if not has_profile:
    # Пробуем Freddy AI (умная говорилка с памятью и голосом)
    from services.freddy_service import get_freddy_service
    freddy = get_freddy_service()
    
    freddy_result = await freddy.chat(data.user_id, data.message, history=history)
    
    if freddy_result.get("reply"):
        # Freddy ответил — используем его
        await message_repo.save(data.user_id, "user", data.message)
        await message_repo.save(data.user_id, "assistant", freddy_result["reply"])
        
        # Счётчик для предложения теста
        msg_count = context_obj.get('_basic_msg_count', 0) + 1
        context_obj['_basic_msg_count'] = msg_count
        await context_repo.save(data.user_id, context_obj)
        
        # Предложение теста после 4 сообщений (как в BasicMode)
        response_text = freddy_result["reply"]
        if msg_count == 4 and not context_obj.get("basic_test_offered"):
            response_text += "\n\nКстати... У меня есть небольшой тест — минут на десять. Он помогает понять себя глубже. Попробуешь?"
            context_obj["basic_test_offered"] = True
            await context_repo.save(data.user_id, context_obj)
        
        return {
            "success": True,
            "response": response_text,
            "mode": "freddy",
            "model": freddy_result.get("model", "freddy"),
            "emotion": freddy_result.get("emotion"),
            "tone": freddy_result.get("tone"),
        }
    
    # Fallback на BasicMode если Freddy недоступен
    mode_name = "basic"
    logger.info(f"🎭 User {data.user_id} → Freddy unavailable, fallback to BasicMode")
```

### 5. Для голоса — замени TTS на Freddy в voice endpoint

В `main.py`, в WebSocket `/ws/voice/{user_id}`, после получения ответа:

```python
# Озвучиваем голосом Джарвиса через Freddy
from services.freddy_service import get_freddy_service
freddy = get_freddy_service()
audio_bytes = await freddy.speak(response_text, voice="jarvis")
if audio_bytes:
    # Отправляем аудио клиенту
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    await websocket.send_json({"type": "audio", "data": audio_b64})
```

## Результат

| До (BasicMode) | После (Freddy) |
|---|---|
| DeepSeek напрямую | Claude/GPT-4 через роутер |
| Нет памяти между сессиями | Помнит всё о пользователе |
| Нет эмоций | Определяет эмоции, адаптирует тон |
| Yandex TTS filipp | Голос Джарвиса (Fish Audio) |
| Нет напоминаний | Напоминания, задачи |
| Нет контекста | Время суток, погода, привычки |
