import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import { QRCodeSVG } from "qrcode.react";
import confetti from "canvas-confetti";
import { Lock, Maximize, Pause, TrendingUp, TrendingDown, Zap, Users } from "lucide-react";
import { useLang } from "@/lib/lang";
import { useCountdown, useRoomState, useRotating, useTitle, useWakeLock } from "@/hooks/useRoomState";
import { ANSWER, Btn, LangToggle, LoadingStage, Marquee, ReconnectBadge, Shape, TimerBar, Wordmark, fmtSec, reducedMotion, teamLabel } from "@/components/hh/kit";
import { normCode } from "@/lib/api";
import { LINES } from "@/i18n";
import WrongCode from "@/pages/WrongCode";
import { PollScreen } from "@/components/hh/Polls";
import { ScreenAudio } from "@/components/hh/ScreenAudio";

const QSIZE = "clamp(34px, 3.4vw, 80px)";
const OSIZE = "clamp(24px, 2vw, 46px)";

function Bi({ en, vi, big, small, className = "", bigClass = "", smallClass = "" }) {
  const { lang, other } = useLang();
  const src = { en, vi };
  return (
    <div className={className}>
      <div className={`font-extrabold leading-[1.05] ${bigClass}`} style={{ fontSize: big }}>{src[lang]}</div>
      {src[other] && src[other] !== src[lang] && (
        <div className={`font-semibold text-[var(--hh-muted)] mt-2 leading-tight ${smallClass}`} style={{ fontSize: small }}>{src[other]}</div>
      )}
    </div>
  );
}

function BiT({ k, vars, big, small, className, bigClass }) {
  const { tIn } = useLang();
  return <Bi en={tIn("en", k, vars)} vi={tIn("vi", k, vars)} big={big} small={small} className={className} bigClass={bigClass} />;
}

function TeamTile({ team, t, i }) {
  return (
    <motion.div layout initial={{ y: 30, opacity: 0, rotate: -4 }} animate={{ y: 0, opacity: 1, rotate: 0 }} transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.03 }}
      className="flex items-center gap-3 p-3 border-2 border-black bg-[var(--hh-raised)] min-w-0" style={{ boxShadow: "4px 4px 0 #000", borderLeft: `10px solid ${team.color}` }}
      data-testid={`screen-team-${team.number}`}>
      <span className="text-4xl" aria-hidden="true">{team.emoji}</span>
      <span className="font-extrabold text-2xl truncate">{teamLabel(team, t)}</span>
    </motion.div>
  );
}

function Lobby({ s }) {
  const { t, tIn, lang, other } = useLang();
  const url = `${window.location.origin}/join/${s.code}`;
  const idle = useRotating(LINES.idle.length, 6000);
  const ticker = s.fun_facts.map((f) => `${f.emoji} ${f.text}`);
  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex-1 grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)] gap-12 px-14 py-8 min-h-0 overflow-hidden">
        <div className="flex flex-col items-start justify-center gap-5 min-h-0">
          <div className="hh-tube p-4 bg-white" data-testid="screen-qr">
            <QRCodeSVG value={url} size={380} level="M" bgColor="#FFFFFF" fgColor="#0B0B12" style={{ width: "min(380px, 40vh)", height: "min(380px, 40vh)", display: "block" }} />
          </div>
          <BiT k="scan_to_join" big="56px" small="30px" />
          <p className="text-2xl text-[var(--hh-muted)]">{t("or_visit")} <b className="text-[var(--hh-text)]">{url.replace(/^https?:\/\//, "")}</b></p>
        </div>
        <div className="flex flex-col min-h-0">
          <p className="hh-meta" style={{ fontSize: 20 }}>{t("room_code")} · {tIn(other, "room_code")}</p>
          <div className="font-extrabold neon-yellow leading-none tracking-[0.12em]" style={{ fontSize: 120 }} data-testid="screen-room-code">{s.code}</div>
          <div className="mt-6 flex items-center gap-4">
            <span className="hh-chip text-xl py-2 px-4" style={{ background: "var(--hh-pink)", color: "#000", fontSize: 22 }} data-testid="screen-team-count"><Users size={22} /> {t("teams_in", { n: s.team_count })}</span>
          </div>
          <div className="mt-6 flex-1 min-h-0 overflow-hidden">
            {s.teams.length === 0 ? (
              <div className="h-full flex items-center"><BiT k="waiting_for_teams" big="48px" small="28px" bigClass="text-[var(--hh-muted)]" /></div>
            ) : (
              <LayoutGroup>
                <div className="grid grid-cols-3 gap-4 content-start">
                  {s.teams.slice(0, 30).map((tm, i) => <TeamTile key={tm.id} team={tm} t={t} i={i} />)}
                </div>
              </LayoutGroup>
            )}
          </div>
        </div>
      </div>
      <div className="px-14 pb-4">
        <AnimatePresence mode="wait">
          <motion.p key={idle} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}
            className="text-3xl font-extrabold" data-testid="screen-idle-line">
            {LINES.idle[idle][lang]} <span className="text-[var(--hh-muted)] font-semibold text-2xl">/ {LINES.idle[idle][other]}</span>
          </motion.p>
        </AnimatePresence>
      </div>
      {ticker.length > 0 && <div style={{ fontSize: 26 }}><Marquee items={ticker} testid="screen-ticker" /></div>}
    </div>
  );
}

