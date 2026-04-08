"use client";

/**
 * Sprint 7 frontend: визуализация графа знаний пользователя.
 * Показывает факты в виде группированного списка по категориям.
 * (Полная graph-визуализация через D3/vis-network — в будущем.)
 */

import { useEffect, useState, useCallback, type ReactNode } from "react";
import { Brain, User, Heart, Target, Briefcase, Activity, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { useSession } from "@/store/session";
import { resolveApiUrl } from "@/lib/api";

type KnowledgeFact = {
  subject: string;
  predicate: string;
  object: string;
  category: string;
  confidence: number;
  importance: number;
};

type KnowledgeData = {
  facts: KnowledgeFact[];
  categories: Record<string, number>;
  total: number;
};

type CategoryMeta = { label: string; icon: ReactNode; color: string };

// Фабрика мета-данных. Построение переезжает внутрь функции, чтобы JSX
// элементов (lucide-react иконок) не создавался на module-init level —
// это исключает TDZ на lazy-загруженных chunk'ах.
function buildCategoryMeta(): Record<string, CategoryMeta> {
  return {
    personal: { label: "Личное", icon: <User className="h-3.5 w-3.5" />, color: "text-blue-400" },
    preference: { label: "Предпочтения", icon: <Heart className="h-3.5 w-3.5" />, color: "text-pink-400" },
    goal: { label: "Цели", icon: <Target className="h-3.5 w-3.5" />, color: "text-emerald-400" },
    work: { label: "Работа", icon: <Briefcase className="h-3.5 w-3.5" />, color: "text-amber-400" },
    health: { label: "Здоровье", icon: <Activity className="h-3.5 w-3.5" />, color: "text-red-400" },
    relation: { label: "Отношения", icon: <User className="h-3.5 w-3.5" />, color: "text-violet-400" },
    habit: { label: "Привычки", icon: <RefreshCw className="h-3.5 w-3.5" />, color: "text-cyan-400" },
  };
}

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("freddy_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function KnowledgeGraph() {
  const token = useSession((s) => s.token);
  const [data, setData] = useState<KnowledgeData | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(["personal", "preference"]));
  // Мета лениво создаётся при первом render'е — внутри компонента, а не
  // на module-init level. JSX иконок тоже строится лениво.
  const [categoryMeta] = useState(() => buildCategoryMeta());

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      // API URL резолвится внутри callback — не на module-init level,
      // чтобы исключить TDZ при lazy chunk load.
      const apiUrl = resolveApiUrl();
      // Use the triggers check endpoint as a proxy for now,
      // or fetch facts directly if the API exists
      const res = await fetch(`${apiUrl}/api/triggers/check`, {
        headers: { ...authHeaders() },
      });
      // Knowledge graph doesn't have a dedicated REST API yet,
      // so we show a placeholder with instructions
      setData(null);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleCategory = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  if (!token) return null;

  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-neon-violet" />
          <span className="text-sm font-semibold">Граф знаний</span>
        </div>
        <button
          className="rounded-lg border border-white/10 p-1 text-slate-400 transition hover:bg-white/10 hover:text-white"
          onClick={load}
          disabled={loading}
          aria-label="Обновить"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="p-4">
        <div className="text-center text-xs text-slate-500">
          <Brain className="mx-auto mb-2 h-8 w-8 text-neon-violet/40" />
          <p>Граф знаний строится автоматически из каждого диалога.</p>
          <p className="mt-1">Расскажи Фреди о себе — он запомнит и будет использовать.</p>
          <div className="mt-3 grid grid-cols-2 gap-1.5">
            {Object.entries(categoryMeta).map(([key, meta]) => (
              <div
                key={key}
                className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-white/5 px-2 py-1.5"
              >
                <span className={meta.color}>{meta.icon}</span>
                <span className="text-[10px] text-slate-400">{meta.label}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[10px] text-slate-600">
            Примеры: "Запомни, что я работаю в Google", "Моя цель — выучить Go",
            "Я люблю итальянскую кухню"
          </p>
        </div>
      </div>
    </div>
  );
}
