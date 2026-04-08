"use client";

/**
 * Sprint 6 frontend: панель проактивных уведомлений.
 * Подключается к WebSocket /api/triggers/ws и показывает уведомления.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, BellRing, X, AlertTriangle, Info, Zap } from "lucide-react";
import { openTriggerSocket, type TriggerEvent } from "@/lib/api";
import { useSession } from "@/store/session";

type Notification = TriggerEvent & {
  id: number;
  timestamp: Date;
  read: boolean;
};

let _nextId = 1;

export function NotificationPanel() {
  const token = useSession((s) => s.token);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleEvent = useCallback((evt: TriggerEvent) => {
    if (evt.type !== "trigger" || !evt.message) return;
    setNotifications((prev) => [
      {
        ...evt,
        id: _nextId++,
        timestamp: new Date(),
        read: false,
      },
      ...prev.slice(0, 49), // keep max 50
    ]);
  }, []);

  useEffect(() => {
    if (!token) return;

    const ws = openTriggerSocket(handleEvent, () => {
      wsRef.current = null;
      // Reconnect after 5s
      setTimeout(() => {
        if (wsRef.current === null) {
          const newWs = openTriggerSocket(handleEvent);
          wsRef.current = newWs;
        }
      }, 5000);
    });
    wsRef.current = ws;

    return () => {
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
        wsRef.current = null;
      }
    };
  }, [token, handleEvent]);

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const dismiss = (id: number) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  const priorityIcon = (priority?: string) => {
    switch (priority) {
      case "CRITICAL":
        return <AlertTriangle className="h-3.5 w-3.5 text-red-400" />;
      case "HIGH":
        return <Zap className="h-3.5 w-3.5 text-amber-400" />;
      default:
        return <Info className="h-3.5 w-3.5 text-slate-400" />;
    }
  };

  const priorityBorder = (priority?: string) => {
    switch (priority) {
      case "CRITICAL":
        return "border-red-500/30";
      case "HIGH":
        return "border-amber-400/30";
      default:
        return "border-white/5";
    }
  };

  const timeAgo = (date: Date) => {
    const s = Math.floor((Date.now() - date.getTime()) / 1000);
    if (s < 60) return "только что";
    if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
    if (s < 86400) return `${Math.floor(s / 3600)} ч назад`;
    return `${Math.floor(s / 86400)} дн назад`;
  };

  if (!token) return null;

  return (
    <div className="relative">
      {/* Bell button */}
      <button
        className="relative flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-400 transition hover:bg-white/10 hover:text-white"
        onClick={() => {
          setOpen(!open);
          if (!open) markAllRead();
        }}
        aria-label="Уведомления"
      >
        {unreadCount > 0 ? (
          <BellRing className="h-4 w-4 animate-pulse text-amber-400" />
        ) : (
          <Bell className="h-4 w-4" />
        )}
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            className="absolute right-0 top-11 z-50 w-80 overflow-hidden rounded-xl border border-white/10 bg-slate-900/95 shadow-2xl backdrop-blur-xl"
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.15 }}
          >
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
              <span className="text-xs font-semibold text-white">Уведомления</span>
              {notifications.length > 0 && (
                <button
                  className="text-[10px] text-slate-500 hover:text-white"
                  onClick={() => setNotifications([])}
                >
                  Очистить
                </button>
              )}
            </div>

            <div className="max-h-72 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-500">
                  Нет уведомлений. Фреди сообщит, когда будет что-то важное.
                </div>
              ) : (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    className={`group flex gap-2.5 border-b px-4 py-3 transition ${priorityBorder(n.priority)} ${
                      n.read ? "opacity-60" : ""
                    }`}
                  >
                    <div className="mt-0.5">{priorityIcon(n.priority)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] text-slate-500">
                        {n.source || "Фреди"} · {timeAgo(n.timestamp)}
                      </div>
                      <div className="mt-0.5 text-xs leading-relaxed text-white">
                        {n.message}
                      </div>
                    </div>
                    <button
                      className="mt-0.5 opacity-0 transition group-hover:opacity-100 text-slate-500 hover:text-white"
                      onClick={() => dismiss(n.id)}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
