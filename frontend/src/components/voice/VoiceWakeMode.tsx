"use client";

/**
 * VoiceWakeMode — режим постоянного прослушивания с wake word "Фреди".
 *
 * Фазы:
 *   listening  → фоновое прослушивание (Web Speech API), ждём "Фреди"
 *   recording  → wake word обнаружен, записываем полное сообщение (MediaRecorder)
 *   processing → отправляем на бэкенд (full-loop)
 *   speaking   → воспроизводим ответ TTS
 *   error      → ошибка (показывается кратко, затем возврат к listening)
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Ear, Mic, MicOff, Volume2, X, Radio, Bell } from "lucide-react";
import { streamSpeech, voiceFullLoop, openTriggerSocket, type FullLoopResponse, type TriggerEvent } from "@/lib/api";
import { useSession } from "@/store/session";
import { SilenceDetector } from "@/lib/vad";
import { WakeWordDetector, isWakeWordSupported, type WakeWordStatus } from "@/lib/wakeword";
import { EmotionBadge } from "./EmotionBadge";

/**
 * Фазы:
 *   listening    → ждём wake word "Фреди"
 *   follow_up    → 30с окно: слушаем продолжение без wake word
 *   recording    → записываем полное сообщение
 *   processing   → отправляем на бэкенд
 *   speaking     → воспроизводим ответ (можно прервать "Стоп")
 *   error        → ошибка
 */
type Phase = "listening" | "follow_up" | "recording" | "processing" | "speaking" | "error";

/** Сколько секунд ждём продолжения диалога без wake word. */
const FOLLOW_UP_WINDOW_MS = 30_000;

/** Стоп-слова для прерывания воспроизведения. */
const STOP_WORDS = ["стоп", "хватит", "замолчи", "тихо", "stop", "enough"];

