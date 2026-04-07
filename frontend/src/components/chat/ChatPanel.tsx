"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LogIn, Send, Sparkles } from "lucide-react";
import { streamChat, type ChatMessage } from "@/lib/api";
import { useSession } from "@/store/session";

type Props = {
  id?: string;
  onStateChange?: (s: "idle" | "thinking" | "speaking") => void;
};

function openAuth() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("freddy:open-auth"));
  }
}

export function ChatPanel({ id, onStateChange }: Props) {
  const token = useSession((s) => s.token);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Привет! Я Фреди — твой всемогущий AI-помощник. Войди или зарегистрируйся, и можем начинать."
    }
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  async function onSend() {
    if (!input.trim() || busy) return;

    if (!token) {
      openAuth();
      return;
    }

    const user = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: user }]);
    setBusy(true);
    onStateChange?.("thinking");

    try {
      let acc = "";
      setMessages((m) => [...m, { role: "assistant", content: "" }]);
      onStateChange?.("speaking");
      await streamChat(user, (chunk) => {
        acc += chunk;
        setMessages((m) => {
          const next = [...m];
          next[next.length - 1] = { role: "assistant", content: acc };
          return next;
        });
      });
    } catch (err) {
      const msg = (err as Error).message;
      const is401 = msg.includes(" 401") || msg.includes("missing bearer");
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: is401
            ? "🔒 Нужна авторизация. Открываю окно входа…"
            : `⚠️ Ошибка: ${msg}`
        }
      ]);
      if (is401) openAuth();
    } finally {
      setBusy(false);
      onStateChange?.("idle");
      queueMicrotask(() =>
        listRef.current?.scrollTo({
          top: listRef.current.scrollHeight,
          behavior: "smooth"
        })
      );
    }
  }

  // Если токен только что появился — добавим приветственный системный месседж
  useEffect(() => {
    if (token) {
      setMessages((m) => {
        if (m.some((x) => x.content.startsWith("✅"))) return m;
        return [
          ...m,
          {
            role: "assistant",
            content: "✅ Подключился. Расскажи, что у тебя сегодня — помогу разобраться."
          }
        ];
      });
    }
  }, [token]);

  return (
    <section id={id} className="glass flex h-[560px] flex-col p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-slate-300">
        <Sparkles className="h-4 w-4 text-neon-violet" />
        <span>Диалог с Фреди</span>
        <span className="ml-auto text-xs text-slate-500">
          {token ? "SSE · router · memory" : "guest"}
        </span>
      </div>

      <div
        ref={listRef}
        className="scrollbar-thin flex-1 space-y-3 overflow-y-auto pr-2"
      >
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-gradient-to-br from-neon-violet/80 to-neon-pink/70 px-4 py-2 text-sm text-white shadow-neon"
                    : "max-w-[85%] rounded-2xl rounded-bl-sm border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-100"
                }
              >
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {m.content || "▍"}
                  </ReactMarkdown>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="mt-3 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={token ? "Спроси Фреди…" : "Сначала войди →"}
          rows={1}
          className="input resize-none"
        />
        {token ? (
          <button
            onClick={onSend}
            disabled={busy}
            className="btn-primary h-[46px] px-4 disabled:opacity-60"
          >
            <Send className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={openAuth}
            className="btn-primary h-[46px] px-4"
            title="Войти / Регистрация"
          >
            <LogIn className="h-4 w-4" />
          </button>
        )}
      </div>
    </section>
  );
}
