"use client";

import { useEffect } from "react";
import { getVapidPublicKey, subscribePush } from "@/lib/api";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return new Uint8Array([...raw].map((c) => c.charCodeAt(0)));
}

async function tryResubscribe(): Promise<void> {
  try {
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing) return;

    // Пермишн уже предоставлен — можно напрямую подписываться, без
    // вторичного requestPermission. Если пермишн не granted, мы сюда
    // не дойдём (см. верхний guard).
    const key = await getVapidPublicKey();
    if (!key) return;

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });
    await subscribePush(sub.toJSON());
  } catch (err) {
    console.warn("push subscribe failed:", err);
  }
}

/**
 * Подписывает браузер на web-push, НО только если пользователь УЖЕ
 * ранее дал permission (notification === "granted"). Chrome 80+
 * блокирует requestPermission() вызванный вне user gesture — и если
 * пользователь несколько раз проигнорировал prompt, браузер ставит
 * "denied" навсегда. Поэтому запрос permission должен происходить
 * через явную кнопку в UI (например в Settings), а этот компонент
 * только автоматически ресабскрайбает если разрешение уже есть.
 */
export function PushSubscribe() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (!("Notification" in window)) return;

    const token = localStorage.getItem("freddy_token");
    if (!token) return;

    // Тихий путь: permission уже granted → просто ресабскрайбимся.
    // Никаких requestPermission() без жеста — Chrome Violation + soft block.
    if (Notification.permission === "granted") {
      void tryResubscribe();
    }
    // default / denied — ничего не делаем. Запрос permission должен
    // инициироваться явным кликом в Settings/UI.
  }, []);

  return null;
}
