import type { Metadata } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/cmdk/CommandPalette";
import { AuthModal } from "@/components/auth/AuthModal";
import { Onboarding } from "@/components/onboarding/Onboarding";

export const metadata: Metadata = {
  title: "Фреди — всемогущий AI-помощник",
  description:
    "Персональный мульти-агентный AI с живым 3D-аватаром, памятью и инструментами.",
  icons: { icon: "/favicon.ico" }
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className="dark">
      <body className="font-sans selection:bg-neon-violet/40">
        <CommandPalette>
          {children}
          <AuthModal />
          <Onboarding />
        </CommandPalette>
      </body>
    </html>
  );
}
