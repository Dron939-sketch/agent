"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Locale } from "@/i18n/dict";

export type Profile = "smart" | "fast" | "cheap" | "local";

type SessionState = {
  token: string | null;
  refreshToken: string | null;
  username: string | null;
  profile: Profile;
  locale: Locale;
  onboarded: boolean;
  voiceReply: boolean;
  /** Голос TTS — id из каталога Yandex/ElevenLabs (madirus, filipp, jane, ...). */
  voice: string;
  /** Wake word "Фреди" — постоянное прослушивание в голосовом режиме. */
  alwaysListening: boolean;
  setAuth: (token: string, username: string, refreshToken?: string) => void;
  logout: () => void;
  setProfile: (p: Profile) => void;
  setLocale: (l: Locale) => void;
  setVoiceReply: (v: boolean) => void;
  setVoice: (v: string) => void;
  setAlwaysListening: (v: boolean) => void;
  markOnboarded: () => void;
};

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      username: null,
      profile: "smart",
      locale: "ru",
      onboarded: false,
      voiceReply: true,
      voice: "jarvis_fish",
      alwaysListening: false,
      setAuth: (token, username, refreshToken) => set({ token, username, refreshToken: refreshToken ?? null }),
      logout: () => set({ token: null, refreshToken: null, username: null }),
      setProfile: (profile) => set({ profile }),
      setLocale: (locale) => set({ locale }),
      setVoiceReply: (voiceReply) => set({ voiceReply }),
      setVoice: (voice) => set({ voice }),
      setAlwaysListening: (alwaysListening) => set({ alwaysListening }),
      markOnboarded: () => set({ onboarded: true })
    }),
    {
      name: "freddy-session",
      partialize: (s) => ({
        token: s.token,
        refreshToken: s.refreshToken,
        username: s.username,
        profile: s.profile,
        locale: s.locale,
        onboarded: s.onboarded,
        voiceReply: s.voiceReply,
        voice: s.voice,
        alwaysListening: s.alwaysListening
      })
    }
  )
);
