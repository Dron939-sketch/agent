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
  | { type: "done"; answer: string };

/**
 * Резолв URL бекенда:
 *   1. NEXT_PUBLIC_API_URL — задан при билде (render.yaml).
 *   2. Если фронт развёрнут на agent-frontend-*.onrender.com — авто-маппим
 *      на agent-ynlg.onrender.com (бекенд из этого репозитория).
 *   3. Локально fallback на http://localhost:8000.
 */
function resolveApiUrl(): string {
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
    // По умолчанию — Render-овский бекенд этого проекта
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
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const data = line.slice(5).trim();
      if (data && data !== "end") onChunk(data);
    }
  }
}

export function openAgentSocket(
  payload: { task: string; mode?: "single" | "pipeline"; profile?: string },
  onEvent: (evt: AgentEvent) => void,
  onClose?: () => void
): WebSocket {
  const wsUrl = (API.startsWith("https") ? API.replace("https", "wss") : API.replace("http", "ws")) + "/api/agents/ws";
  const ws = new WebSocket(wsUrl);
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