function OptionTile({ o, i, dim, glow, compact }) {
  const { lang, other } = useLang();
  const a = ANSWER[i];
  return (
    <div className={`relative flex items-center gap-5 px-6 border-2 border-black ${glow ? "hh-pulse-lime" : ""}`}
      style={{ background: "var(--hh-surface)", borderColor:glow?"var(--hh-lime)":"var(--hh-line)", boxShadow: "6px 6px 0 #000", opacity: dim ? 0.3 : 1, minHeight: compact ? 90 : 130, outline: glow ? "6px solid #A3E635" : "none" }}
      data-testid={`screen-option-${a.key}`}>
      <Shape shape={a.shape} size={compact ? 40 : 56} />
      <div className="min-w-0">
        <div className="font-extrabold text-white leading-tight" style={{ fontSize: compact ? "clamp(20px,1.6vw,36px)" : OSIZE, textShadow: "none" }}>{o[lang]}</div>
        {o[other] !== o[lang] && <div className="font-semibold text-white/85 leading-tight mt-1" style={{ fontSize: compact ? 18 : 24 }}>{o[other]}</div>}
      </div>
    </div>
  );
}

function QuestionHeader({ s }) {
  const { t, pick } = useLang();
  return (
    <div className="flex items-center gap-4">
      {s.round && <span className="hh-chip text-lg py-1.5 px-3" style={{ background: "var(--hh-yellow)", color: "#000", fontSize: 18 }}>{pick({ en: s.round.name_en, vi: s.round.name_vi })}</span>}
      <span className="hh-meta" style={{ fontSize: 20 }} data-testid="screen-q-number">{t("q_of", { a: s.question_number, b: s.question_total })}</span>
    </div>
  );
}

function QuestionOpen({ s, cd }) {
  const { t } = useLang();
  const q = s.question;
  return (
    <div className="flex-1 flex flex-col px-14 py-8 gap-7 min-h-0" data-testid="screen-question">
      <QuestionHeader s={s} />
      <div className="flex items-start gap-10">
        <Bi en={q.text_en} vi={q.text_vi} big={QSIZE} small="clamp(20px,1.7vw,38px)" className="flex-1" />
        {q.media_hint && <div className="shrink-0 text-[120px] leading-none hh-panel-raised px-6 py-4" aria-hidden="true" data-testid="screen-emoji-scene">{q.media_hint}</div>}
      </div>
      <div className="grid grid-cols-2 gap-5 flex-1 content-end" data-testid="screen-options">
        {q.options.map((o, i) => <OptionTile key={i} o={o} i={i} />)}
      </div>
      <div className="flex items-center gap-6">
        <div className="text-7xl font-extrabold tabular-nums w-[140px]" data-testid="screen-countdown">{cd.frozen ? <Pause size={64} /> : fmtSec(cd.remaining)}</div>
        <TimerBar fraction={cd.fraction} frozen={cd.frozen} className="flex-1 !h-7" testid="screen-countdown-bar" />
        <span className="hh-chip py-2 px-4" style={{ fontSize: 22 }} data-testid="screen-answered-count">{t("answered_live", { a: s.answered_count, b: s.eligible_count })}</span>
      </div>
    </div>
  );
}

