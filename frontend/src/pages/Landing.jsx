import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Mic } from "lucide-react";
import { useLang } from "@/lib/lang";
import { useTitle } from "@/hooks/useRoomState";
import { Btn, LangToggle, Marquee, Wordmark } from "@/components/hh/kit";
import { normCode } from "@/lib/api";

export function CodeBox({ onGo, autoFocus = false, testid = "landing-code" }) {
  const { t } = useLang();
  const [code, setCode] = useState("");
  const submit = (e) => {
    e.preventDefault();
    if (code.length === 4) onGo(code);
  };
  return (
    <form onSubmit={submit} className="flex gap-3 items-stretch">
      <input
        data-testid={`${testid}-input`}
        className="hh-input flex-1 min-w-0 text-center uppercase"
        style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "0.4em", paddingLeft: "0.4em" }}
        value={code}
        maxLength={4}
        autoFocus={autoFocus}
        autoCapitalize="characters"
        autoComplete="off"
        spellCheck={false}
        inputMode="text"
        placeholder={t("code_placeholder")}
        aria-label={t("code_placeholder")}
        onChange={(e) => setCode(normCode(e.target.value))}
      />
      <Btn type="submit" variant="cyan" size="lg" disabled={code.length !== 4} data-testid={`${testid}-go`} aria-label={t("go")}>
        {t("go")} <ArrowRight size={20} />
      </Btn>
    </form>
  );
}

export default function Landing() {
  const { t } = useLang();
  const nav = useNavigate();
  useTitle(t("live_now"));
  const steps = [
    { n: "01", title: t("how_1_t"), d: t("how_1_d"), emoji: "📺" },
    { n: "02", title: t("how_2_t"), d: t("how_2_d"), emoji: "📱" },
    { n: "03", title: t("how_3_t"), d: t("how_3_d"), emoji: "🎤" },
  ];
  return (
    <div className="hh-bg">
      <header className="flex items-center justify-between px-4 sm:px-8 py-4 border-b-2 border-black bg-[var(--hh-surface)]">
        <Wordmark size="sm" />
        <LangToggle />
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-8 pt-10 sm:pt-16 pb-12 grid lg:grid-cols-[1.25fr_1fr] gap-10 lg:gap-14 items-start">
        <section>
          <div className="flex items-center gap-2 mb-6">
            <span className="hh-chip" style={{ background: "var(--hh-pink)", color: "#000" }}><Mic size={12} /> {t("live_now")}</span>
            <span className="hh-meta">{t("made_for")}</span>
          </div>
          <motion.div initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.25 }}>
            <div className="hh-tube inline-block px-5 py-4 sm:px-7 sm:py-6 bg-[#0B0B12] hh-swing" data-testid="landing-sign">
              <Wordmark size="lg" />
            </div>
          </motion.div>
          <h1 className="mt-8 text-3xl sm:text-5xl font-extrabold leading-[1.05] max-w-2xl" data-testid="landing-tagline">
            {t("tagline")}
          </h1>
          <p className="mt-4 text-lg sm:text-xl text-[var(--hh-muted)] max-w-xl" data-testid="landing-secondary">{t("secondary")}</p>
          <div className="hh-comedian-note mt-8" data-testid="landing-comedian-note">
            <Mic size={24} aria-hidden="true" />
            <div><strong>{t("your_material_title")}</strong><p>{t("your_material_body")}</p></div>
          </div>
        </section>

        <section className="flex flex-col gap-6">
          <div className="hh-ticket p-5 sm:p-6" data-testid="landing-join-card">
            <div className="flex items-center justify-between mb-1">
              <span className="hh-meta">{t("ticket_admit")}</span>
              <span className="hh-meta" style={{ color: "var(--hh-yellow)" }}>No. 0042</span>
            </div>
            <h2 className="text-2xl font-extrabold mb-4">{t("join_a_game")}</h2>
            <CodeBox onGo={(c) => nav(`/join/${c}`)} />
          </div>
          <div className="hh-panel p-5 sm:p-6 hh-spine" style={{ borderLeftColor: "var(--hh-pink)" }}>
            <p className="hh-meta mb-2">{t("for_comedians")}</p>
            <Btn variant="pink" size="xl" className="w-full" onClick={() => nav("/host")} data-testid="landing-host-cta">
              {t("host_a_night")} <ArrowRight size={22} />
            </Btn>
          </div>
        </section>
      </main>

      <section className="max-w-6xl mx-auto px-4 sm:px-8 pb-14">
        <h3 className="hh-meta mb-4">{t("how_title")}</h3>
        <div className="grid sm:grid-cols-3 gap-4">
          {steps.map((s, i) => (
            <motion.div key={s.n} initial={{ y: 12, opacity: 0 }} whileInView={{ y: 0, opacity: 1 }} viewport={{ once: true }} transition={{ duration: 0.2, delay: i * 0.06 }} className="hh-ticket p-5">
              <div className="flex items-start justify-between">
                <span className="text-4xl font-extrabold neon-yellow">{s.n}</span>
                <span className="text-4xl" aria-hidden="true">{s.emoji}</span>
              </div>
              <h4 className="mt-3 text-xl font-extrabold">{s.title}</h4>
              <p className="mt-1 text-[var(--hh-muted)]">{s.d}</p>
            </motion.div>
          ))}
        </div>
      </section>
      <Marquee items={[t("house_rules"), t("secondary")]} testid="landing-ticker" />
    </div>
  );
}
