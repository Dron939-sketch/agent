"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { LogIn, UserPlus, X } from "lucide-react";
import { useSession } from "@/store/session";

type Mode = "login" | "register";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" ? "" : "http://localhost:8000");

async function apiPost(path: string, body: unknown) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export function AuthModal() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setAuth = useSession((s) => s.setAuth);

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener("freddy:open-auth", onOpen as EventListener);
    return () => window.removeEventListener("freddy:open-auth", onOpen as EventListener);
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        await apiPost("/api/auth/register", { username, email, password });
      }
      const tokens = (await apiPost("/api/auth/login", {
        username,
        password
      })) as { access_token: string };
      localStorage.setItem("freddy_token", tokens.access_token);
      setAuth(tokens.access_token, username);
      setOpen(false);
      setPassword("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            className="glass-strong relative w-full max-w-md p-6"
            initial={{ y: 20, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 280, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="absolute right-3 top-3 text-slate-400 hover:text-white"
              onClick={() => setOpen(false)}
              aria-label="Закрыть"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="mb-5 flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-neon-cyan via-neon-violet to-neon-pink shadow-neon" />
              <div>
                <div className="font-semibold">
                  {mode === "login" ? "Вход в Фреди" : "Регистрация"}
                </div>
                <div className="text-xs text-slate-400">
                  Продолжи беседу и получи доступ к памяти
                </div>
              </div>
            </div>

            <div className="mb-4 grid grid-cols-2 gap-1 rounded-xl bg-white/5 p-1 text-sm">
              {(["login", "register"] as Mode[]).map((m) => (
                <button
                  key={m}
                  className={`rounded-lg px-3 py-2 transition ${
                    mode === m
                      ? "bg-gradient-to-r from-neon-violet/70 to-neon-pink/70 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                  onClick={() => setMode(m)}
                >
                  {m === "login" ? "Вход" : "Регистрация"}
                </button>
              ))}
            </div>

            <div className="space-y-3">
              <input
                className="input"
                placeholder="Имя пользователя"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              {mode === "register" && (
                <input
                  className="input"
                  placeholder="Email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
              <input
                className="input"
                placeholder="Пароль"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {error && (
                <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                  {error}
                </div>
              )}
              <button
                className="btn-primary w-full py-3"
                onClick={submit}
                disabled={busy || !username || !password}
              >
                {mode === "login" ? (
                  <>
                    <LogIn className="mr-2 h-4 w-4" /> Войти
                  </>
                ) : (
                  <>
                    <UserPlus className="mr-2 h-4 w-4" /> Создать аккаунт
                  </>
                )}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
