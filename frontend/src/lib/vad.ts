"use client";

/**
 * Простой VAD на чистом WebAudio: вычисляет RMS-энергию входного потока
 * и вызывает onSilence() после `silenceMs` мс непрерывной тишины.
 *
 * Используется в `VoiceRecorder` для авто-остановки записи. Параметры
 * берутся из `process.env.NEXT_PUBLIC_VAD_MODE` ("webrtc" | "off").
 */

export type VadCallbacks = {
  onSilence: () => void;
  threshold?: number; // 0..1, дефолт 0.04
  silenceMs?: number; // дефолт 1500
};

export class SilenceDetector {
  private analyser: AnalyserNode;
  private buffer: Uint8Array;
  private raf: number | null = null;
  private silenceStart: number | null = null;
  private threshold: number;
  private silenceMs: number;
  private onSilence: () => void;
  private mode: string;

  constructor(stream: MediaStream, ctx: AudioContext, cb: VadCallbacks) {
    this.threshold = cb.threshold ?? 0.04;
    this.silenceMs = cb.silenceMs ?? 1500;
    this.onSilence = cb.onSilence;
    this.mode = process.env.NEXT_PUBLIC_VAD_MODE ?? "webrtc";

    const source = ctx.createMediaStreamSource(stream);
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 512;
    source.connect(this.analyser);
    this.buffer = new Uint8Array(this.analyser.fftSize);
  }

  start() {
    if (this.mode === "off") return;
    const tick = () => {
      this.analyser.getByteTimeDomainData(this.buffer);
      let sum = 0;
      for (let i = 0; i < this.buffer.length; i++) {
        const v = (this.buffer[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / this.buffer.length);
      const now = performance.now();
      if (rms < this.threshold) {
        if (this.silenceStart == null) this.silenceStart = now;
        else if (now - this.silenceStart >= this.silenceMs) {
          this.silenceStart = null;
          this.onSilence();
          return; // не продолжаем — клиент сам решит
        }
      } else {
        this.silenceStart = null;
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop() {
    if (this.raf != null) cancelAnimationFrame(this.raf);
    this.raf = null;
    this.silenceStart = null;
  }
}
