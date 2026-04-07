"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import dynamic from "next/dynamic";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { AgentTimeline } from "@/components/timeline/AgentTimeline";

const FreddyAvatar = dynamic(
  () => import("@/components/avatar/FreddyAvatar").then((m) => m.FreddyAvatar),
  { ssr: false }
);

type AgentState = "idle" | "thinking" | "speaking";

export default function HomePage() {
  const [agentState, setAgentState] = useState<AgentState>("idle");

  return (
    <main className="relative min-h-screen">
      <header className="flex items-center justify-between px-8 py-6">
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
        <nav className="hidden gap-6 text-sm text-slate-400 md:flex">
          <a className="hover:text-white" href="#chat">Чат</a>
          <a className="hover:text-white" href="#agents">Агенты</a>
          <a className="hover:text-white" href="#memory">Память</a>
          <kbd className="rounded-md border border-white/10 px-2 py-0.5 text-xs text-slate-400">
            ⌘K
          </kbd>
        </nav>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 px-6 pb-16 md:grid-cols-[1.1fr_1fr] lg:grid-cols-[1.2fr_1fr_0.9fr]">
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

      <footer className="px-8 pb-10 text-center text-xs text-slate-500">
        Фаза 3 · WOW UI · Next.js 14 + R3F + Framer Motion
      </footer>
    </main>
  );
}
