# Quickstart

## Через docker compose

```bash
git clone https://github.com/dron939-sketch/agent.git
cd agent
cp .env.example .env   # заполни ключи
docker compose up -d --build
```

Открой:
- http://localhost — фронт через Caddy
- http://localhost:8000/health — бекенд

## Локально без Docker

```bash
# Бекенд
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # минимум: DEEPSEEK_API_KEY и SECRET_KEY
python -m app

# Фронт (в другом терминале)
cd frontend
npm install
npm run dev
```

Открой http://localhost:3000.

## Ключи

| Переменная | Назначение | Обязательно |
|---|---|---|
| `DEEPSEEK_API_KEY` | LLM (cheap) | да (или Anthropic/OpenAI) |
| `ANTHROPIC_API_KEY` | Claude (smart) | опц. |
| `OPENAI_API_KEY` | GPT-4 + embeddings | опц. |
| `DEEPGRAM_API_KEY` | STT | опц. |
| `YANDEX_API_KEY` | STT/TTS | опц. |
| `OPENWEATHER_API_KEY` | Погода (плитка) | опц. |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | Web Push | опц. |
| `VAD_MODE` | `webrtc` или `off` | опц. |
| `SECRET_KEY` | JWT-сессии | да |
| `SENTRY_DSN` | Observability | опц. |

## Сгенерировать VAPID-ключи

```bash
python -c "from py_vapid import Vapid01; v = Vapid01(); v.generate_keys(); v.save_key('vapid_priv.pem'); v.save_public_key('vapid_pub.pem')"
```
