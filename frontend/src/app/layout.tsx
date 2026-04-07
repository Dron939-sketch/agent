import type { Metadata, Viewport } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/cmdk/CommandPalette";
import { AuthModal } from "@/components/auth/AuthModal";
import { Onboarding } from "@/components/onboarding/Onboarding";
import { I18nProvider } from "@/i18n/I18nProvider";
import { SWRegister } from "@/components/pwa/SWRegister";

export const metadata: Metadata = {
  title: "Фреди — всемогущий AI-помощник",
  description:
    "Персональный мульти-агентный AI с живым 3D-аватаром, памятью и инструментами.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/favicon.ico" },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Фреди"
  }
};

export const viewport: Viewport = {
  themeColor: "#a855f7",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className="dark">
      <body className="font-sans selection:bg-neon-violet/40">
        <I18nProvider>
          <CommandPalette>
            {children}
            <AuthModal />
            <Onboarding />
            <SWRegister />
          </CommandPalette>
        </I18nProvider>
      </body>
    </html>
  );
}
