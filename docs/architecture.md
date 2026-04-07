# Архитектура

```
┌──────────── Frontend (Next.js 14, R3F, shadcn-style) ─────────┐
│   3D Avatar · Chat Stream · Agent Timeline · ⌘K · Push       │
└───────────────▲────────────────────────────▲──────────────────┘
                │ REST + SSE + WebSocket     │
┌───────────────┴────────────────────────────┴──────────────────┐
│                  FastAPI Gateway                              │
│  /api/auth · /api/chat · /api/agents (REST+WS)                │
│  /api/voice · /api/push · /api/system                         │
├────────────────────────────────────────────────────────────────┤
│  Orchestrator (ReAct + 5-stage Pipeline)                      │
│  ├─ Planner    ├─ Researcher  ├─ Coder                        │
│  ├─ Critic     ├─ Executor    └─ Trace (WS)                   │
├────────────────────────────────────────────────────────────────┤
│  Tool Registry: web · fetch · calc · plugins/*                │
├────────────────────────────────────────────────────────────────┤
│  LLM Router (smart/fast/cheap/local) → Claude / GPT / DS / Ollama │
├────────────────────────────────────────────────────────────────┤
│  Memory: SQL ↔ Qdrant + Embedder (Hash/OpenAI) + Summarizer   │
├────────────────────────────────────────────────────────────────┤
│  Postgres · Redis · Qdrant · Caddy reverse proxy              │
└────────────────────────────────────────────────────────────────┘
```

## Слои

| Пакет | Содержимое |
|---|---|
| `app/core` | конфиг, логирование, sentry |
| `app/db` | SQLAlchemy 2.0 модели + репозитории + async session |
| `app/auth` | argon2 + JWT + AuthService |
| `app/services/llm` | base + adapters + router |
| `app/services/tools` | registry + builtin |
| `app/services/memory` | base + embeddings + sql/inmemory/qdrant + summarizer |
| `app/services/voice` | Deepgram + Yandex |
| `app/services/push` | pywebpush wrapper |
| `app/services/profile` | Varitype KB → system prompt |
| `app/orchestrator` | trace + react + roles + pipeline |
| `app/api` | роутеры FastAPI |
| `frontend/` | Next.js 14 App Router |
