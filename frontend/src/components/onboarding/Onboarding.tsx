"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Brain, MessageSquare, Workflow } from "lucide-react";
import { useSession } from "@/store/session";
import { useT } from "@/i18n/I18nProvider";

export function Onboarding() {
  const onboarded = useSession((s) => s.onboarded);
  const markOnboarded = useSession((s) => s.markOnboarded);
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(false);
  const t = useT();

  const steps = [
    {
      icon: <MessageSquare className="h-8 w-8 text-neon-cyan" />,
      title: t("onboarding.step1.title"),
      text: t("onboarding.step1.text")
    },
    {
      icon: <Workflow className="h-8 w-8 text-neon-violet" />,
      title: t("onboarding.step2.title"),
      text: t("onboarding.step2.text")
    },
    {
      icon: <Brain className="h-8 w-8 text-neon-pink" />,
      title: t("onboarding.step3.title"),
      text: t("onboarding.step3.text")
    }
  ];

  useEffect(() => {
    if (!onboarded) setVisible(true);
  }, [onboarded]);

  function next() {
    if (idx < steps.length - 1) {
      setIdx((i) => i + 1);
      return;
    }
    markOnboarded();
    setVisible(false);
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            key={idx}
            className="glass-strong w-full max-w-md p-8 text-center"
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -24, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
          >
            <div className="mb-4 flex justify-center">{steps[idx].icon}</div>
            <h2 className="text-xl font-semibold">{steps[idx].title}</h2>
            <p className="mt-3 text-sm text-slate-300">{steps[idx].text}</p>

            <div className="mt-6 flex items-center justify-between">
              <div className="flex gap-1.5">
                {steps.map((_, i) => (
                  <div
                    key={i}
                    className={`h-1.5 rounded-full transition-all ${
                      i === idx ? "w-6 bg-neon-violet" : "w-1.5 bg-white/20"
                    }`}
                  />
                ))}
              </div>
              <button className="btn-primary" onClick={next}>
                {idx < steps.length - 1 ? t("onboarding.next") : t("onboarding.start")}
                <ArrowRight className="ml-2 h-4 w-4" />
              </button>
            </div>
            <button
              className="mt-3 text-xs text-slate-500 hover:text-slate-300"
              onClick={() => {
                markOnboarded();
                setVisible(false);
              }}
            >
              {t("onboarding.skip")}
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
