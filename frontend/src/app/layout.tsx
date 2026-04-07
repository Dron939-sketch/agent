import type { Metadata } from "next";
import "./globals.css";

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
        {children}
      </body>
    </html>
  );
}