function Locked({ s }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-8 text-center" data-testid="screen-locked">
      <motion.div initial={{ scale: 1.6, rotate: -15, opacity: 0 }} animate={{ scale: 1, rotate: -4, opacity: 1 }} transition={{ type: "spring", stiffness: 260, damping: 14 }}
        className="w-[220px] h-[220px] flex items-center justify-center border-4 border-black bg-[var(--hh-yellow)] text-black" style={{ boxShadow: "10px 10px 0 #000" }}>
        <Lock size={130} strokeWidth={2.5} />
      </motion.div>
      <BiT k="answers_locked" big="96px" small="44px" />
      <BiT k="host_reading" big="36px" small="26px" bigClass="text-[var(--hh-muted)]" />
    </div>
  );
}

function Reveal({ s }) {
  const { t, other, pick } = useLang();
  const q = s.question;
  const r = s.reveal;
  const max = Math.max(1, ...r.counts);
  const fired = useRef(false);
  useEffect(() => {
    if (!fired.current && !reducedMotion() && r.counts[r.correct_index] > 0) {
      fired.current = true;
      setTimeout(() => confetti({ particleCount: 160, spread: 100, origin: { y: 0.6 }, colors: ["#A3E635", "#FFE14D", "#FF2E88", "#22D3EE"] }), 1300);
    }
  }, [r]);
  const fastName = r.fastest ? teamLabel(r.fastest.team, t) : null;
  const pw = r.popular_wrong;
  return (
    <div className="flex-1 flex flex-col px-14 py-8 gap-6 min-h-0" data-testid="screen-reveal">
      <QuestionHeader s={s} />
      <Bi en={q.text_en} vi={q.text_vi} big="clamp(28px,2.4vw,52px)" small="24px" />
      <div className="flex-1 grid grid-cols-4 gap-6 min-h-[260px]">
        {q.options.map((o, i) => {
          const a = ANSWER[i];
          const correct = i === r.correct_index;
          return (
            <div key={i} className="flex flex-col justify-end min-h-0" style={{ opacity: correct ? 1 : 0.45 }} data-testid={`screen-bar-${a.key}`}>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 + i * 0.25 }} className="text-6xl font-extrabold text-center mb-2 tabular-nums">{r.counts[i]}</motion.div>
              <div className="flex-1 flex items-end">
                <motion.div className={`w-full border-2 border-black ${correct ? "hh-pulse-lime" : ""}`}
                  initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ duration: 0.25, delay: 0.2 + i * 0.25, ease: [0.2, 0.8, 0.2, 1] }}
                  style={{ originY: 1, height: `${Math.max(4, (r.counts[i] / max) * 100)}%`, background: a.color, boxShadow: "6px 6px 0 #000" }} />
              </div>
              <div className={`mt-4 flex items-center gap-3 p-3 border-2 border-black ${correct ? "bg-[var(--hh-lime)] text-black" : "bg-[var(--hh-raised)]"}`} style={{ minHeight: 84 }}>
                <Shape shape={a.shape} fill={a.color} size={34} />
                <span className="font-extrabold leading-tight" style={{ fontSize: "clamp(18px,1.5vw,32px)" }}>{pick(o)}</span>
              </div>
            </div>
          );
        })}
      </div>
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 1.3, duration: 0.25 }} className="grid grid-cols-[1fr_1fr] gap-5">
        <div className="hh-panel-raised p-4 flex items-center gap-3" style={{ fontSize: 26 }} data-testid="screen-fastest">
          <Zap size={30} className="text-[var(--hh-yellow)] shrink-0" />
          <span className="font-extrabold">{fastName ? t("fastest_correct", { team: fastName, s: (r.fastest.ms / 1000).toFixed(1) }) : t("nobody_correct")}</span>
        </div>
        <div className="hh-panel-raised p-4 flex items-center gap-3" style={{ fontSize: 26 }} data-testid="screen-popular-wrong">
          {pw ? <span className="font-extrabold">{t(pw.count === 1 ? "popular_wrong_one" : "popular_wrong", { opt: pick(q.options[pw.index]), n: pw.count })}</span> : <span className="font-extrabold neon-lime">{t("correct_title")}</span>}
        </div>
      </motion.div>
      {(r.explanation_en || r.explanation_vi) && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.6 }} className="hh-ticket p-4" data-testid="screen-explanation">
          <p className="font-semibold" style={{ fontSize: 26 }}>{pick({ en: r.explanation_en, vi: r.explanation_vi })}</p>
          <p className="text-[var(--hh-muted)] mt-1" style={{ fontSize: 20 }}>{pick({ en: r.explanation_en, vi: r.explanation_vi }, other)}</p>
        </motion.div>
      )}
    </div>
  );
}

