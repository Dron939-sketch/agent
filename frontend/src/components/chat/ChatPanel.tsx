"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ImagePlus,
  LogIn,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  VolumeX
} from "lucide-react";
import {
  analyzeImage,
  generateImage,
  sendChat,
  sendFeedback,
  streamChat,
  streamSpeech,
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
  const voiceReply = useSession((s) => s.voiceReply);
  const setVoiceReply = useSession((s) => s.setVoiceReply);
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
  const playerRef = useRef<HTMLAudioElement | null>(null);

  function scrollToEnd() {
    queueMicrotask(() =>
      listRef.current?.scrollTo({
        top: listRef.current.scrollHeight,
        behavior: "smooth"
      })
    );
  }

  function stopAudio() {
    if (playerRef.current) {
      try {
        playerRef.current.pause();
      } catch {}
      playerRef.current = null;
    }
  }

  async function speakReply(text: string, tone?: string | null) {
    if (!voiceReply || !text.trim()) return;
    stopAudio();
    try {
      const url = await streamSpeech(text.slice(0, 1500), { tone: tone ?? "warm" });
      const audio = new Audio(url);
      playerRef.current = audio;
      onStateChange?.("speaking");
      audio.onended = () => {
        URL.revokeObjectURL(url);
        if (playerRef.current === audio) {
          playerRef.current = null;
          onStateChange?.("idle");
        }
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        if (playerRef.current === audio) {
          playerRef.current = null;
          onStateChange?.("idle");
        }
      };
      await audio.play();
    } catch {
      // если TTS не настроен на бекенде — тихо игнорим, текст уже показан
      onStateChange?.("idle");
    }
  }

  async function onSend() {
    if (!input.trim() || busy) return;
    if (!token) {
      openAuth();
      return;
    }

    // Если Фреди говорит — прервать его при новой реплике (barge-in lite)
    stopAudio();

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

    // 2. Обычный чат: streaming + одновременно полный POST для метаданных
    try {
      let acc = "";
      setMessages((m) => [...m, { role: "assistant", content: "" }]);

      // Параллельно стартуем streamChat (для бубла) и sendChat (для emotion+id)
      const metaPromise = sendChat(user, { profile: "smart" }).catch(() => null);

      await streamChat(user, (chunk) => {
        acc += chunk;
        setMessages((m) => {
          const next = [...m];
          next[next.length - 1] = { role: "assistant", content: acc };
          return next;
        });
      });

      const meta = await metaPromise;
      if (meta) {
        setMessages((m) => {
          const next = [...m];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "assistant" && !next[i].id) {
              next[i] = {
                ...next[i],
                emotion: meta.emotion,
                tone: meta.tone,
                id: meta.message_id
              };
              break;
            }
          }
          return next;
        });
      }

      // Авто-озвучка ответа (если включено)
      const finalText = (meta?.reply ?? acc) || acc;
      if (voiceReply && finalText.trim()) {
        await speakReply(finalText, meta?.tone);
      }
    } catch (err) {
      const msg = (err as Error).message;
      const is401 = msg.includes(" 401") || msg.includes("missing bearer");
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: is401 ? "🔒 Нужна авторизация. Открываю окно входа…" : `⚠️ Ошибка: ${msg}`
        }
      ]);
      if (is401) openAuth();
    } finally {
      setBusy(false);
      if (!voiceReply) onStateChange?.("idle");
      scrollToEnd();
    }
  }

  async function onAttachImage(file: File) {
    if (!token) {
      openAuth();
      return;
    }
    stopAudio();
    setMessages((m) => [
      ...m,
      {
        role: "user",
        content: `[Изображение: ${file.name}]`,
        imageUrl: URL.createObjectURL(file)
      }
    ]);
    setBusy(true);
    onStateChange?.("thinking");
    try {
      const res = await analyzeImage(file, "Опиши изображение по-русски, кратко и точно.");
      setMessages((m) => [...m, { role: "assistant", content: res.text, tone: "warm" }]);
      if (voiceReply && res.text) {
        await speakReply(res.text, "warm");
      }
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
      if (!voiceReply) onStateChange?.("idle");
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

  function toggleVoiceReply() {
    if (voiceReply) {
      stopAudio();
    }
    setVoiceReply(!voiceReply);
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

  // Cleanup при размонтировании
  useEffect(() => () => stopAudio(), []);

  return (
    <section id={id} className="glass flex h-[560px] flex-col p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-slate-300">
        <Sparkles className="h-4 w-4 text-neon-violet" />
        <span>Диалог с Фреди</span>
        <button
          onClick={toggleVoiceReply}
          className={`ml-auto rounded-md border px-2 py-0.5 text-[10px] uppercase tracking-wider transition ${
            voiceReply
              ? "border-neon-cyan/40 bg-neon-cyan/10 text-neon-cyan"
              : "border-white/10 bg-white/5 text-slate-500 hover:text-white"
          }`}
          title={voiceReply ? "Озвучка включена" : "Озвучка выключена"}
        >
          {voiceReply ? <Volume2 className="inline h-3 w-3" /> : <VolumeX className="inline h-3 w-3" />}
          <span className="ml-1">{voiceReply ? "voice on" : "voice off"}</span>
        </button>
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
                          className={`rounded p-1 transition ${
                            m.feedback === 1 ? "text-neon-lime" : "text-slate-500 hover:text-white"
                          }`}
                          onClick={() => onFeedback(i, 1)}
                          aria-label="нравится"
                        >
                          <ThumbsUp className="h-3 w-3" />
                        </button>
                        <button
                          className={`rounded p-1 transition ${
                            m.feedback === -1 ? "text-neon-pink" : "text-slate-500 hover:text-white"
                          }`}
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
          <button onClick={openAuth} className="btn-primary h-[46px] px-4" title="Войти / Регистрация">
            <LogIn className="h-4 w-4" />
          </button>
        )}
      </div>
    </section>
  );
}
