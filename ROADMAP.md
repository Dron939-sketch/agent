# Roadmap — путь к «всемогущему» Фреди

## Фаза 1 · Фундамент
- Распилить `main.py` (2071 строка) на пакеты `app/{core,api,db,auth,services,agents,schemas}`.
- Удалить дублирование между `main.py` и отдельными модулями (`database.py`, `auth.py`, `scheduler.py`, `backup_service.py`).
- SQLAlchemy 2.0 async + Alembic; опционально Postgres.
- Стабильный SECRET_KEY, argon2 для паролей, refresh-токены, rate-limit, security headers.
- ruff + mypy + pytest + pre-commit, GitHub Actions.
- README, .env.example, CONTRIBUTING.

## Фаза 2 · Всемогущий мозг
- Абстракция `LLMClient`: Claude / OpenAI / DeepSeek / Ollama + auto-router + fallback.
- Стриминг ответов (SSE/WebSocket).
- Tool-use по стандарту Anthropic/OpenAI; реестр `tools/registry.py`.
- Инструменты: web search (DDG+Tavily), Playwright-браузер, code interpreter sandbox в Docker, files, shell allow-list, email, calendar, Telegram, Notion, GitHub, погода, карты, перевод, OCR, TTS/STT (Whisper+Yandex), генерация изображений (FLUX/DALL·E), генерация видео.
- Векторная память (Qdrant/Chroma) + Redis для краткосрочной.
- Авто-суммаризация диалогов и «профиль» пользователя через Varitype KB.
- Мульти-агент оркестратор: Planner → Researcher → Coder → Critic → Executor.
- Проактивные триггеры: утренний бриф, дедлайны, мониторинг сайтов/цен/новостей.

## Фаза 3 · WOW-фронтенд
- Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui.
- 3D-аватар (React-Three-Fiber) с реакциями на состояние агента.
- Glassmorphism + аврора-градиенты, тёмная тема, неоновые акценты.
- Стриминг ответов с подсветкой кода (Shiki), Markdown/Mermaid/KaTeX/Recharts.
- Agent Timeline — live-визуализация шагов мульти-агента.
- Командная палитра ⌘K (kbar).
- Голосовой режим с визуализацией звуковой волны.
- Dashboard-плитки (dnd-kit): погода, задачи, GitHub, новости.
- Onboarding с микро-интеракциями, конфетти, Lottie.
- PWA, мобильная адаптация, i18n (ru/en).

## Фаза 4 · Продакшн и DevEx
- docker-compose: api + worker (Arq) + redis + qdrant + postgres + frontend + caddy.
- Observability: structlog + OpenTelemetry + Grafana/Loki, Sentry.
- LLM-as-judge оценка качества, A/B промптов, feature flags.
- E2E тесты (Playwright), нагрузочные (Locust).
- MkDocs Material + автогенерация OpenAPI.

## Фаза 5 · Магия
- Plugin SDK (один Python-файл = новый инструмент).
- Workflow-конструктор в UI (drag-and-drop как n8n).
- Marketplace персон на базе Varitype KB.
- Mobile-app (Expo).
- AR-режим (WebXR): аватар Фреди в комнате через камеру.
