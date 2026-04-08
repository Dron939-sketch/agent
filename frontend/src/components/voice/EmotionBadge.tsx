"use client";

import { motion, AnimatePresence } from "framer-motion";

/** Цвета по 24 эмоциям Plutchik (нагляднее, чем серый текст). */
const EMOTION_COLORS: Record<string, string> = {
  // Joy variants — жёлтые/оранжевые
  joy: "#fbbf24",
  ecstasy: "#f59e0b",
  serenity: "#fcd34d",
  // Sadness variants — синие
  sadness: "#60a5fa",
  grief: "#3b82f6",
  pensiveness: "#93c5fd",
  // Anger — красные
  anger: "#ef4444",
  rage: "#dc2626",
  annoyance: "#f87171",
  // Fear — фиолетовые
  fear: "#a78bfa",
  terror: "#7c3aed",
  apprehension: "#c4b5fd",
  // Surprise — циан
  surprise: "#22d3ee",
  amazement: "#06b6d4",
  distraction: "#67e8f9",
  // Trust — зелёные
  trust: "#34d399",
  admiration: "#10b981",
  acceptance: "#6ee7b7",
  // Disgust — болотные
  disgust: "#84cc16",
  loathing: "#65a30d",
  boredom: "#a3e635",
  // Anticipation — оранжевые
  anticipation: "#fb923c",
  vigilance: "#ea580c",
  interest: "#fdba74",
  // Композитные
  love: "#f472b6",
  remorse: "#a855f7",
  contempt: "#71717a",
  optimism: "#facc15",
  confusion: "#94a3b8",
  calm: "#86efac",
  neutral: "#94a3b8"
};

const EMOTION_LABELS: Record<string, string> = {
  joy: "радость",
  ecstasy: "восторг",
  serenity: "умиротворение",
  sadness: "грусть",
  grief: "горе",
  pensiveness: "задумчивость",
  anger: "злость",
  rage: "ярость",
  annoyance: "раздражение",
  fear: "страх",
  terror: "ужас",
  apprehension: "тревога",
  surprise: "удивление",
  amazement: "изумление",
  distraction: "растерянность",
  trust: "доверие",
  admiration: "восхищение",
  acceptance: "принятие",
  disgust: "отвращение",
  loathing: "омерзение",
  boredom: "скука",
  anticipation: "ожидание",
  vigilance: "бдительность",
  interest: "интерес",
  love: "любовь",
  remorse: "сожаление",
  contempt: "презрение",
  optimism: "оптимизм",
  confusion: "замешательство",
  calm: "спокойствие",
  neutral: "нейтрально"
};

type Props = {
  emotion: string | null;
  intensity?: number;
  source?: "voice" | "text" | "fused";
  className?: string;
};

export function EmotionBadge({ emotion, intensity, source, className }: Props) {
  if (!emotion) return null;
  const color = EMOTION_COLORS[emotion] ?? "#94a3b8";
  const label = EMOTION_LABELS[emotion] ?? emotion;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={emotion}
        initial={{ opacity: 0, y: -4, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 4, scale: 0.9 }}
        transition={{ duration: 0.25 }}
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${className ?? ""}`}
        style={{
          borderColor: `${color}66`,
          backgroundColor: `${color}1f`,
          color
        }}
      >
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }}
        />
        <span className="font-medium capitalize">{label}</span>
        {intensity != null && intensity > 0 && (
          <span className="opacity-70">{intensity}/10</span>
        )}
        {source && <span className="ml-1 text-[9px] uppercase opacity-60">{source}</span>}
      </motion.div>
    </AnimatePresence>
  );
}
