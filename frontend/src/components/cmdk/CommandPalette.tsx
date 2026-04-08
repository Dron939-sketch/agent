"use client";

import {
  KBarProvider,
  KBarPortal,
  KBarPositioner,
  KBarAnimator,
  KBarSearch,
  KBarResults,
  useMatches
} from "kbar";
import {
  Languages,
  LogIn,
  LogOut,
  MessageSquare,
  Sparkles,
  Volume2,
  VolumeX,
  Workflow
} from "lucide-react";
import type { ReactNode } from "react";
import { useSession } from "@/store/session";

function RenderResults() {
  const { results } = useMatches();
  return (
    <KBarResults
      items={results}
      onRender={({ item, active }) =>
        typeof item === "string" ? (
          <div className="px-4 py-2 text-xs uppercase tracking-wider text-slate-500">
            {item}
          </div>
        ) : (
          <div
            className={`flex cursor-pointer items-center gap-3 px-4 py-3 text-sm ${
              active ? "bg-neon-violet/20 text-white" : "text-slate-200"
            }`}
          >
            {item.icon}
            <div className="flex-1">{item.name}</div>
            {item.shortcut?.length ? (
              <kbd className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-400">
                {item.shortcut.join(" ")}
              </kbd>
            ) : null}
          </div>
        )
      }
    />
  );
}

function scrollTo(id: string) {
  if (typeof document === "undefined") return;
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

export function CommandPalette({ children }: { children: ReactNode }) {
  const setProfile = useSession((s) => s.setProfile);
  const setLocale = useSession((s) => s.setLocale);
  const voiceReply = useSession((s) => s.voiceReply);
  const setVoiceReply = useSession((s) => s.setVoiceReply);
  const token = useSession((s) => s.token);
  const logout = useSession((s) => s.logout);

  const actions = [
    {
      id: "chat",
      name: "Чат · Chat",
      shortcut: ["g", "c"],
      keywords: "chat диалог",
      section: "Навигация",
      icon: <MessageSquare className="h-4 w-4 text-neon-cyan" />,
      perform: () => scrollTo("chat")
    },
    {
      id: "agents",
      name: "Agent Timeline",
      shortcut: ["g", "a"],
      keywords: "agents pipeline",
      section: "Навигация",
      icon: <Workflow className="h-4 w-4 text-neon-violet" />,
      perform: () => scrollTo("agents")
    },
    {
      id: "voice-toggle",
      name: voiceReply ? "🔊 Выключить озвучку" : "🔇 Включить озвучку",
      keywords: "voice tts mute speak",
      section: "Голос",
      icon: voiceReply ? (
        <VolumeX className="h-4 w-4 text-neon-pink" />
      ) : (
        <Volume2 className="h-4 w-4 text-neon-cyan" />
      ),
      perform: () => setVoiceReply(!voiceReply)
    },
    ...(token
      ? [
          {
            id: "logout",
            name: "Выйти",
            keywords: "logout signout exit",
            section: "Аккаунт",
            icon: <LogOut className="h-4 w-4 text-neon-pink" />,
            perform: () => {
              localStorage.removeItem("freddy_token");
              logout();
            }
          }
        ]
      : [
          {
            id: "login",
            name: "Войти / Sign in",
            keywords: "login auth signup",
            section: "Аккаунт",
            icon: <LogIn className="h-4 w-4 text-neon-pink" />,
            perform: () =>
              window.dispatchEvent(new CustomEvent("freddy:open-auth"))
          }
        ]),
    {
      id: "profile-smart",
      name: "Режим: Smart (Claude/GPT-4)",
      keywords: "profile smart claude gpt",
      section: "Режим LLM",
      icon: <Sparkles className="h-4 w-4 text-neon-lime" />,
      perform: () => setProfile("smart")
    },
    {
      id: "profile-fast",
      name: "Режим: Fast",
      keywords: "profile fast",
      section: "Режим LLM",
      icon: <Sparkles className="h-4 w-4 text-neon-cyan" />,
      perform: () => setProfile("fast")
    },
    {
      id: "profile-cheap",
      name: "Режим: Cheap",
      keywords: "profile cheap deepseek",
      section: "Режим LLM",
      icon: <Sparkles className="h-4 w-4 text-neon-pink" />,
      perform: () => setProfile("cheap")
    },
    {
      id: "profile-local",
      name: "Режим: Local (Ollama)",
      keywords: "profile local ollama",
      section: "Режим LLM",
      icon: <Sparkles className="h-4 w-4 text-neon-violet" />,
      perform: () => setProfile("local")
    },
    {
      id: "lang-ru",
      name: "Язык: Русский",
      keywords: "language locale russian",
      section: "Язык",
      icon: <Languages className="h-4 w-4 text-neon-cyan" />,
      perform: () => setLocale("ru")
    },
    {
      id: "lang-en",
      name: "Language: English",
      keywords: "language locale english",
      section: "Язык",
      icon: <Languages className="h-4 w-4 text-neon-lime" />,
      perform: () => setLocale("en")
    }
  ];

  return (
    <KBarProvider actions={actions}>
      <KBarPortal>
        <KBarPositioner className="z-50 bg-black/60 backdrop-blur-sm">
          <KBarAnimator className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-bg-soft/95 shadow-neon">
            <KBarSearch
              className="w-full bg-transparent px-5 py-4 text-base text-white placeholder:text-slate-500 focus:outline-none"
              placeholder="Ask Freddy or run a command…"
            />
            <div className="border-t border-white/5 py-2">
              <RenderResults />
            </div>
          </KBarAnimator>
        </KBarPositioner>
      </KBarPortal>
      {children}
    </KBarProvider>
  );
}
