"use client";

/**
 * Sprint 8 frontend: виджет напоминаний на дашборде.
 * Показывает список активных напоминаний + форма для создания.
 */

import { useEffect, useState, useCallback } from "react";
import { Bell, Plus, Clock, Trash2, X } from "lucide-react";
import { createReminder, listReminders, type ReminderInfo } from "@/lib/api";
import { useSession } from "@/store/session";

export function RemindersWidget() {
  const token = useSession((s) => s.token);
  const [reminders, setReminders] = useState<ReminderInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [text, setText] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await listReminders();
      setReminders(data.reminders);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
    // Refresh every 60s
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [load]);

  const handleCreate = async () => {
    if (!text.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const tzOffset = -(new Date().getTimezoneOffset() / 60);
      await createReminder(text.trim(), tzOffset);
      setText("");
      setShowForm(false);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const formatTime = (iso: string | null | undefined) => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = d.getTime() - now.getTime();
      const diffH = Math.round(diffMs / 3600000);
      if (diffH < 1) return `${Math.max(1, Math.round(diffMs / 60000))} мин`;
      if (diffH < 24) return `${diffH} ч`;
      const diffD = Math.round(diffH / 24);
      return `${diffD} дн`;
    } catch {
      return "";
    }
  };

  if (!token) return null;

  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-neon-cyan" />
          <span className="text-sm font-semibold">Напоминания</span>
          {reminders.length > 0 && (
            <span className="rounded-full bg-neon-cyan/20 px-1.5 text-[10px] text-neon-cyan">
              {reminders.length}
            </span>
          )}
        </div>
        <button
          className="rounded-lg border border-white/10 p-1 text-slate-400 transition hover:bg-white/10 hover:text-white"
          onClick={() => setShowForm(!showForm)}
          aria-label="Добавить напоминание"
        >
          {showForm ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="border-b border-white/5 p-3">
          <input
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white placeholder-slate-500 outline-none focus:border-neon-cyan/50"
            placeholder='Через 2 часа позвонить маме...'
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            disabled={creating}
          />
          <div className="mt-2 flex items-center justify-between">
            <span className="text-[10px] text-slate-500">
              Поддерживает: "через 2 часа", "завтра в 9", "каждый день"
            </span>
            <button
              className="rounded-lg bg-neon-cyan/20 px-3 py-1 text-[10px] text-neon-cyan transition hover:bg-neon-cyan/30 disabled:opacity-50"
              onClick={handleCreate}
              disabled={creating || !text.trim()}
            >
              {creating ? "..." : "Создать"}
            </button>
          </div>
          {error && (
            <div className="mt-1 text-[10px] text-red-400">{error}</div>
          )}
        </div>
      )}

      {/* Reminder list */}
      <div className="max-h-48 overflow-y-auto">
        {loading && reminders.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">Загрузка...</div>
        ) : reminders.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">
            Нет активных напоминаний
          </div>
        ) : (
          reminders.map((r) => (
            <div
              key={r.id || r.task_id}
              className="flex items-center gap-2 border-b border-white/5 px-4 py-2.5 last:border-0"
            >
              <Clock className="h-3.5 w-3.5 flex-shrink-0 text-slate-500" />
              <div className="flex-1 min-w-0">
                <div className="truncate text-xs text-white">{r.title}</div>
                <div className="flex items-center gap-2 text-[10px] text-slate-500">
                  {r.scheduled_at && (
                    <span>через {formatTime(r.scheduled_at)}</span>
                  )}
                  {r.recurrence && (
                    <span className="rounded bg-neon-violet/20 px-1 text-neon-violet">
                      {r.recurrence}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
