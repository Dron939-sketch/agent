export type Locale = "ru" | "en";

export const LOCALES: Locale[] = ["ru", "en"];

export type DictKey =
  | "app.tagline"
  | "nav.chat"
  | "nav.agents"
  | "nav.dashboard"
  | "chat.title"
  | "chat.placeholder"
  | "chat.meta"
  | "chat.greeting"
  | "timeline.title"
  | "timeline.meta"
  | "timeline.placeholder"
  | "timeline.empty"
  | "dashboard.title"
  | "dashboard.hint"
  | "tile.weather"
  | "tile.tasks"
  | "tile.github"
  | "tile.news"
  | "tile.memory"
  | "auth.login"
  | "auth.register"
  | "auth.subtitle"
  | "auth.username"
  | "auth.email"
  | "auth.password"
  | "auth.submit.login"
  | "auth.submit.register"
  | "voice.idle"
  | "voice.recording"
  | "onboarding.step1.title"
  | "onboarding.step1.text"
  | "onboarding.step2.title"
  | "onboarding.step2.text"
  | "onboarding.step3.title"
  | "onboarding.step3.text"
  | "onboarding.next"
  | "onboarding.start"
  | "onboarding.skip"
  | "cmd.placeholder";

export type Dictionary = Record<DictKey, string>;

const ru: Dictionary = {
  "app.tagline": "всемогущий AI-помощник",
  "nav.chat": "Чат",
  "nav.agents": "Агенты",
  "nav.dashboard": "Дашборд",
  "chat.title": "Диалог с Фреди",
  "chat.placeholder": "Спроси Фреди…",
  "chat.meta": "SSE · router · memory",
  "chat.greeting":
    "Привет! Я Фреди. Спроси что-нибудь или скомандуй — я подключу инструменты и память.",
  "timeline.title": "Agent Timeline",
  "timeline.meta": "pipeline · WS live",
  "timeline.placeholder": "Что должен сделать Фреди?",
  "timeline.empty":
    "Здесь появятся шаги мульти-агента: Planner → Researcher → Coder → Critic → Executor",
  "dashboard.title": "Дашборд",
  "dashboard.hint": "перетаскивай плитки",
  "tile.weather": "Погода",
  "tile.tasks": "Задачи",
  "tile.github": "GitHub",
  "tile.news": "Новости",
  "tile.memory": "Память",
  "auth.login": "Вход в Фреди",
  "auth.register": "Регистрация",
  "auth.subtitle": "Продолжи беседу и получи доступ к памяти",
  "auth.username": "Имя пользователя",
  "auth.email": "Email",
  "auth.password": "Пароль",
  "auth.submit.login": "Войти",
  "auth.submit.register": "Создать аккаунт",
  "voice.idle": "Нажми и говори",
  "voice.recording": "Слушаю…",
  "onboarding.step1.title": "Диалог с памятью",
  "onboarding.step1.text":
    "Пиши как другу. Фреди помнит важное между сессиями через векторную память и подмешивает нужный контекст.",
  "onboarding.step2.title": "Мульти-агент pipeline",
  "onboarding.step2.text":
    "Planner → Researcher → Coder → Critic → Executor решают сложные задачи с инструментами и показывают каждый шаг в реальном времени.",
  "onboarding.step3.title": "Всемогущий мозг",
  "onboarding.step3.text":
    "Claude, GPT-4, DeepSeek и локальные модели работают как одна команда с автоматическим fallback.",
  "onboarding.next": "Дальше",
  "onboarding.start": "Поехали",
  "onboarding.skip": "пропустить",
  "cmd.placeholder": "Спроси Фреди или выбери команду…"
};

const en: Dictionary = {
  "app.tagline": "your almighty AI assistant",
  "nav.chat": "Chat",
  "nav.agents": "Agents",
  "nav.dashboard": "Dashboard",
  "chat.title": "Chat with Freddy",
  "chat.placeholder": "Ask Freddy…",
  "chat.meta": "SSE · router · memory",
  "chat.greeting":
    "Hi! I'm Freddy. Ask me anything — I'll pull in tools and memory.",
  "timeline.title": "Agent Timeline",
  "timeline.meta": "pipeline · WS live",
  "timeline.placeholder": "What should Freddy do?",
  "timeline.empty":
    "Multi-agent steps will appear here: Planner → Researcher → Coder → Critic → Executor",
  "dashboard.title": "Dashboard",
  "dashboard.hint": "drag tiles",
  "tile.weather": "Weather",
  "tile.tasks": "Tasks",
  "tile.github": "GitHub",
  "tile.news": "News",
  "tile.memory": "Memory",
  "auth.login": "Sign in to Freddy",
  "auth.register": "Sign up",
  "auth.subtitle": "Keep the conversation going and unlock memory",
  "auth.username": "Username",
  "auth.email": "Email",
  "auth.password": "Password",
  "auth.submit.login": "Sign in",
  "auth.submit.register": "Create account",
  "voice.idle": "Press and talk",
  "voice.recording": "Listening…",
  "onboarding.step1.title": "Chat with memory",
  "onboarding.step1.text":
    "Talk like a friend. Freddy remembers key facts across sessions via vector memory and injects the right context.",
  "onboarding.step2.title": "Multi-agent pipeline",
  "onboarding.step2.text":
    "Planner → Researcher → Coder → Critic → Executor solve hard tasks with tools and show every step live.",
  "onboarding.step3.title": "Almighty brain",
  "onboarding.step3.text":
    "Claude, GPT-4, DeepSeek and local models work as one team with automatic fallback.",
  "onboarding.next": "Next",
  "onboarding.start": "Let's go",
  "onboarding.skip": "skip",
  "cmd.placeholder": "Ask Freddy or run a command…"
};

export const dict: Record<Locale, Dictionary> = { ru, en };
