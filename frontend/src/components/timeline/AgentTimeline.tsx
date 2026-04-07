"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Workflow } from "lucide-react";
import { openAgentSocket, type AgentStep } from "@/lib/api";
import { useSession } from "@/store/session";

type Props = { id?: string };

const KIND_COLOR: Record<string, string> = {
  thought: "bg-neon-cyan/15 border-neon-cyan/40 text-neon-cyan",
  action: "bg-neon-violet/15 border-neon-violet/40 text-neon-violet",
  observation: "bg-neon-lime/10 border-neon-lime/40 text-neon-lime",
  final: "bg-neon-pink/15 border-neon-pink/50 text-neon-pink",
  error: "bg-red-500/10 border-red-500/50 text-red-300",
  agent_start: "bg-white/5 border-white/10 text-slate-200",
  agent_end: "bg-white/5 border-white/10 text-slate-400"
};

export function AgentTimeline({ id }: Props) {
  const token = useSession((s) => s.token);
  const [task, setTask] = useState("");
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  function run() {
    if (!task.trim() || running) return;
    if (!token) {
      window.dispatchEvent(new CustomEvent("freddy:open-auth"));
      return;
    }
    setSteps([]);
    setError(null);
    setRunning(true);
    const ws = openAgentSocket(
      { task, mode: "pipeline", profile: "smart" },
      (evt) => {
        if (evt.type === "step") {
          setSteps((s) => [...s, evt.step]);
        }
        if (evt.type === "done") {
          setRunning(false);
        }
        if (evt.type === "error") {
          setError(evt.message);
          setRunning(false);
        }
      },
      () => setRunning(false)
    );
    if (!ws) {
      setRunning(false);
      setError("Не удалось открыть соединение");
      return;
    }
    socketRef.current = ws;
  }

  useEffect(() => () => socketRef.current?.close(), []);

  return (
    <section id={id} className="glass flex h-[560px] flex-col p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-slate-300">
        <Workflow className="h-4 w-4 text-neon-cyan" />
        <span>Agent Timeline</span>
        <span className="ml-auto text-xs text-slate-500">
          {token ? "pipeline · WS live" : "guest"}
        </span>
      </div>

      <div className="mb-3 flex gap-2">
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder={token ? "Что должен сделать Фреди?" : "Сначала войди →"}
          className="input"
        />
        <button
          onClick={run}
          disabled={running}
          className="btn-primary h-[46px] px-4 disabled:opacity-60"
        >
          <Play className="h-4 w-4" />
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="scrollbar-thin flex-1 space-y-2 overflow-y-auto pr-2">
        <AnimatePresence initial={false}>
          {steps.map((s, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              className={`rounded-xl border px-3 py-2 text-xs ${KIND_COLOR[s.kind] ?? "border-white/10 bg-white/5 text-slate-200"}`}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono uppercase tracking-wider opacity-80">
                  {s.kind}
                </span>
                <span className="text-slate-400">· {s.agent}</span>
                {s.tool && (
                  <span className="ml-auto rounded-md bg-black/30 px-2 py-0.5 font-mono">
                    {s.tool}
                  </span>
                )}
              </div>
              {s.content && (
                <div className="mt-1 whitespace-pre-wrap break-words font-mono leading-relaxed">
                  {s.content}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {steps.length === 0 && !running && (
          <div className="flex h-full items-center justify-center text-center text-xs text-slate-500">
            Здесь появятся шаги мульти-агента:
            <br />
            Planner → Researcher → Coder → Critic → Executor
          </div>
        )}
      </div>
    </section>
  );
}
