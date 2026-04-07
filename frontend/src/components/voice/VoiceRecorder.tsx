"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, X, Volume2 } from "lucide-react";
import { sendChat, synthesizeSpeech, transcribeAudio } from "@/lib/api";
import { useSession } from "@/store/session";
import { SilenceDetector } from "@/lib/vad";

type Props = {
  /** Опционально: внешний обработчик распознанного текста (для интеграций). */
  onTranscript?: (text: string) => void;
};

type Phase = "idle" | "recording" | "transcribing" | "thinking" | "speaking" | "error";

export function VoiceRecorder({ onTranscript }: Props) {
  const token = useSession((s) => s.token);
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState<number[]>(new Array(48).fill(0));
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mediaRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const vadRef = useRef<SilenceDetector | null>(null);
  const playerRef = useRef<HTMLAudioElement | null>(null);
  const stoppedAutoRef = useRef(false);

  function cleanupRecording() {
    try {
      recorderRef.current?.stop();
    } catch {}
    mediaRef.current?.getTracks().forEach((t) => t.stop());
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    audioCtxRef.current?.close().catch(() => {});
    vadRef.current?.stop();
    rafRef.current = null;
    vadRef.current = null;
    setLevel(new Array(48).fill(0));
  }

  async function startRecording() {
    if (!token) {
      window.dispatchEvent(new CustomEvent("freddy:open-auth"));
      return;
    }
    setError(null);
    setTranscript("");
    setReply("");
    stoppedAutoRef.current = false;
    setPhase("recording");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRef.current = stream;

      const ctx = new (window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 128;
      source.connect(analyser);
      const buffer = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteFrequencyData(buffer);
        const bins = new Array(48).fill(0).map((_, i) => {
          const slice = buffer.slice(
            Math.floor((i * buffer.length) / 48),
            Math.floor(((i + 1) * buffer.length) / 48)
          );
          const avg = slice.reduce((a, b) => a + b, 0) / Math.max(slice.length, 1);
          return avg / 255;
        });
        setLevel(bins);
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);

      const vad = new SilenceDetector(stream, ctx, {
        onSilence: () => {
          if (recorderRef.current && recorderRef.current.state === "recording") {
            stoppedAutoRef.current = true;
            stopRecording();
          }
        },
        threshold: 0.05,
        silenceMs: 1500
      });
      vad.start();
      vadRef.current = vad;

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        cleanupRecording();
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size < 1000) {
          setPhase("idle");
          return;
        }
        await runVoiceLoop(blob);
      };
      recorderRef.current = recorder;
      recorder.start();
    } catch (err) {
      setError((err as Error).message);
      setPhase("error");
    }
  }

  function stopRecording() {
    try {
      recorderRef.current?.stop();
    } catch {}
  }

  async function runVoiceLoop(blob: Blob) {
    setPhase("transcribing");
    let userText = "";
    try {
      const stt = await transcribeAudio(blob);
      userText = stt.text || "";
      setTranscript(userText);
      onTranscript?.(userText);
    } catch (err) {
      setError(`STT: ${(err as Error).message}`);
      setPhase("error");
      return;
    }
    if (!userText) {
      setPhase("idle");
      return;
    }

    setPhase("thinking");
    let assistantText = "";
    try {
      const chat = await sendChat(userText, { profile: "smart", useMemory: true });
      assistantText = chat.reply || "";
      setReply(assistantText);
    } catch (err) {
      setError(`Chat: ${(err as Error).message}`);
      setPhase("error");
      return;
    }
    if (!assistantText) {
      setPhase("idle");
      return;
    }

    setPhase("speaking");
    try {
      const audio = await synthesizeSpeech(assistantText.slice(0, 500));
      const url = URL.createObjectURL(audio);
      const player = new Audio(url);
      playerRef.current = player;
      player.onended = () => {
        URL.revokeObjectURL(url);
        setPhase("idle");
      };
      player.onerror = () => {
        URL.revokeObjectURL(url);
        setPhase("idle");
      };
      await player.play();
    } catch (err) {
      // TTS опциональный — если нет YANDEX_API_KEY, просто показываем текст
      setError(`TTS недоступен (${(err as Error).message}). Ответ показан текстом.`);
      setPhase("idle");
    }
  }

  function close() {
    cleanupRecording();
    if (playerRef.current) {
      try {
        playerRef.current.pause();
      } catch {}
      playerRef.current = null;
    }
    setOpen(false);
    setPhase("idle");
    setTranscript("");
    setReply("");
    setError(null);
  }

  useEffect(() => () => close(), []);

  const phaseLabel = {
    idle: "Нажми и говори",
    recording: "Слушаю…",
    transcribing: "Распознаю…",
    thinking: "Думаю…",
    speaking: "Говорю…",
    error: "Ошибка"
  }[phase];

  const isRecording = phase === "recording";

  return (
    <>
      <button
        className="fixed bottom-6 right-6 z-20 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-neon-cyan via-neon-violet to-neon-pink text-white shadow-neon transition hover:scale-105 active:scale-95"
        onClick={() => setOpen(true)}
        aria-label="Голосовой режим"
      >
        <Mic className="h-6 w-6" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="glass-strong relative w-full max-w-md p-8 text-center"
              initial={{ scale: 0.94, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.94, opacity: 0 }}
              transition={{ type: "spring", stiffness: 280, damping: 26 }}
            >
              <button
                className="absolute right-3 top-3 text-slate-400 hover:text-white"
                onClick={close}
                aria-label="Закрыть"
              >
                <X className="h-5 w-5" />
              </button>

              <div className="mb-2 flex items-center justify-center gap-2 text-sm text-slate-300">
                {phase === "speaking" && <Volume2 className="h-4 w-4 animate-pulse text-neon-cyan" />}
                <span>{phaseLabel}</span>
              </div>

              <div className="mx-auto mb-4 flex h-24 w-full max-w-xs items-end justify-center gap-[3px]">
                {level.map((v, i) => (
                  <div
                    key={i}
                    className="w-1 rounded-full bg-gradient-to-t from-neon-cyan via-neon-violet to-neon-pink transition-[height]"
                    style={{ height: `${Math.max(4, v * 100)}%` }}
                  />
                ))}
              </div>

              <button
                className={`mx-auto flex h-20 w-20 items-center justify-center rounded-full transition disabled:opacity-50 ${
                  isRecording
                    ? "bg-red-500/80 shadow-[0_0_60px_rgba(239,68,68,0.55)]"
                    : "bg-gradient-to-br from-neon-cyan via-neon-violet to-neon-pink shadow-neon"
                }`}
                onClick={isRecording ? stopRecording : startRecording}
                disabled={phase === "transcribing" || phase === "thinking" || phase === "speaking"}
                aria-label={isRecording ? "Остановить" : "Начать запись"}
              >
                {isRecording ? (
                  <MicOff className="h-8 w-8 text-white" />
                ) : (
                  <Mic className="h-8 w-8 text-white" />
                )}
              </button>

              {transcript && (
                <div className="mt-4 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-200">
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Ты</div>
                  {transcript}
                </div>
              )}

              {reply && (
                <div className="mt-2 rounded-xl border border-neon-violet/30 bg-neon-violet/10 px-3 py-2 text-left text-xs text-slate-100">
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-neon-violet">Фреди</div>
                  {reply}
                </div>
              )}

              {error && (
                <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                  {error}
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
