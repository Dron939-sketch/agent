"use client";

import { createContext, useContext, useEffect } from "react";
import { dict, type DictKey, type Locale } from "./dict";
import { useSession } from "@/store/session";

type Ctx = { locale: Locale; t: (key: DictKey) => string };

const I18nCtx = createContext<Ctx>({
  locale: "ru",
  t: (k) => dict.ru[k]
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = useSession((s) => s.locale);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
  }, [locale]);

  const value: Ctx = {
    locale,
    t: (key) => dict[locale][key] ?? dict.ru[key]
  };
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useT() {
  return useContext(I18nCtx).t;
}

export function useLocale() {
  return useContext(I18nCtx).locale;
}
