"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Profile = "smart" | "fast" | "cheap" | "local";

type SessionState = {
  token: string | null;
  username: string | null;
  profile: Profile;
  onboarded: boolean;
  setAuth: (token: string, username: string) => void;
  logout: () => void;
  setProfile: (p: Profile) => void;
  markOnboarded: () => void;
};

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      profile: "smart",
      onboarded: false,
      setAuth: (token, username) => set({ token, username }),
      logout: () => set({ token: null, username: null }),
      setProfile: (profile) => set({ profile }),
      markOnboarded: () => set({ onboarded: true })
    }),
    {
      name: "freddy-session",
      partialize: (s) => ({
        token: s.token,
        username: s.username,
        profile: s.profile,
        onboarded: s.onboarded
      })
    }
  )
);
