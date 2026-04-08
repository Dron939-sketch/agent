"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, Volume2, X } from "lucide-react";
import { streamSpeech, voiceFullLoop, type FullLoopResponse } from "@/lib/api";
import { useSession } from "@/store/session";
import { SilenceDetector } from "@/lib/vad";
import { EmotionBadge } from "./EmotionBadge";

type Phase = "idle" | "recording" | "processing" | "speaking" | "error";

export function VoiceRecorder() {
  const token = useSession((s) => s.token);
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState<number[]>(new Array(48).fill(0));
  const [result, setResult] = useState<FullLoopResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mediaRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const vadRef = useRef<SilenceDetector | null>(null);
  const playerRef = useRef<HTMLAudioElement | null>(null);

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
    setResult(null);
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
        await runFullLoop(blob);
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

  async function runFullLoop(blob: Blob) {
    setPhase("processing");
    let response: FullLoopResponse;
    try {
      response = await voiceFullLoop(blob);
      setResult(response);
    } catch (err) {
      setError(`${(err as Error).message}`);
      setPhase("error");
      return;
    }

    if (!response.reply) {
      setPhase("idle");
      return;
    }

    setPhase("speaking");
    try {
      const tone = response.fused_tone || "warm";
      const audioUrl = await streamSpeech(response.reply.slice(0, 1000), { tone });
      const player = new Audio(audioUrl);
      playerRef.current = player;
      player.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setPhase("idle");
      };
      player.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        setPhase("idle");
      };
      await player.play();
    } catch (err) {
      setError(`TTS: ${(err as Error).message}`);
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
    setResult(null);
    setError(null);
  }

  useEffect(() => () => close(), []);

  const phaseLabel: Record<Phase, string> = {
    idle: "Нажми и говори",
    recording: "Слушаю…",
    processing: "Думаю…",
    speaking: "Говорю…",
    error: "Ошибка"
  };

  const isRecording = phase === "recording";
  const isBusy = phase === "processing" || phase === "speaking";

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
              className="glass-strong relative w-full max-w-md p-6 sm:p-8"
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

              <div className="mb-3 flex items-center justify-center gap-2 text-sm text-slate-300">
                {phase === "speaking" && (
                  <Volume2 className="h-4 w-4 animate-pulse text-neon-cyan" />
                )}
                <span>{phaseLabel[phase]}</span>
              </div>

              {/* Эмоция в процессе/после */}
              {result?.fused_emotion && (
                <div className="mb-4 flex justify-center">
                  <EmotionBadge
                    emotion={result.fused_emotion}
                    intensity={result.voice_emotion?.intensity ?? result.text_emotion?.intensity}
                    source={result.voice_emotion ? "voice" : "text"}
                  />
                </div>
              )}

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
                disabled={isBusy}
                aria-label={isRecording ? "Остановить" : "Начать запись"}
              >
                {isRecording ? (
                  <MicOff className="h-8 w-8 text-white" />
                ) : (
                  <Mic className="h-8 w-8 text-white" />
                )}
              </button>

              {result?.transcript && (
                <div className="mt-4 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-200">
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                    Ты ({result.transcript_provider})
                  </div>
                  {result.transcript}
                </div>
              )}

              {result?.reply && (
                <div className="mt-2 rounded-xl border border-neon-violet/30 bg-neon-violet/10 px-3 py-2 text-left text-xs text-slate-100">
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-neon-violet">
                    Фреди ({result.reply_model})
                  </div>
                  {result.reply}
                </div>
              )}

              {/* Top-3 эмоций по голосу — для wow-эффекта */}
              {result?.voice_emotion?.top_5 && result.voice_emotion.top_5.length > 0 && (
                <div className="mt-3 flex flex-wrap justify-center gap-1">
                  {result.voice_emotion.top_5.slice(0, 3).map((e) => (
                    <EmotionBadge
                      key={e.raw}
                      emotion={e.name}
                      intensity={Math.round(e.score * 10)}
                      className="text-[10px]"
                    />
                  ))}
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
