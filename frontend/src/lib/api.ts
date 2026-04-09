"use client";

export type ChatMessage = { role: "user" | "assistant" | "system"; content: string };

export type AgentStep = {
  kind: string;
  agent: string;
  content?: string;
  tool?: string | null;
  args?: Record<string, unknown> | null;
  timestamp?: number;
};

export type AgentEvent =
  | { type: "step"; step: AgentStep }
  | { type: "done"; answer: string }
  | { type: "error"; message: string };

export type EmotionTopItem = { name: string; raw: string; score: number };
export type VoiceEmotion = {
  primary: string;
  primary_raw: string;
  intensity: number;
  confidence: number;
  top_5: EmotionTopItem[];
};

export type TextEmotion = {
  primary: string;
  confidence: number;
  intensity: number;
  needs_support: boolean;
  tone: string;
  scores?: Record<string, number>;
};

export type FullLoopResponse = {
  transcript: string;
  transcript_provider: string;
  voice_emotion: VoiceEmotion | null;
  text_emotion: TextEmotion | null;
  fused_emotion: string | null;
  fused_tone: string | null;
  reply: string;
  reply_model: string;
  intent: string | null;
  audio_url: string | null;
};

export type VoiceInfo = {
  id: string;
  label: string;
  gender?: string | null;
  accent?: string | null;
  default?: boolean;
};

/** Sprint 5: события стрима — токен (для UI) или предложение (для TTS). */
export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "sentence"; text: string };

export function resolveApiUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, "");

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host.includes("agent-frontend") || host === "agent-ynlg.onrender.com") {
      return "https://agent-ynlg.onrender.com";
    }
    if (host === "localhost" || host === "127.0.0.1") {
      return "http://localhost:8000";
    }
    return "https://agent-ynlg.onrender.com";
  }
  return "http://localhost:8000";
}

// `API` резолвится лениво через геттер-функцию: никакого module-init side
// effect-а, никаких TDZ на chunk split'ах. Все функции ниже используют
// apiBase() вместо top-level const API = resolveApiUrl().
let _apiBaseCache: string | null = null;
function apiBase(): string {
  if (_apiBaseCache === null) _apiBaseCache = resolveApiUrl();
  return _apiBaseCache;
}

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("freddy_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("freddy_token");
}

// === Chat ===

