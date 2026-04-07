"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Sparkles } from "lucide-react";
import { streamChat, type ChatMessage } from "@/lib/api";

type Props = {
  id?: string;
  onStateChange?: (s: "idle" | "thinking" | "speaking") => void;
};

export function ChatPanel({ id, onStateChange }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Привет! Я Фреди. Спроси что-нибудь или скомандуй — я подключу инструменты и память."
    }
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  async function onSend() {
    if (!input.trim() || busy) return;
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
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠️ Ошибка: ${(err as Error).message}` }
      ]);
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

  return (
    <section id={id} className="glass flex h-[560px] flex-col p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-slate-300">
        <Sparkles className="h-4 w-4 text-neon-violet" />
        <span>Диалог с Фреди</span>
        <span className="ml-auto text-xs text-slate-500">SSE · router · memory</span>
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
          placeholder="Спроси Фреди…"
          rows={1}
          className="input resize-none"
        />
        <button
          onClick={onSend}
          disabled={busy}
          className="btn-primary h-[46px] px-4 disabled:opacity-60"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </section>
  );
}
