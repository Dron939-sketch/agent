"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Locale } from "@/i18n/dict";

export type Profile = "smart" | "fast" | "cheap" | "local";

type SessionState = {
  token: string | null;
  username: string | null;
  profile: Profile;
  locale: Locale;
  onboarded: boolean;
  voiceReply: boolean;
  /** Голос TTS — id из каталога Yandex/ElevenLabs (madirus, filipp, jane, ...). */
  voice: string;
  setAuth: (token: string, username: string) => void;
  logout: () => void;
  setProfile: (p: Profile) => void;
  setLocale: (l: Locale) => void;
  setVoiceReply: (v: boolean) => void;
  setVoice: (v: string) => void;
  markOnboarded: () => void;
};

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      profile: "smart",
      locale: "ru",
      onboarded: false,
      voiceReply: true,
      voice: "madirus",
      setAuth: (token, username) => set({ token, username }),
      logout: () => set({ token: null, username: null }),
      setProfile: (profile) => set({ profile }),
      setLocale: (locale) => set({ locale }),
      setVoiceReply: (voiceReply) => set({ voiceReply }),
      setVoice: (voice) => set({ voice }),
      markOnboarded: () => set({ onboarded: true })
    }),
    {
      name: "freddy-session",
      partialize: (s) => ({
        token: s.token,
        username: s.username,
        profile: s.profile,
        locale: s.locale,
        onboarded: s.onboarded,
        voiceReply: s.voiceReply,
        voice: s.voice
      })
    }
  )
);
