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

/**
 * Резолв URL бекенда:
 *   1. NEXT_PUBLIC_API_URL — задан при билде (render.yaml).
 *   2. Если фронт развёрнут на agent-frontend-*.onrender.com — авто-маппим
 *      на agent-ynlg.onrender.com (бекенд из этого репозитория).
 *   3. Локально fallback на http://localhost:8000.
 */
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

const API = resolveApiUrl();

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
): Promise<{ reply: string; model: string; recalled: string[]; emotion?: string; tone?: string }> {
  const res = await fetch(`${API}/api/chat/`, {
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
 * SSE-стрим сервера. Сервер отдаёт чанки в формате `data: {"t": "..."}\n\n`,
 * сохраняя ВСЕ пробелы и переводы строк. Раньше .trim() съедал ведущие
 * пробелы между чанками — слова слипались.
 */
export async function streamChat(
  message: string,
  onChunk: (chunk: string) => void,
  opts: { profile?: string; useMemory?: boolean } = {}
): Promise<void> {
  const res = await fetch(`${API}/api/chat/stream`, {
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
    // SSE события разделены пустой строкой
    const events = buf.split("\n\n");
    buf = events.pop() ?? "";
    for (const evt of events) {
      // Каждое событие может содержать несколько строк; ищем "data:"
      for (const line of evt.split("\n")) {
        if (!line.startsWith("data:")) continue;
        // SSE-спека: после "data:" допустим один опциональный пробел
        let raw = line.slice(5);
        if (raw.startsWith(" ")) raw = raw.slice(1);
        if (!raw || raw === "end") continue;
        try {
          const parsed = JSON.parse(raw) as { t?: string };
          if (typeof parsed.t === "string") {
            onChunk(parsed.t);
          }
        } catch {
          // Если бекенд старого формата — берём как есть
          onChunk(raw);
        }
      }
    }
  }
}

// === Agents (REST + WS) ===

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
  const wsBase = API.startsWith("https") ? API.replace("https", "wss") : API.replace("http", "ws");
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
  const res = await fetch(`${API}/api/voice/stt`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: fd
  });
  if (!res.ok) throw new Error(`stt ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function synthesizeSpeech(text: string, voice = "jane"): Promise<Blob> {
  const res = await fetch(`${API}/api/voice/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text, voice })
  });
  if (!res.ok) throw new Error(`tts ${res.status}: ${await res.text()}`);
  return res.blob();
}

// === Push ===

export async function getVapidPublicKey(): Promise<string> {
  const res = await fetch(`${API}/api/push/public-key`);
  if (!res.ok) throw new Error(`vapid ${res.status}`);
  const data = (await res.json()) as { key: string };
  return data.key;
}

export async function subscribePush(subscription: PushSubscriptionJSON): Promise<void> {
  const res = await fetch(`${API}/api/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(subscription)
  });
  if (!res.ok) throw new Error(`subscribe ${res.status}`);
}

// === Auth ===

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${API}/api/auth/login`, {
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
    const res = await fetch(`${API}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}