function Scoreboard({ s, final, hideTitle = false }) {
  const { t, tIn, other } = useLang();
  const sb = s.scoreboard || {};
  const rows = (s.leaderboard || []).slice(0, final ? 10 : 5);
  const hasPrev = rows.some((r) => r.prev_rank);
  const [settled, setSettled] = useState(!hasPrev);
  useEffect(() => {
    if (!hasPrev) return undefined;
    const id = setTimeout(() => setSettled(true), 900);
    return () => clearTimeout(id);
  }, [hasPrev]);
  const ordered = settled ? rows : [...rows].sort((a, b) => (a.prev_rank || 99) - (b.prev_rank || 99));
  useEffect(() => {
    if (final && !reducedMotion()) confetti({ particleCount: 200, spread: 120, origin: { y: 0.5 } });
  }, [final]);
  const big = final || s.phase === "ended";
  return (
    <div className="flex-1 flex flex-col px-14 py-8 gap-5 min-h-0" data-testid="screen-scoreboard">
      <div className={`flex items-end justify-between ${hideTitle ? "hidden" : ""}`}>
        <div>
          <h1 className={`font-extrabold leading-none ${big ? "neon-yellow" : "neon-pink"}`} style={{ fontSize: 80 }}>{big ? t("final_results") : t("scoreboard")}</h1>
          <p className="text-[var(--hh-muted)] font-semibold mt-2" style={{ fontSize: 30 }}>{big ? tIn(other, "final_results") : tIn(other, "scoreboard")}</p>
        </div>
      </div>
      <LayoutGroup>
        <div className={`flex flex-col ${big ? "gap-2" : "gap-3"}`}>
          {ordered.map((r) => {
            const climber = sb.climber_id === r.id;
            const faller = sb.faller_id === r.id;
            const shownRank = settled ? r.rank : r.prev_rank || r.rank;
            return (
              <motion.div layout key={r.id} transition={{ type: "spring", stiffness: 300, damping: 30 }}
                className="flex items-center gap-5 border-2 border-black bg-[var(--hh-raised)] pr-6" style={{ boxShadow: "5px 5px 0 #000", minHeight: big ? 70 : 104 }}
                data-testid={`screen-row-${r.rank}`}>
                <div className="self-stretch flex items-center justify-center font-extrabold text-black tabular-nums" style={{ width: big ? 80 : 110, background: shownRank === 1 ? "var(--hh-yellow)" : r.color, fontSize: big ? 36 : 54 }}>{shownRank}</div>
                <span style={{ fontSize: big ? 40 : 56 }} aria-hidden="true">{r.emoji}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-extrabold truncate" style={{ fontSize: big ? 32 : 44 }}>{teamLabel(r, t)}</div>
                  <div className="text-[var(--hh-muted)] font-semibold" style={{ fontSize: big ? 18 : 22 }}>{r.brain_points} {t("brain")} · {r.laugh_points} {t("laugh")}</div>
                </div>
                {climber && settled && <span className="hh-chip" style={{ background: "var(--hh-lime)", color: "#000", fontSize: 18 }} data-testid="screen-climber"><TrendingUp size={18} /> {t("biggest_climber")}</span>}
                {faller && settled && <span className="hh-chip" style={{ background: "var(--hh-red)", color: "#000", fontSize: 18 }} data-testid="screen-faller"><TrendingDown size={18} /> {t("biggest_faller")}</span>}
                <div className="font-extrabold tabular-nums" style={{ fontSize: big ? 40 : 60 }}>{r.total.toLocaleString()}</div>
              </motion.div>
            );
          })}
        </div>
      </LayoutGroup>
    </div>
  );
}

