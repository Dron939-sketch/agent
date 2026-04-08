"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import dynamic from "next/dynamic";
import { LogIn, LogOut } from "lucide-react";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { AgentTimeline } from "@/components/timeline/AgentTimeline";
import { DashboardTiles } from "@/components/dashboard/DashboardTiles";
import { MoodGraph } from "@/components/dashboard/MoodGraph";
import { RemindersWidget } from "@/components/dashboard/RemindersWidget";
import { NotificationPanel } from "@/components/dashboard/NotificationPanel";
import { KnowledgeGraph } from "@/components/dashboard/KnowledgeGraph";
import { VoiceRecorder } from "@/components/voice/VoiceRecorder";
import { useSession } from "@/store/session";

const FreddyAvatar = dynamic(
  () => import("@/components/avatar/FreddyAvatar").then((m) => m.FreddyAvatar),
  { ssr: false }
);

type AgentState = "idle" | "thinking" | "speaking";

export default function HomePage() {
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const token = useSession((s) => s.token);
  const username = useSession((s) => s.username);
  const logout = useSession((s) => s.logout);

  function openAuth() {
    window.dispatchEvent(new CustomEvent("freddy:open-auth"));
  }

  function doLogout() {
    localStorage.removeItem("freddy_token");
    logout();
  }

  return (
    <main className="relative min-h-screen">
      <header className="flex items-center justify-between px-4 py-4 sm:px-8 sm:py-6">
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="flex items-center gap-3"
        >
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-neon-cyan via-neon-violet to-neon-pink shadow-neon" />
          <div>
            <div className="text-lg font-semibold tracking-tight">Фреди</div>
            <div className="text-xs text-slate-400">всемогущий AI-помощник</div>
          </div>
        </motion.div>
        <nav className="hidden gap-6 text-sm text-slate-400 md:flex md:items-center">
          <a className="hover:text-white" href="#chat">Чат</a>
          <a className="hover:text-white" href="#agents">Агенты</a>
          <a className="hover:text-white" href="#mood">Настроение</a>
          <a className="hover:text-white" href="#dashboard">Дашборд</a>
          <NotificationPanel />
          <kbd className="rounded-md border border-white/10 px-2 py-0.5 text-xs text-slate-400">
            ⌘K
          </kbd>
          {token ? (
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
          ) : (
            <button onClick={openAuth} className="btn-primary px-4 py-2 text-xs">
              <LogIn className="mr-1 h-3 w-3" /> Войти
            </button>
          )}
        </nav>
      </header>

      <section className="mx-auto grid max-w-7xl gap-4 px-4 pb-10 sm:gap-6 sm:px-6 md:grid-cols-[1.1fr_1fr] lg:grid-cols-[1.2fr_1fr_0.9fr]">
        <div className="glass relative aspect-square min-h-[320px] overflow-hidden md:aspect-auto md:min-h-[560px]">
          <div className="absolute inset-0 bg-aurora opacity-60" />
          <FreddyAvatar state={agentState} />
          <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between text-xs text-slate-300">
            <span className="rounded-full border border-white/10 bg-black/30 px-3 py-1 capitalize">
              {agentState}
            </span>
            <span className="text-slate-500">live 3D · react-three-fiber</span>
          </div>
        </div>

        <ChatPanel id="chat" onStateChange={setAgentState} />
        <AgentTimeline id="agents" />
      </section>

      <MoodGraph id="mood" />

      {/* Sprint 8+7: Reminders + Knowledge Graph widgets */}
      <section className="mx-auto grid max-w-7xl gap-4 px-4 pb-6 sm:px-6 md:grid-cols-2">
        <RemindersWidget />
        <KnowledgeGraph />
      </section>

      <DashboardTiles id="dashboard" />

      <VoiceRecorder />

      <footer className="px-4 pb-10 text-center text-xs text-slate-500 sm:px-8">
        Фреди · Next.js 14 + R3F + Framer Motion · PWA · autonomous
      </footer>
    </main>
  );
}
