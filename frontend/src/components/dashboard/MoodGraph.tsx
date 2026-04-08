"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Activity } from "lucide-react";
import { resolveApiUrl } from "@/lib/api";
import { useSession } from "@/store/session";

type MoodPoint = {
  timestamp: string;
  primary: string;
  intensity: number;
  confidence: number;
  tone?: string | null;
};

type MoodGraphResponse = {
  days: number;
  points: MoodPoint[];
  distribution: Record<string, number>;
  dominant: string | null;
  avg_intensity: number;
};

const EMOTION_COLORS: Record<string, string> = {
  joy: "#fbbf24",
  ecstasy: "#f59e0b",
  serenity: "#fcd34d",
  sadness: "#60a5fa",
  grief: "#3b82f6",
  pensiveness: "#93c5fd",
  anger: "#ef4444",
  rage: "#dc2626",
  annoyance: "#f87171",
  fear: "#a78bfa",
  terror: "#7c3aed",
  apprehension: "#c4b5fd",
  surprise: "#22d3ee",
  amazement: "#06b6d4",
  distraction: "#67e8f9",
  trust: "#34d399",
  admiration: "#10b981",
  acceptance: "#6ee7b7",
  disgust: "#84cc16",
  loathing: "#65a30d",
  boredom: "#a3e635",
  anticipation: "#fb923c",
  vigilance: "#ea580c",
  interest: "#fdba74",
  love: "#f472b6",
  remorse: "#a855f7",
  contempt: "#71717a",
  optimism: "#facc15",
  confusion: "#94a3b8",
  calm: "#86efac",
  neutral: "#94a3b8"
};

type Props = { id?: string };

export function MoodGraph({ id }: Props) {
  const token = useSession((s) => s.token);
  const [data, setData] = useState<MoodGraphResponse | null>(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const API = useMemo(() => resolveApiUrl(), []);

  async function load() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/dashboard/mood?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error(`mood ${res.status}`);
      const json = (await res.json()) as MoodGraphResponse;
      setData(json);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, days]);

  return (
    <section id={id} className="mx-auto mt-6 max-w-7xl px-6">
      <div className="glass p-5">
        <div className="mb-4 flex items-center gap-2">
          <Activity className="h-4 w-4 text-neon-violet" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Эмоциональный график
          </h2>
          <div className="ml-auto flex gap-1">
            {[1, 7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded-md px-2 py-1 text-[10px] uppercase tracking-wider transition ${
                  days === d
                    ? "bg-neon-violet/30 text-white"
                    : "border border-white/10 text-slate-400 hover:text-white"
                }`}
              >
                {d === 1 ? "сутки" : `${d} дней`}
              </button>
            ))}
          </div>
        </div>

        {!token && (
          <div className="text-center text-sm text-slate-500">
            Войди, чтобы увидеть график своего настроения.
          </div>
        )}

        {token && error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        {token && loading && (
          <div className="text-center text-sm text-slate-500">Загружаю…</div>
        )}

        {token && data && data.points.length === 0 && (
          <div className="text-center text-sm text-slate-500">
            Пока нет данных за этот период. Поговори со мной — я начну запоминать настроение.
          </div>
        )}

        {token && data && data.points.length > 0 && (
          <>
            <div className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-2 text-xs text-slate-400">
              <div>
                Доминирующая эмоция:{" "}
                <span
                  className="font-semibold"
                  style={{ color: data.dominant ? EMOTION_COLORS[data.dominant] : "#fff" }}
                >
                  {data.dominant ?? "—"}
                </span>
              </div>
              <div>
                Средняя интенсивность:{" "}
                <span className="font-semibold text-white">{data.avg_intensity.toFixed(1)}</span>
                /10
              </div>
              <div>
                Точек:{" "}
                <span className="font-semibold text-white">{data.points.length}</span>
              </div>
            </div>

            {/* Полоска времени с цветными штрихами */}
            <div className="mb-3 flex h-12 w-full overflow-hidden rounded-lg border border-white/10 bg-white/5">
              {data.points.map((p, i) => {
                const color = EMOTION_COLORS[p.primary] ?? "#94a3b8";
                const opacity = 0.3 + (p.intensity / 10) * 0.7;
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0 }}
                    animate={{ opacity }}
                    transition={{ delay: i * 0.005, duration: 0.3 }}
                    title={`${p.primary} ${p.intensity}/10 · ${p.timestamp}`}
                    className="flex-1 transition hover:opacity-100"
                    style={{ backgroundColor: color }}
                  />
                );
              })}
            </div>

            {/* Распределение эмоций */}
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.distribution)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([emo, count]) => {
                  const color = EMOTION_COLORS[emo] ?? "#94a3b8";
                  return (
                    <div
                      key={emo}
                      className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
                      style={{
                        borderColor: `${color}66`,
                        backgroundColor: `${color}1f`,
                        color
                      }}
                    >
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
                      />
                      <span className="capitalize">{emo}</span>
                      <span className="opacity-70">×{count}</span>
                    </div>
                  );
                })}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
