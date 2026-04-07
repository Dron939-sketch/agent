# Фреди — Frontend (Next.js 14)

WOW-интерфейс для всемогущего AI-помощника Фреди.

## Стек
- **Next.js 14** (App Router) + **TypeScript**
- **Tailwind CSS** с glassmorphism + аврора-градиентами + неоновыми акцентами
- **React-Three-Fiber** + `@react-three/drei` — живой 3D-аватар с реакцией на состояние агента
- **Framer Motion** — плавные spring-анимации
- **react-markdown** + remark-gfm — стриминг ответов с Markdown
- **kbar** — командная палитра ⌘K (подключим в PR2)

## Быстрый старт

```bash
cd frontend
npm install
cp ../.env.example .env.local     # при необходимости
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Открыть http://localhost:3000.

Бекенд должен работать параллельно: `python -m app`.

## Структура
```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx      # root layout, тёмная тема
│   │   ├── page.tsx        # главная: аватар + чат + timeline
│   │   └── globals.css     # Tailwind + glassmorphism
│   ├── components/
│   │   ├── avatar/FreddyAvatar.tsx     # R3F 3D-ядро
│   │   ├── chat/ChatPanel.tsx          # SSE-стриминг, markdown
│   │   └── timeline/AgentTimeline.tsx  # WS live-трасса агента
│   └── lib/
│       └── api.ts          # клиент (chat/stream/agents/login)
├── package.json
├── tsconfig.json
├── next.config.mjs
├── tailwind.config.ts
└── Dockerfile
```

## Roadmap фронта (Фаза 3)
- [x] PR1: скелет + 3D-аватар + чат стриминг + Agent Timeline
- [ ] PR2: командная палитра ⌘K, auth-модалка, онбординг
- [ ] PR3: dashboard-плитки (dnd-kit), голосовой режим
- [ ] PR4: PWA, i18n ru/en, мобильная адаптация
```
