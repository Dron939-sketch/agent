"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, X } from "lucide-react";

type Props = {
  onTranscript?: (text: string) => void;
};

export function VoiceRecorder({ onTranscript }: Props) {
  const [open, setOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState<number[]>(new Array(48).fill(0));
  const [error, setError] = useState<string | null>(null);

  const mediaRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  async function start() {
    setError(null);
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

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        await send(blob);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function stop() {
    recorderRef.current?.stop();
    mediaRef.current?.getTracks().forEach((t) => t.stop());
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    audioCtxRef.current?.close();
    rafRef.current = null;
    setRecording(false);
    setLevel(new Array(48).fill(0));
  }

  async function send(blob: Blob) {
    // endpoint опционален — если на бэке нет /api/voice/stt, молча пропустим
    try {
      const fd = new FormData();
      fd.append("audio", blob, "voice.webm");
      const res = await fetch("/api/backend/voice/stt", { method: "POST", body: fd });
      if (!res.ok) return;
      const data = (await res.json()) as { text?: string };
      if (data.text) onTranscript?.(data.text);
    } catch {
      /* no-op */
    }
  }

  useEffect(() => () => void stop(), []);

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
                onClick={() => {
                  stop();
                  setOpen(false);
                }}
                aria-label="Закрыть"
              >
                <X className="h-5 w-5" />
              </button>

              <div className="mb-4 text-sm text-slate-300">
                {recording ? "Слушаю…" : "Нажми и говори"}
              </div>

              <div className="mx-auto mb-6 flex h-28 w-full max-w-xs items-end justify-center gap-[3px]">
                {level.map((v, i) => (
                  <div
                    key={i}
                    className="w-1 rounded-full bg-gradient-to-t from-neon-cyan via-neon-violet to-neon-pink transition-[height]"
                    style={{ height: `${Math.max(4, v * 100)}%` }}
                  />
                ))}
              </div>

              <button
                className={`mx-auto flex h-20 w-20 items-center justify-center rounded-full transition ${
                  recording
                    ? "bg-red-500/80 shadow-[0_0_60px_rgba(239,68,68,0.55)]"
                    : "bg-gradient-to-br from-neon-cyan via-neon-violet to-neon-pink shadow-neon"
                }`}
                onClick={recording ? stop : start}
                aria-label={recording ? "Остановить" : "Начать запись"}
              >
                {recording ? (
                  <MicOff className="h-8 w-8 text-white" />
                ) : (
                  <Mic className="h-8 w-8 text-white" />
                )}
              </button>

              {error && (
                <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
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