export default function BigScreen() {
  const { code: raw } = useParams();
  const code = normCode(raw);
  const { t, setLang } = useLang();
  const { state: s, status, reconnecting, serverNow } = useRoomState(code, "screen", { pauseWhenHidden: false });
  const cd = useCountdown(s, serverNow);
  const langInit = useRef(false);
  useWakeLock(true);
  useTitle(s ? `${t("app_name")} · ${s.code}` : t("app_name"));

  useEffect(() => {
    if (s && !langInit.current) {
      langInit.current = true;
      if (!sessionStorage.getItem(`hh_screen_lang_${code}`)) setLang(s.default_lang);
    }
  }, [s, code, setLang]);

  const view = useMemo(() => {
    if (!s) return null;
    if (s.poll && s.phase.startsWith("poll_")) return <PollScreen s={s} cd={cd} />;
    switch (s.phase) {
      case "lobby": return <Lobby s={s} />;
      case "cold_open":
        return (
          <div className="flex-1 flex flex-col justify-center px-20 gap-6" data-testid="screen-cold-open">
            <BiT k="tonight_host" big="40px" small="26px" bigClass="text-[var(--hh-muted)]" />
            <motion.h1 initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.25 }}
              className="font-extrabold neon-pink leading-none" style={{ fontSize: "clamp(80px, 9vw, 180px)" }} data-testid="screen-host-name">{s.host_name}</motion.h1>
            {s.venue_name && <BiT k="live_at" vars={{ v: s.venue_name }} big="44px" small="28px" />}
            <div className="mt-8"><BiT k="tagline" big="44px" small="28px" bigClass="neon-yellow" /></div>
          </div>
        );
      case "round_intro":
        return (
          <div className="flex-1 flex flex-col items-center justify-center gap-8 text-center" data-testid="screen-round-intro">
            <motion.div initial={{ scale: 2, rotate: -20, opacity: 0 }} animate={{ scale: 1, rotate: -4, opacity: 1 }} transition={{ type: "spring", stiffness: 200, damping: 12 }}
              className="hh-stamp neon-yellow" style={{ fontSize: 72, borderColor: "var(--hh-yellow)", borderWidth: 6 }}>
              {s.round ? t("round_n", { n: s.round.index + 1 }) : t("get_ready")}
            </motion.div>
            {s.round && <Bi en={s.round.name_en} vi={s.round.name_vi} big="130px" small="56px" />}
            {s.round && <BiT k="questions_n" vars={{ n: s.round.count }} big="36px" small="24px" bigClass="text-[var(--hh-muted)]" />}
          </div>
        );
      case "question_open": return s.question ? <QuestionOpen s={s} cd={cd} /> : null;
      case "question_locked": return <Locked s={s} />;
      case "reveal": return s.reveal ? <Reveal key={s.question && s.question.id} s={s} /> : null;
      case "scoreboard": return <Scoreboard key={`sb-${s.version}-${s.question_number}`} s={s} final={!!(s.scoreboard && s.scoreboard.final)} />;
      case "ended":
        return (
          <div className="flex-1 flex flex-col min-h-0" data-testid="screen-ended">
            <div className="px-14 pt-8"><BiT k="thats_a_wrap" big="72px" small="34px" bigClass="neon-lime" /></div>
            <Scoreboard s={s} final hideTitle />
          </div>
        );
      default: return null;
    }
  }, [s, cd, t]);

  if (code.length !== 4 || status === "notfound") return <WrongCode />;
  if (!s) return <LoadingStage />;

  const fullscreen = () => {
    const el = document.documentElement;
    if (document.fullscreenElement) document.exitFullscreen && document.exitFullscreen();
    else if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
  };

  return (
    <div className="hh-bg hh-tv flex flex-col overflow-hidden" style={{ height: "100dvh" }} data-testid="big-screen">
      <ReconnectBadge show={reconnecting} />
      <ScreenAudio s={s} cd={cd} />
      <header className="hh-tv-header" data-testid="tv-header">
        <Wordmark size="tv" />
        <div className="hh-tv-join min-w-0" data-testid="screen-header-code"><span className="hidden lg:inline truncate text-sm text-[var(--hh-muted)]">{window.location.host}/join/{s.code}</span><strong className="text-xl tracking-widest text-[var(--hh-cyan)]">{s.code}</strong></div>
        <div className="flex items-center gap-2 justify-end"><LangToggle onChange={() => sessionStorage.setItem(`hh_screen_lang_${code}`, "1")} /><Btn variant="ghost" size="sm" onClick={fullscreen} data-testid="screen-fullscreen" aria-label={t("fullscreen")}><Maximize size={18} /><span className="hidden xl:inline">{t("fullscreen")}</span></Btn></div>
      </header>
      <AnimatePresence mode="wait">
        <motion.div key={s.phase} className="flex-1 flex flex-col min-h-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
          {view}
        </motion.div>
      </AnimatePresence>
      {s.frozen && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-[#0B0B12]/90" data-testid="screen-paused">
          <div className="hh-tube-cyan px-12 py-6 bg-black flex items-center gap-6">
            <Pause size={96} className="text-[var(--hh-cyan)]" />
            <span className="font-extrabold neon-cyan" style={{ fontSize: 120 }}>{t("paused")}</span>
          </div>
          <BiT k="paused_sub" big="36px" small="24px" />
        </div>
      )}
    </div>
  );
}