export async function sendChat(
  message: string,
  opts: { profile?: string; useMemory?: boolean } = {}
): Promise<{
  reply: string;
  model: string;
  recalled: string[];
  emotion?: string;
  tone?: string;
  message_id?: number;
}> {
  const res = await fetch(`${apiBase()}/api/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      message,
      profile: opts.profile ?? "smart",
      use_memory: opts.useMemory ?? true
    })
  });
  if (!res.ok) throw new Error(`chat ${res.status}: ${await res.text()}`);
  return res.json();
}

/**
 * Sprint 5: streamChatEvents — поддерживает оба типа событий из SSE.
 *
 * Сервер шлёт `data: {"t": "..."}` для UI-токенов и `data: {"s": "..."}`
 * для готовых предложений. Фронт может одновременно показывать токены
 * в bubble И запускать TTS для каждого предложения.
 */
export async function streamChatEvents(
  message: string,
  onEvent: (evt: StreamEvent) => void,
  opts: { profile?: string; useMemory?: boolean } = {}
): Promise<void> {
  const res = await fetch(`${apiBase()}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      message,
      profile: opts.profile ?? "smart",
      use_memory: opts.useMemory ?? true
    })
  });
  if (!res.ok || !res.body) {
    throw new Error(`stream ${res.status}: ${await res.text()}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split("\n\n");
    buf = events.pop() ?? "";
    for (const evt of events) {
      for (const line of evt.split("\n")) {
        if (!line.startsWith("data:")) continue;
        let raw = line.slice(5);
        if (raw.startsWith(" ")) raw = raw.slice(1);
        if (!raw || raw === "end") continue;
        try {
          const parsed = JSON.parse(raw) as { t?: string; s?: string };
          if (typeof parsed.t === "string") {
            onEvent({ type: "token", text: parsed.t });
          } else if (typeof parsed.s === "string") {
            onEvent({ type: "sentence", text: parsed.s });
          }
        } catch {
          onEvent({ type: "token", text: raw });
        }
      }
    }
  }
}

/** Backward-compat: только токены, для старого кода. */
export async function streamChat(
  message: string,
  onChunk: (chunk: string) => void,
  opts: { profile?: string; useMemory?: boolean } = {}
): Promise<void> {
  return streamChatEvents(
    message,
    (evt) => {
      if (evt.type === "token") onChunk(evt.text);
    },
    opts
  );
}

// === Agents ===

export function openAgentSocket(
  payload: { task: string; mode?: "single" | "pipeline"; profile?: string },
  onEvent: (evt: AgentEvent) => void,
  onClose?: () => void
): WebSocket | null {
  const token = getToken();
  if (!token) {
    onEvent({ type: "error", message: "missing auth token" });
    return null;
  }
  const base = apiBase();
  const wsBase = base.startsWith("https") ? base.replace("https", "wss") : base.replace("http", "ws");
  const ws = new WebSocket(`${wsBase}/api/agents/ws?token=${encodeURIComponent(token)}`);
  ws.onopen = () => ws.send(JSON.stringify(payload));
  ws.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => onClose?.();
  return ws;
}

// === Voice ===

export async function transcribeAudio(audio: Blob): Promise<{ text: string; provider: string }> {
  const fd = new FormData();
  fd.append("audio", audio, "voice.webm");
  const res = await fetch(`${apiBase()}/api/voice/stt`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: fd
  });
  if (!res.ok) throw new Error(`stt ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function listVoices(): Promise<VoiceInfo[]> {
  const res = await fetch(`${apiBase()}/api/voice/voices`);
  if (!res.ok) throw new Error(`voices ${res.status}`);
  return res.json();
}

export async function synthesizeSpeech(
  text: string,
  opts: { voice?: string; tone?: string; prefer?: "auto" | "elevenlabs" | "yandex" } = {}
): Promise<Blob> {
  const res = await fetch(`${apiBase()}/api/voice/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      text,
      voice: opts.voice ?? "madirus",
      tone: opts.tone ?? "warm",
      prefer: opts.prefer ?? "auto"
    })
  });
  if (!res.ok) throw new Error(`tts ${res.status}: ${await res.text()}`);
  return res.blob();
}

export async function streamSpeech(
  text: string,
  opts: { voice?: string; tone?: string } = {}
): Promise<string> {
  const res = await fetch(`${apiBase()}/api/voice/tts/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      text,
      voice: opts.voice ?? "madirus",
      tone: opts.tone ?? "warm"
    })
  });
  if (!res.ok || !res.body) {
    const blob = await synthesizeSpeech(text, opts);
    return URL.createObjectURL(blob);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function voiceFullLoop(audio: Blob): Promise<FullLoopResponse> {
  const fd = new FormData();
  fd.append("audio", audio, "voice.webm");
  const res = await fetch(`${apiBase()}/api/voice/full-loop`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: fd
  });
  if (!res.ok) throw new Error(`full-loop ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Stream-reply event types from /api/voice/stream-reply SSE. */
export type VoiceStreamEvent =
  | { type: "transcript"; text: string; provider: string }
  | { type: "token"; text: string }
  | { type: "audio"; audio: string; sentence: string; provider: string }
  | { type: "error"; message: string };

/**
 * Потоковый голосовой ответ: audio → STT → LLM stream → TTS по предложениям.
 *
 * Каждое предложение синтезируется и отправляется как base64 audio chunk.
 * Фронт начинает играть первое предложение пока LLM генерит второе.
 * Используйте onEvent для получения транскрипта, токенов текста и аудио-чанков.
 */
export async function streamVoiceReply(
  audio: Blob,
  onEvent: (evt: VoiceStreamEvent) => void,
): Promise<void> {
  const fd = new FormData();
  fd.append("audio", audio, "voice.webm");
  const res = await fetch(`${apiBase()}/api/voice/stream-reply`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: fd,
  });
  if (!res.ok || !res.body) {
    throw new Error(`stream-reply ${res.status}: ${await res.text()}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split("\n\n");
    buf = events.pop() ?? "";
    for (const evt of events) {
      for (const line of evt.split("\n")) {
        if (!line.startsWith("data:")) continue;
        let raw = line.slice(5);
        if (raw.startsWith(" ")) raw = raw.slice(1);
        if (!raw || raw === "end") continue;
        try {
          const parsed = JSON.parse(raw) as VoiceStreamEvent;
          onEvent(parsed);
        } catch {
          // ignore malformed
        }
      }
    }
  }
}

