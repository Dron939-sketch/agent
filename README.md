# Фреди — Всемогущий AI-помощник

> Автономный персональный ассистент с мульти-агентным мозгом и WOW-интерфейсом.

[![CI](https://github.com/dron939-sketch/agent/actions/workflows/ci.yml/badge.svg)](https://github.com/dron939-sketch/agent/actions/workflows/ci.yml)

## Что это

Фреди — open-source платформа персонального AI-агента:

- 🧠 Мульти-LLM мозг (Claude / OpenAI / DeepSeek / локальные) с авто-роутингом и fallback.
- 🛠️ Богатый набор инструментов: web-поиск, браузер, code interpreter, GitHub, календарь, почта, погода, TTS/STT, генерация изображений.
- 🧬 Долговременная память на векторной БД + профиль пользователя на базе Varitype KB.
- 🤖 Мульти-агент оркестратор (Planner → Researcher → Coder → Critic → Executor) с живой визуализацией шагов.
- 🎨 WOW-интерфейс на Next.js + Three.js + Framer Motion: 3D-аватар, glassmorphism, голосовой режим, ⌘K.
- 📲 PWA, мобильная адаптация, проактивные уведомления, расписание задач.

## Быстрый старт

```bash
git clone https://github.com/dron939-sketch/agent.git
cd agent
cp .env.example .env   # заполните ключи
docker compose up -d
```

Откройте http://localhost:8000.

Подробный план развития — см. [ROADMAP.md](./ROADMAP.md).

## Лицензия

MIT
