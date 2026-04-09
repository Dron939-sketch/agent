"use client";

/**
 * Header-вырезка для login/logout кнопки.
 *
 * Живёт в отдельном файле, чтобы её можно было подключить через
 * `dynamic(..., { ssr: false })` в page.tsx. Иначе условный рендер
 * `{token ? <Logout/> : <Login/>}` на основе persisted Zustand-стейта
 * вызывает hydration mismatch (server: null token → Login, client после
 * rehydrate → Logout).
 */

import { LogIn, LogOut } from "lucide-react";
import { useSession } from "@/store/session";

export function HeaderAuth() {
  const token = useSession((s) => s.token);
  const username = useSession((s) => s.username);
  const logout = useSession((s) => s.logout);

  function openAuth() {
    window.dispatchEvent(new CustomEvent("freddy:open-auth"));
  }

  function doLogout() {
    try {
      localStorage.removeItem("freddy_token");
    } catch {
      // no-op (iOS private mode и т.п.)
    }
    logout();
  }

  if (token) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-300">@{username}</span>
        <button
          onClick={doLogout}
          className="flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1 text-xs hover:border-neon-pink/40 hover:text-white"
        >
          <LogOut className="h-3 w-3" />
          Выйти
        </button>
      </div>
    );
  }

  return (
    <button onClick={openAuth} className="btn-primary px-4 py-2 text-xs">
      <LogIn className="mr-1 h-3 w-3" /> Войти
    </button>
  );
}
