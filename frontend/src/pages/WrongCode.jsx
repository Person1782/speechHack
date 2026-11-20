import React from "react";
import { useNavigate } from "react-router-dom";
import { useLang } from "@/lib/lang";
import { useTitle } from "@/hooks/useRoomState";
import { Btn, LangToggle, Wordmark } from "@/components/hh/kit";
import { CodeBox } from "@/pages/Landing";

export default function WrongCode() {
  const { t } = useLang();
  const nav = useNavigate();
  useTitle(t("wrong_code_title"));
  return (
    <div className="hh-bg">
      <header className="flex items-center justify-between px-4 py-4 border-b-2 border-black bg-[var(--hh-surface)]">
        <button onClick={() => nav("/")} aria-label="home" data-testid="wrong-code-home-logo"><Wordmark size="sm" /></button>
        <LangToggle />
      </header>
      <main className="max-w-xl mx-auto px-5 py-14">
        <div className="hh-tube-cyan inline-block px-6 py-3 mb-8 bg-black">
          <span className="text-6xl sm:text-7xl font-extrabold neon-cyan tracking-tight" style={{ animation: "hh-flicker 4s infinite" }}>NO ROOM</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold leading-tight" data-testid="wrong-code-message">{t("wrong_code_title")}</h1>
        <p className="mt-3 text-[var(--hh-muted)]">{t("wrong_code_sub")}</p>
        <div className="hh-ticket p-5 mt-8">
          <p className="hh-meta mb-3">{t("try_again")}</p>
          <CodeBox onGo={(c) => nav(`/join/${c}`)} testid="wrong-code-retry" />
        </div>
        <Btn variant="ghost" className="mt-6" onClick={() => nav("/")} data-testid="wrong-code-home">{t("back_home")}</Btn>
      </main>
    </div>
  );
}
