"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageCircle, Link2, Unlink, Copy, Check, Loader2 } from "lucide-react";
import { resolveApiUrl } from "@/lib/api";
import { useSession } from "@/store/session";

type LinkStatus = { linked: boolean; chat_id: number | null };
type LinkCode = { code: string; bot_username: string; expires_in: number };

export function TelegramSettings() {
  const token = useSession((s) => s.token);
  const [status, setStatus] = useState<LinkStatus | null>(null);
  const [linkCode, setLinkCode] = useState<LinkCode | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const headers = useCallback(
    () => ({
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }),
    [token]
  );

  // Загрузка статуса привязки
  useEffect(() => {
    if (!token) return;
    fetch(`${resolveApiUrl()}/api/telegram/status`, { headers: headers() })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setStatus(data))
      .catch(() => {});
  }, [token, headers]);

  // Генерация кода привязки
  async function generateCode() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${resolveApiUrl()}/api/telegram/link-code`, {
        method: "POST",
        headers: headers(),
      });
      if (!res.ok) throw new Error("Ошибка генерации кода");
      const data: LinkCode = await res.json();
      setLinkCode(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  // Отвязка
  async function unlink() {
    setLoading(true);
    try {
      await fetch(`${resolveApiUrl()}/api/telegram/unlink`, {
        method: "DELETE",
        headers: headers(),
      });
      setStatus({ linked: false, chat_id: null });
      setLinkCode(null);
    } catch {} finally {
      setLoading(false);
    }
  }

  // Копирование кода
  function copyCode(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (!token) return null;

  return (
    <div className="glass rounded-2xl p-4 sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <MessageCircle className="h-5 w-5 text-sky-400" />
        <h3 className="font-medium">Telegram</h3>
      </div>

      {status?.linked ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-green-400">
            <Link2 className="h-4 w-4" />
            <span>Привязан (ID: {status.chat_id})</span>
          </div>
          <p className="text-xs text-slate-400">
            Фреди отправляет напоминания и отвечает на голосовые в Telegram.
          </p>
          <button
            onClick={unlink}
            disabled={loading}
            className="flex items-center gap-1 rounded-lg bg-red-500/20 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/30 transition"
          >
            <Unlink className="h-3 w-3" />
            Отвязать
          </button>
        </div>
      ) : linkCode ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-300">
            1. Откройте бот{" "}
            <a
              href={`https://t.me/${linkCode.bot_username}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sky-400 underline"
            >
              @{linkCode.bot_username}
            </a>
          </p>
          <p className="text-sm text-slate-300">2. Отправьте команду:</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded-lg bg-white/10 px-3 py-2 font-mono text-lg tracking-widest text-white">
              /link {linkCode.code}
            </code>
            <button
              onClick={() => copyCode(`/link ${linkCode.code}`)}
              className="rounded-lg bg-white/10 p-2 hover:bg-white/20 transition"
              title="Скопировать"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-400" />
              ) : (
                <Copy className="h-4 w-4 text-slate-400" />
              )}
            </button>
          </div>
          <p className="text-xs text-slate-500">
            Код действителен 5 минут
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-slate-400">
            Привяжите Telegram чтобы получать напоминания и общаться с Фреди голосом.
          </p>
          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}
          <button
            onClick={generateCode}
            disabled={loading}
            className="btn-primary flex items-center gap-2 px-4 py-2 text-sm"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Link2 className="h-4 w-4" />
            )}
            Привязать Telegram
          </button>
        </div>
      )}
    </div>
  );
}