export function VoiceWakeMode() {
  const token = useSession((s) => s.token);
  const voice = useSession((s) => s.voice);
  const alwaysListening = useSession((s) => s.alwaysListening);
  const setAlwaysListening = useSession((s) => s.setAlwaysListening);

  const [phase, setPhase] = useState<Phase>("listening");
  const [wakeStatus, setWakeStatus] = useState<WakeWordStatus>("stopped");
  const [level, setLevel] = useState<number[]>(new Array(48).fill(0));
  const [result, setResult] = useState<FullLoopResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [supported] = useState(() => isWakeWordSupported());
  const [notification, setNotification] = useState<TriggerEvent | null>(null);
  const [followUpCountdown, setFollowUpCountdown] = useState(0);

  const wakeRef = useRef<WakeWordDetector | null>(null);
  const triggerWsRef = useRef<WebSocket | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const vadRef = useRef<SilenceDetector | null>(null);
  const playerRef = useRef<HTMLAudioElement | null>(null);
  const followUpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const interruptDetectorRef = useRef<SpeechRecognition | null>(null);

  // --- Cleanup helpers ---

  const cleanupRecording = useCallback(() => {
    try { recorderRef.current?.stop(); } catch {}
    mediaRef.current?.getTracks().forEach((t) => t.stop());
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    audioCtxRef.current?.close().catch(() => {});
    vadRef.current?.stop();
    rafRef.current = null;
    vadRef.current = null;
    recorderRef.current = null;
    mediaRef.current = null;
    audioCtxRef.current = null;
    setLevel(new Array(48).fill(0));
  }, []);

  const stopInterruptDetector = useCallback(() => {
    if (interruptDetectorRef.current) {
      try {
        interruptDetectorRef.current.onresult = null;
        interruptDetectorRef.current.onend = null;
        interruptDetectorRef.current.onerror = null;
        interruptDetectorRef.current.abort();
      } catch {}
      interruptDetectorRef.current = null;
    }
  }, []);

  const clearFollowUpTimer = useCallback(() => {
    if (followUpTimerRef.current) {
      clearTimeout(followUpTimerRef.current);
      followUpTimerRef.current = null;
    }
    setFollowUpCountdown(0);
  }, []);

  const cleanupAll = useCallback(() => {
    cleanupRecording();
    clearFollowUpTimer();
    stopInterruptDetector();
    wakeRef.current?.stop();
    wakeRef.current = null;
    if (triggerWsRef.current) {
      try { triggerWsRef.current.close(); } catch {}
      triggerWsRef.current = null;
    }
    if (playerRef.current) {
      try { playerRef.current.pause(); } catch {}
      playerRef.current = null;
    }
  }, [cleanupRecording, clearFollowUpTimer, stopInterruptDetector]);

  // --- Wake word detected → start recording ---

  const startRecording = useCallback(async () => {
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
          if (recorderRef.current?.state === "recording") {
            try { recorderRef.current.stop(); } catch {}
          }
        },
        threshold: 0.05,
        silenceMs: 1500,
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
          // Слишком короткая запись — возвращаемся к прослушиванию
          returnToListening();
          return;
        }
        await runFullLoop(blob);
      };
      recorderRef.current = recorder;
      recorder.start();
    } catch (err) {
      setError((err as Error).message);
      setPhase("error");
      setTimeout(() => returnToListening(), 3000);
    }
  }, [token, cleanupRecording]);

  // --- Full loop pipeline ---

  const runFullLoop = useCallback(async (blob: Blob) => {
    setPhase("processing");
    let response: FullLoopResponse;
    try {
      response = await voiceFullLoop(blob);
      setResult(response);
    } catch (err) {
      setError((err as Error).message);
      setPhase("error");
      setTimeout(() => returnToListening(), 3000);
      return;
    }

    if (!response.reply) {
      returnToListening();
      return;
    }

    setPhase("speaking");
    try {
      const tone = response.fused_tone || "warm";
      const audioUrl = await streamSpeech(response.reply.slice(0, 1000), { tone, voice });
      const player = new Audio(audioUrl);
      playerRef.current = player;

      // Start interrupt detector — user can say "Стоп" to interrupt
      startInterruptDetector();

      player.onended = () => {
        URL.revokeObjectURL(audioUrl);
        playerRef.current = null;
        stopInterruptDetector();
        returnToListening();
      };
      player.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        playerRef.current = null;
        stopInterruptDetector();
        returnToListening();
      };
      await player.play();
    } catch (err) {
      setError(`TTS: ${(err as Error).message}`);
      stopInterruptDetector();
      returnToListening();
    }
  }, [voice, startInterruptDetector, stopInterruptDetector]);

  // --- Interrupt detection: listen for "Стоп" during speaking ---

  const startInterruptDetector = useCallback(() => {
    stopInterruptDetector();
    const SRClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SRClass) return;

    const sr = new SRClass();
    sr.continuous = true;
    sr.interimResults = true;
    sr.lang = "ru-RU";

    sr.onresult = (event: SpeechRecognitionEvent) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript.toLowerCase().trim();
        for (const sw of STOP_WORDS) {
          if (text.includes(sw)) {
            // Прерываем воспроизведение
            if (playerRef.current) {
              try { playerRef.current.pause(); } catch {}
              playerRef.current = null;
            }
            stopInterruptDetector();
            enterFollowUpMode();
            return;
          }
        }
      }
    };
    sr.onerror = () => {};
    sr.onend = () => { interruptDetectorRef.current = null; };

    try {
      sr.start();
      interruptDetectorRef.current = sr;
    } catch {}
  }, [stopInterruptDetector]);

  // --- Follow-up mode: 30s window to continue dialogue without wake word ---

  const enterFollowUpMode = useCallback(() => {
    clearFollowUpTimer();
    setPhase("follow_up");
    setError(null);
    setFollowUpCountdown(FOLLOW_UP_WINDOW_MS / 1000);

    // Pause wake word detector — we're in direct conversation mode
    wakeRef.current?.pause();

    // Countdown display
    const interval = setInterval(() => {
      setFollowUpCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    // Auto-exit follow-up after timeout
    followUpTimerRef.current = setTimeout(() => {
      clearInterval(interval);
      setFollowUpCountdown(0);
      followUpTimerRef.current = null;
      // Return to normal listening
      setPhase("listening");
      wakeRef.current?.resume();
    }, FOLLOW_UP_WINDOW_MS);
  }, [clearFollowUpTimer]);

  // --- Return to listening after interaction ---

  const returnToListening = useCallback(() => {
    setError(null);
    stopInterruptDetector();
    // After a conversation — enter follow-up mode instead of cold listening
    if (result?.reply) {
      enterFollowUpMode();
    } else {
      setPhase("listening");
      if (wakeRef.current) {
        wakeRef.current.resume();
      }
    }
  }, [result, enterFollowUpMode, stopInterruptDetector]);

  // --- Handle wake word detection ---

  const onWakeDetected = useCallback((_trailing: string) => {
    clearFollowUpTimer();
    startRecording();
  }, [startRecording, clearFollowUpTimer]);

  // --- Speak a proactive notification aloud ---

  const speakNotification = useCallback(async (message: string) => {
    if (phase !== "listening") return; // Don't interrupt active dialogue
    wakeRef.current?.pause();
    setPhase("speaking");
    try {
      const audioUrl = await streamSpeech(message.slice(0, 500), { tone: "warm", voice });
      const player = new Audio(audioUrl);
      playerRef.current = player;
      player.onended = () => {
        URL.revokeObjectURL(audioUrl);
        playerRef.current = null;
        setNotification(null);
        returnToListening();
      };
      player.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        playerRef.current = null;
        setNotification(null);
        returnToListening();
      };
      await player.play();
    } catch {
      setNotification(null);
      returnToListening();
    }
  }, [phase, voice, returnToListening]);

  // --- Handle incoming trigger events ---

  const handleTriggerEvent = useCallback((evt: TriggerEvent) => {
    if (evt.type !== "trigger" || !evt.message) return;
    setNotification(evt);
    // Speak HIGH/CRITICAL priority notifications aloud
    if (evt.priority === "HIGH" || evt.priority === "CRITICAL") {
      speakNotification(evt.message);
    }
  }, [speakNotification]);

  // --- Initialize / teardown wake word detector + trigger WebSocket ---

  useEffect(() => {
    if (!alwaysListening || !supported) {
      wakeRef.current?.stop();
      wakeRef.current = null;
      return;
    }

    const detector = new WakeWordDetector({
      onWake: onWakeDetected,
      onStatusChange: setWakeStatus,
      lang: "ru-RU",
    });
    wakeRef.current = detector;
    detector.start();

    // Connect to trigger WebSocket for proactive notifications
    const ws = openTriggerSocket(handleTriggerEvent, () => {
      triggerWsRef.current = null;
    });
    triggerWsRef.current = ws;

    setPhase("listening");

    return () => {
      detector.stop();
      wakeRef.current = null;
      if (triggerWsRef.current) {
        try { triggerWsRef.current.close(); } catch {}
        triggerWsRef.current = null;
      }
    };
  }, [alwaysListening, supported, onWakeDetected, handleTriggerEvent]);

  // Cleanup on unmount
  useEffect(() => () => cleanupAll(), [cleanupAll]);

  // --- Early return if not active ---
  if (!alwaysListening) return null;

  const phaseLabel: Record<Phase, string> = {
    listening: "Слушаю... скажи \"Фреди\"",
    follow_up: `Продолжай... (${followUpCountdown}с)`,
    recording: "Слушаю тебя...",
    processing: "Думаю...",
    speaking: "Говорю... (скажи \"Стоп\")",
    error: "Ошибка",
  };

  const isRecording = phase === "recording";
  const isBusy = phase === "processing" || phase === "speaking";
  const isListening = phase === "listening";
  const isFollowUp = phase === "follow_up";

  return (
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
        {/* Close button */}
        <button
          className="absolute right-3 top-3 text-slate-400 hover:text-white"
          onClick={() => {
            cleanupAll();
            setAlwaysListening(false);
          }}
          aria-label="Выключить режим Фреди"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Status line */}
        <div className="mb-3 flex items-center justify-center gap-2 text-sm text-slate-300">
          {isListening && (
            <Ear className="h-4 w-4 animate-pulse text-green-400" />
          )}
          {isFollowUp && (
            <Mic className="h-4 w-4 animate-pulse text-blue-400" />
          )}
          {phase === "speaking" && (
            <Volume2 className="h-4 w-4 animate-pulse text-neon-cyan" />
          )}
          {isRecording && (
            <Radio className="h-4 w-4 animate-pulse text-red-400" />
          )}
          <span>{phaseLabel[phase]}</span>
          {wakeStatus === "error" && (
            <span className="text-[10px] text-red-400">mic denied</span>
          )}
          {!supported && (
            <span className="text-[10px] text-amber-400">Speech API not supported</span>
          )}
        </div>

        {/* Emotion badge */}
        {result?.fused_emotion && (
          <div className="mb-4 flex justify-center">
            <EmotionBadge
              emotion={result.fused_emotion}
              intensity={result.voice_emotion?.intensity ?? result.text_emotion?.intensity}
              source={result.voice_emotion ? "voice" : "text"}
            />
          </div>
        )}

        {/* Visualizer */}
        <div className="mx-auto mb-4 flex h-24 w-full max-w-xs items-end justify-center gap-[3px]">
          {isListening ? (
            // Мягная зелёная пульсация — ждём wake word
            <div className="flex h-full w-full items-center justify-center">
              <motion.div
                className="h-16 w-16 rounded-full bg-gradient-to-br from-green-400/20 to-green-600/10 border border-green-400/30"
                animate={{
                  scale: [1, 1.15, 1],
                  opacity: [0.6, 1, 0.6],
                }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
            </div>
          ) : isFollowUp ? (
            // Синяя пульсация — ждём продолжения диалога
            <div className="flex h-full w-full items-center justify-center">
              <motion.div
                className="h-16 w-16 rounded-full bg-gradient-to-br from-blue-400/30 to-blue-600/10 border border-blue-400/40"
                animate={{
                  scale: [1, 1.2, 1],
                  opacity: [0.7, 1, 0.7],
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
            </div>
          ) : (
            level.map((v, i) => (
              <div
                key={i}
                className="w-1 rounded-full bg-gradient-to-t from-neon-cyan via-neon-violet to-neon-pink transition-[height]"
                style={{ height: `${Math.max(4, v * 100)}%` }}
              />
            ))
          )}
        </div>

        {/* Central button */}
        <button
          className={`mx-auto flex h-20 w-20 items-center justify-center rounded-full transition disabled:opacity-50 ${
            isListening
              ? "bg-gradient-to-br from-green-400 via-green-500 to-emerald-600 shadow-[0_0_40px_rgba(74,222,128,0.35)]"
              : isFollowUp
                ? "bg-gradient-to-br from-blue-400 via-blue-500 to-indigo-600 shadow-[0_0_40px_rgba(96,165,250,0.45)]"
                : isRecording
                  ? "bg-red-500/80 shadow-[0_0_60px_rgba(239,68,68,0.55)]"
                  : "bg-gradient-to-br from-neon-cyan via-neon-violet to-neon-pink shadow-neon"
          }`}
          onClick={
            isListening || isFollowUp
              ? () => { clearFollowUpTimer(); startRecording(); }
              : isRecording
                ? () => { try { recorderRef.current?.stop(); } catch {} }
                : phase === "speaking"
                  ? () => {
                      // Прервать озвучку по нажатию кнопки
                      if (playerRef.current) { try { playerRef.current.pause(); } catch {} playerRef.current = null; }
                      stopInterruptDetector();
                      enterFollowUpMode();
                    }
                  : undefined
          }
          disabled={phase === "processing"}
          aria-label={
            isListening
              ? "Начать запись вручную"
              : isFollowUp
                ? "Продолжить диалог"
                : isRecording
                  ? "Остановить запись"
                  : phase === "speaking"
                    ? "Прервать"
                    : "Обработка..."
          }
        >
          {isListening ? (
            <Ear className="h-8 w-8 text-white" />
          ) : isFollowUp ? (
            <Mic className="h-8 w-8 text-white" />
          ) : isRecording ? (
            <MicOff className="h-8 w-8 text-white" />
          ) : phase === "speaking" ? (
            <Volume2 className="h-8 w-8 text-white" />
          ) : (
            <Mic className="h-8 w-8 text-white" />
          )}
        </button>

        {/* Transcript */}
        {result?.transcript && (
          <div className="mt-4 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-200">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
              Ты ({result.transcript_provider})
            </div>
            {result.transcript}
          </div>
        )}

        {/* Reply */}
        {result?.reply && (
          <div className="mt-2 rounded-xl border border-neon-violet/30 bg-neon-violet/10 px-3 py-2 text-left text-xs text-slate-100">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-neon-violet">
              Фреди ({result.reply_model})
            </div>
            {result.reply}
          </div>
        )}

        {/* Voice emotion top items */}
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

        {/* Proactive notification */}
        {notification && notification.message && (
          <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-left text-xs text-amber-100">
            <div className="mb-1 flex items-center gap-1 text-[10px] uppercase tracking-wider text-amber-400">
              <Bell className="h-3 w-3" />
              <span>{notification.source || "trigger"}</span>
              {notification.priority && (
                <span className="ml-auto rounded bg-amber-500/20 px-1 text-amber-300">
                  {notification.priority}
                </span>
              )}
            </div>
            {notification.message}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        {/* Hint */}
        <div className="mt-4 text-center text-[10px] text-slate-500">
          {isListening
            ? "Скажи \"Фреди\" или нажми кнопку для записи"
            : isFollowUp
              ? "Продолжай говорить или нажми кнопку — wake word не нужен"
              : phase === "speaking"
                ? "Скажи \"Стоп\" или нажми кнопку чтобы прервать"
                : phase === "processing"
                  ? ""
                  : "Нажми для остановки записи"}
        </div>
      </motion.div>
    </motion.div>
  );
}
