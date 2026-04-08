"use client";

/**
 * WakeWordDetector: непрерывное прослушивание через Web Speech API.
 *
 * Использует браузерный SpeechRecognition для фонового распознавания речи.
 * Когда в interim/final результатах обнаруживается wake word "Фреди",
 * вызывается callback `onWake`. Автоматически перезапускается при обрыве.
 *
 * Поддерживаемые варианты wake word: фреди, фредди, freddy, fredi.
 */

export type WakeWordOptions = {
  /** Callback при обнаружении wake word. Получает текст после wake word (если есть). */
  onWake: (trailing: string) => void;
  /** Callback при изменении статуса (listening / paused / error). */
  onStatusChange?: (status: WakeWordStatus) => void;
  /** Язык распознавания. По умолчанию "ru-RU". */
  lang?: string;
};

export type WakeWordStatus = "listening" | "paused" | "stopped" | "error" | "unsupported";

// Варианты написания wake word (lowercase)
const WAKE_VARIANTS = ["фреди", "фредди", "freddy", "fredi", "фрэди", "фрэдди"];

// Regex для поиска wake word в тексте
const WAKE_REGEX = new RegExp(
  `(?:^|\\s)(${WAKE_VARIANTS.join("|")})(?:[,!.?\\s]|$)`,
  "i"
);

/**
 * Извлекает текст после wake word из строки.
 * Возвращает null если wake word не найден.
 */
export function extractAfterWakeWord(text: string): { found: true; trailing: string } | { found: false } {
  const lower = text.toLowerCase().trim();
  for (const variant of WAKE_VARIANTS) {
    const idx = lower.indexOf(variant);
    if (idx !== -1) {
      const after = text.slice(idx + variant.length).replace(/^[,!.?\s]+/, "").trim();
      return { found: true, trailing: after };
    }
  }
  return { found: false };
}

/**
 * Проверяет поддержку Web Speech API в текущем браузере.
 */
export function isWakeWordSupported(): boolean {
  if (typeof window === "undefined") return false;
  return !!(
    (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition
  );
}

function getSpeechRecognitionClass(): (new () => SpeechRecognition) | null {
  if (typeof window === "undefined") return null;
  return (
    (window as unknown as { SpeechRecognition?: new () => SpeechRecognition }).SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognition }).webkitSpeechRecognition ||
    null
  );
}

export class WakeWordDetector {
  private recognition: SpeechRecognition | null = null;
  private status: WakeWordStatus = "stopped";
  private onWake: WakeWordOptions["onWake"];
  private onStatusChange: WakeWordOptions["onStatusChange"];
  private lang: string;
  private intentionalStop = false;
  private restartTimeout: ReturnType<typeof setTimeout> | null = null;
  /** Предотвращает двойной вызов onWake на одном и том же результате. */
  private lastWakeTimestamp = 0;

  constructor(opts: WakeWordOptions) {
    this.onWake = opts.onWake;
    this.onStatusChange = opts.onStatusChange;
    this.lang = opts.lang ?? "ru-RU";
  }

  /** Запускает непрерывное прослушивание. */
  start(): boolean {
    const SRClass = getSpeechRecognitionClass();
    if (!SRClass) {
      this.setStatus("unsupported");
      return false;
    }

    this.intentionalStop = false;
    this.cleanup();

    const recognition = new SRClass();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = this.lang;
    recognition.maxAlternatives = 3;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      this.handleResults(event);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // "no-speech" — нормальная ситуация, просто тишина
      if (event.error === "no-speech" || event.error === "aborted") {
        return;
      }
      console.warn("[WakeWord] error:", event.error);
      if (event.error === "not-allowed") {
        this.setStatus("error");
        return;
      }
      // Для остальных ошибок — перезапуск
      this.scheduleRestart();
    };

    recognition.onend = () => {
      if (!this.intentionalStop) {
        // SpeechRecognition может останавливаться сам — перезапускаем
        this.scheduleRestart();
      }
    };

    this.recognition = recognition;

    try {
      recognition.start();
      this.setStatus("listening");
      return true;
    } catch (err) {
      console.error("[WakeWord] start failed:", err);
      this.setStatus("error");
      return false;
    }
  }

  /** Останавливает прослушивание. */
  stop(): void {
    this.intentionalStop = true;
    this.cleanup();
    this.setStatus("stopped");
  }

  /** Временная пауза (например, во время записи полного сообщения). */
  pause(): void {
    this.intentionalStop = true;
    this.cleanup();
    this.setStatus("paused");
  }

  /** Возобновление после паузы. */
  resume(): void {
    this.start();
  }

  getStatus(): WakeWordStatus {
    return this.status;
  }

  private handleResults(event: SpeechRecognitionEvent) {
    const now = Date.now();
    // Защита от двойного срабатывания (минимум 2 секунды между активациями)
    if (now - this.lastWakeTimestamp < 2000) return;

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      // Проверяем все альтернативы
      for (let j = 0; j < result.length; j++) {
        const transcript = result[j].transcript;
        const match = extractAfterWakeWord(transcript);
        if (match.found) {
          this.lastWakeTimestamp = now;
          // Пауза на время обработки — VoiceRecorder возобновит при необходимости
          this.pause();
          this.onWake(match.trailing);
          return;
        }
      }
    }
  }

  private scheduleRestart(): void {
    if (this.intentionalStop) return;
    if (this.restartTimeout) clearTimeout(this.restartTimeout);
    this.restartTimeout = setTimeout(() => {
      this.restartTimeout = null;
      if (!this.intentionalStop) {
        this.start();
      }
    }, 300);
  }

  private cleanup(): void {
    if (this.restartTimeout) {
      clearTimeout(this.restartTimeout);
      this.restartTimeout = null;
    }
    if (this.recognition) {
      try {
        this.recognition.onresult = null;
        this.recognition.onerror = null;
        this.recognition.onend = null;
        this.recognition.abort();
      } catch {}
      this.recognition = null;
    }
  }

  private setStatus(s: WakeWordStatus): void {
    if (this.status === s) return;
    this.status = s;
    this.onStatusChange?.(s);
  }
}
