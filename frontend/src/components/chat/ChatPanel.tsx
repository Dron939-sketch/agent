"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ImagePlus, LogIn, Send, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import {
  analyzeImage,
  generateImage,
  sendChat,
  sendFeedback,
  streamChat,
  type ChatMessage as ChatMsgT
} from "@/lib/api";
import { useSession } from "@/store/session";
import { EmotionBadge } from "@/components/voice/EmotionBadge";

type Props = {
  id?: string;
  onStateChange?: (s: "idle" | "thinking" | "speaking") => void;
};

type Message = ChatMsgT & {
  id?: number;
  emotion?: string | null;
  tone?: string | null;
  imageUrl?: string;
  generatedImages?: string[];
  feedback?: 1 | -1;
};

const IMAGE_GEN_PATTERNS = [
  /(?:^|\s)(нарисуй|сгенерируй|покажи как выглядит|создай картинку|придумай изображение)\s+(.+)/i
];

function detectImageGenIntent(text: string): string | null {
  for (const p of IMAGE_GEN_PATTERNS) {
    const m = text.match(p);
    if (m) return m[2].trim();
  }
  return null;
}

function openAuth() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("freddy:open-auth"));
  }
}

export function ChatPanel({ id, onStateChange }: Props) {
  const token = useSession((s) => s.token);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Привет! Я Фреди — твой всемогущий AI-помощник. Войди или зарегистрируйся, и можем начинать."
    }
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function scrollToEnd() {
    queueMicrotask(() =>
      listRef.current?.scrollTo({
        top: listRef.current.scrollHeight,
        behavior: "smooth"
      })
    );
  }

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

    // 1. Image generation intent
    const imagePrompt = detectImageGenIntent(user);
    if (imagePrompt) {
      try {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `🎨 Генерирую: «${imagePrompt}»…` }
        ]);
        const res = await generateImage(imagePrompt);
        setMessages((m) => {
          const next = [...m];
          next[next.length - 1] = {
            role: "assistant",
            content: `Готово, вот «${imagePrompt}»:`,
            generatedImages: res.urls
          };
          return next;
        });
      } catch (err) {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: `⚠️ Не получилось сгенерировать (${(err as Error).message}). Возможно, не задан REPLICATE_API_TOKEN.`
          }
        ]);
      } finally {
        setBusy(false);
        onStateChange?.("idle");
        scrollToEnd();
      }
      return;
    }

    // 2. Обычный текстовый чат через streaming
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
      // После окончания получаем эмоцию через отдельный POST (быстрее, чем парсить SSE)
      try {
        const meta = await sendChat(user, { profile: "smart" });
        setMessages((m) => {
          const next = [...m];
          // обновляем последний ответ ассистента метаданными
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "assistant" && !next[i].id) {
              next[i] = { ...next[i], emotion: meta.emotion, tone: meta.tone, id: meta.message_id };
              break;
            }
          }
          return next;
        });
      } catch {
        /* not critical */
      }
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
      scrollToEnd();
    }
  }

  async function onAttachImage(file: File) {
    if (!token) {
      openAuth();
      return;
    }
    setMessages((m) => [
      ...m,
      { role: "user", content: `[Изображение: ${file.name}]`, imageUrl: URL.createObjectURL(file) }
    ]);
    setBusy(true);
    onStateChange?.("thinking");
    try {
      const res = await analyzeImage(file, "Опиши изображение по-русски, кратко и точно.");
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.text, tone: "warm" }
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `⚠️ Не получилось проанализировать (${(err as Error).message}). Возможно, не задан ANTHROPIC_API_KEY.`
        }
      ]);
    } finally {
      setBusy(false);
      onStateChange?.("idle");
      scrollToEnd();
    }
  }

  async function onFeedback(idx: number, score: 1 | -1) {
    const msg = messages[idx];
    if (!msg || msg.role !== "assistant" || msg.feedback) return;
    setMessages((m) => {
      const next = [...m];
      next[idx] = { ...next[idx], feedback: score };
      return next;
    });
    try {
      await sendFeedback(score, msg.id);
    } catch {
      /* tolerant */
    }
  }

  // Welcome после логина
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
          {token ? "stream · vision · memory" : "guest"}
        </span>
      </div>

      <div ref={listRef} className="scrollbar-thin flex-1 space-y-3 overflow-y-auto pr-2">
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
                {m.imageUrl && (
                  <img
                    src={m.imageUrl}
                    alt="user upload"
                    className="mb-2 max-h-48 rounded-lg border border-white/10"
                  />
                )}
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {m.content || "▍"}
                  </ReactMarkdown>
                </div>
                {m.generatedImages && m.generatedImages.length > 0 && (
                  <div className="mt-2 grid grid-cols-1 gap-2">
                    {m.generatedImages.map((url, k) => (
                      <img
                        key={k}
                        src={url}
                        alt="generated"
                        className="rounded-lg border border-white/10"
                        loading="lazy"
                      />
                    ))}
                  </div>
                )}
                {m.role === "assistant" && (m.emotion || m.id) && (
                  <div className="mt-2 flex items-center gap-2">
                    {m.emotion && <EmotionBadge emotion={m.emotion} />}
                    {m.id && (
                      <div className="ml-auto flex gap-1">
                        <button
                          className={`rounded p-1 transition ${m.feedback === 1 ? "text-neon-lime" : "text-slate-500 hover:text-white"}`}
                          onClick={() => onFeedback(i, 1)}
                          aria-label="нравится"
                        >
                          <ThumbsUp className="h-3 w-3" />
                        </button>
                        <button
                          className={`rounded p-1 transition ${m.feedback === -1 ? "text-neon-pink" : "text-slate-500 hover:text-white"}`}
                          onClick={() => onFeedback(i, -1)}
                          aria-label="не нравится"
                        >
                          <ThumbsDown className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="mt-3 flex items-end gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onAttachImage(file);
            if (fileRef.current) fileRef.current.value = "";
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy || !token}
          className="flex h-[46px] w-[46px] items-center justify-center rounded-xl border border-white/10 text-slate-400 transition hover:border-neon-cyan/40 hover:text-neon-cyan disabled:opacity-50"
          title="Прикрепить изображение"
        >
          <ImagePlus className="h-4 w-4" />
        </button>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={token ? "Спроси Фреди или скажи «нарисуй кота»…" : "Сначала войди →"}
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