// === Vision ===

export async function analyzeImage(
  image: Blob,
  question = "Опиши изображение по-русски."
): Promise<{ text: string; provider: string }> {
  const fd = new FormData();
  fd.append("image", image, "image.png");
  fd.append("question", question);
  const res = await fetch(`${apiBase()}/api/vision/analyze`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: fd
  });
  if (!res.ok) throw new Error(`vision ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function generateImage(
  prompt: string,
  opts: { aspectRatio?: string; numOutputs?: number } = {}
): Promise<{ urls: string[]; provider: string; prompt: string }> {
  const res = await fetch(`${apiBase()}/api/vision/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      prompt,
      aspect_ratio: opts.aspectRatio ?? "1:1",
      num_outputs: opts.numOutputs ?? 1
    })
  });
  if (!res.ok) throw new Error(`gen ${res.status}: ${await res.text()}`);
  return res.json();
}

// === Push ===

export async function getVapidPublicKey(): Promise<string> {
  const res = await fetch(`${apiBase()}/api/push/public-key`);
  if (!res.ok) throw new Error(`vapid ${res.status}`);
  const data = (await res.json()) as { key: string };
  return data.key;
}

export async function subscribePush(subscription: PushSubscriptionJSON): Promise<void> {
  const res = await fetch(`${apiBase()}/api/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(subscription)
  });
  if (!res.ok) throw new Error(`subscribe ${res.status}`);
}

// === Feedback ===

export async function sendFeedback(
  score: 1 | -1 | 0,
  messageId?: number,
  note?: string
): Promise<{ id: number }> {
  const res = await fetch(`${apiBase()}/api/feedback/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ score, message_id: messageId ?? null, note: note ?? null })
  });
  if (!res.ok) throw new Error(`feedback ${res.status}`);
  return res.json();
}

// === Auth ===

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${apiBase()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
  if (!res.ok) throw new Error(`login ${res.status}`);
  const data = (await res.json()) as { access_token: string };
  localStorage.setItem("freddy_token", data.access_token);
}

export async function ping(): Promise<boolean> {
  try {
    const res = await fetch(`${apiBase()}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getIntegrations(): Promise<Record<string, unknown>> {
  const res = await fetch(`${apiBase()}/integrations`);
  if (!res.ok) throw new Error(`integrations ${res.status}`);
  return res.json();
}

// === Reminders (Sprint 8) ===

export type ReminderInfo = {
  id?: number;
  task_id?: number;
  title: string;
  scheduled_at?: string | null;
  recurrence?: string | null;
  created_at?: string | null;
};

export async function createReminder(
  text: string,
  tzOffset = 3
): Promise<ReminderInfo> {
  const res = await fetch(`${apiBase()}/api/reminders`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text, tz_offset: tzOffset })
  });
  if (!res.ok) throw new Error(`reminder ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function listReminders(): Promise<{ reminders: ReminderInfo[]; count: number }> {
  const res = await fetch(`${apiBase()}/api/reminders`, {
    headers: { ...authHeaders() }
  });
  if (!res.ok) throw new Error(`reminders ${res.status}`);
  return res.json();
}

// === Triggers (Sprint 6) ===

export type TriggerEvent = {
  type: "trigger" | "ping";
  source?: string;
  message?: string;
  title?: string;
  priority?: string;
  data?: Record<string, unknown>;
};

export function openTriggerSocket(
  onEvent: (evt: TriggerEvent) => void,
  onClose?: () => void
): WebSocket | null {
  const token = getToken();
  if (!token) return null;
  const base = apiBase();
  const wsBase = base.startsWith("https") ? base.replace("https", "wss") : base.replace("http", "ws");
  const ws = new WebSocket(`${wsBase}/api/triggers/ws?token=${encodeURIComponent(token)}`);
  ws.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {}
  };
  ws.onclose = () => onClose?.();
  ws.onerror = () => onClose?.();
  return ws;
}
