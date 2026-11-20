import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import confetti from "canvas-confetti";
import { toast } from "sonner";
import { Lock, Flame, Trophy, Pause } from "lucide-react";
import { useLang } from "@/lib/lang";
import { useCountdown, useRoomState, useRotating, useTitle } from "@/hooks/useRoomState";
import { ANSWER, LangToggle, LoadingStage, ReconnectBadge, Shape, TimerBar, fmtSec, reducedMotion } from "@/components/hh/kit";
import { deviceId, errCode, normCode, postRetry } from "@/lib/api";
import { LINES } from "@/i18n";
import WrongCode from "@/pages/WrongCode";
import { PollPhone } from "@/components/hh/Polls";

function seedOf(s) {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function Screen({ bg = "var(--hh-bg)", color = "var(--hh-text)", children, testid }) {
  return (
    <motion.div key={testid} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}
      className="flex-1 flex flex-col items-center justify-center text-center px-6 py-8" style={{ background: bg, color }} data-testid={testid}>
      {children}
    </motion.div>
  );
}

export default function Play() {
  const { code: raw } = useParams();
  const code = normCode(raw);
  const nav = useNavigate();
  const { t, pick, lang } = useLang();
  const dev = useMemo(() => deviceId(), []);
  const { state, status, reconnecting, refresh, serverNow } = useRoomState(code, "player", { device: dev });
  const cd = useCountdown(state, serverNow);
  const [pending, setPending] = useState(null); // {qid, option}
  const lastQ = useRef(null);
  const lastReveal = useRef(null);
  const waitIdx = useRotating(LINES.waiting.length, 6000);
  useTitle(state && state.me ? state.me.name : t("join_title"));

  const me = state && state.me;
  const q = state && state.question;
  const phase = state && state.phase;

  useEffect(() => {
    if (state && !state.me && status === "ok") nav(`/join/${code}`, { replace: true });
  }, [state, status, nav, code]);

  // vibrate when a new question opens
  useEffect(() => {
    if (phase === "question_open" && q && lastQ.current !== q.id) {
      lastQ.current = q.id;
      setPending(null);
      if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
    }
  }, [phase, q]);

  useEffect(() => {
    if (phase === "reveal" && state.my_result && state.my_result.correct && q && lastReveal.current !== q.id) {
      lastReveal.current = q.id;
      if (!reducedMotion()) confetti({ particleCount: 90, spread: 70, origin: { y: 0.7 }, colors: ["#A3E635", "#FFE14D", "#FF2E88", "#22D3EE"], disableForReducedMotion: true });
    }
  }, [phase, state, q]);

  if (code.length !== 4 || status === "notfound") return <WrongCode />;
  if (!state || !me) return <LoadingStage />;

  const answer = async (i) => {
    if (pending || (state.my_answer && state.my_answer.option_index != null)) return;
    if (navigator.vibrate) navigator.vibrate(30);
    setPending({ qid: q.id, option: i });
    try {
      await postRetry(`/rooms/${code}/answer`, { device_id: dev, question_id: q.id, option_index: i });
      refresh();
    } catch (e) {
      const c = errCode(e);
      setPending(null);
      toast.error(c === "answers_closed" ? t("too_late") : c === "joined_late" ? t("joined_late") : t("error_generic"));
      refresh();
    }
  };

  const myOpt = state.my_answer ? state.my_answer.option_index : pending && q && pending.qid === q.id ? pending.option : null;
  const lineSeed = seedOf((q && q.id) || phase) + me.number;

  let body;
  if (me.hidden) {
    body = <Screen testid="play-hidden"><p className="text-xl font-semibold text-[var(--hh-muted)]">{t("hidden_note")}</p></Screen>;
  } else if (state.poll && phase.startsWith("poll_")) {
    body = <PollPhone key={state.poll.id} s={state} cd={cd} code={code} device={dev} refresh={refresh} />;
  } else if (phase === "lobby" || phase === "cold_open") {
    body = (
      <Screen testid="play-lobby">
        <motion.div initial={{ scale: 0.8, rotate: -8 }} animate={{ scale: 1, rotate: -3 }} transition={{ type: "spring", stiffness: 260, damping: 14 }}
          className="w-36 h-36 flex items-center justify-center text-7xl border-2 border-black" style={{ background: me.color, boxShadow: "6px 6px 0 #000" }}>
          {me.emoji}
        </motion.div>
        <h1 className="mt-8 text-5xl font-extrabold neon-lime" data-testid="play-youre-in">{t("youre_in")}</h1>
        <p className="mt-2 text-2xl font-extrabold" data-testid="play-team-name">{me.name}</p>
        <p className="mt-6 hh-meta">{t("waiting_host")}</p>
        <AnimatePresence mode="wait">
          <motion.p key={waitIdx} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}
            className="mt-3 text-lg max-w-xs text-[var(--hh-muted)]" data-testid="play-waiting-line">
            {LINES.waiting[waitIdx][lang]}
          </motion.p>
        </AnimatePresence>
        {me.name_status !== "shown" && (
          <p className="mt-6 text-sm p-3 border-2 border-[var(--hh-yellow)] text-[var(--hh-yellow)] max-w-xs" data-testid="play-name-pending">{t("name_pending_note", { n: me.number })}</p>
        )}
      </Screen>
    );
  } else if (phase === "round_intro") {
    body = (
      <Screen testid="play-round-intro">
        <p className="hh-meta">{t("round_starting")}</p>
        <h1 className="mt-3 text-5xl font-extrabold neon-yellow">{state.round ? t("round_n", { n: state.round.index + 1 }) : t("get_ready")}</h1>
        {state.round && <p className="mt-3 text-2xl font-extrabold">{pick({ en: state.round.name_en, vi: state.round.name_vi })}</p>}
        <p className="mt-8 text-lg text-[var(--hh-muted)]">{t("look_up")}</p>
      </Screen>
    );
  } else if (phase === "question_open" && q) {
    if (!me.eligible) {
      body = <Screen testid="play-joined-late"><p className="text-2xl font-extrabold max-w-xs">{t("joined_late")}</p></Screen>;
    } else if (myOpt != null) {
      const a = ANSWER[myOpt];
      body = (
        <Screen testid="play-locked-in" bg="var(--hh-surface)" color="var(--hh-text)">
          <motion.div initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 15 }}
            className="w-28 h-28 flex items-center justify-center border-2 border-black bg-black/10"><Shape shape={a.shape} size={72} /></motion.div>
          <h1 className="mt-6 text-5xl font-extrabold text-white" style={{ textShadow: "3px 3px 0 #000" }}>{t("locked_in_title")}</h1>
          <p className="mt-3 text-2xl font-extrabold text-white" style={{ textShadow: "2px 2px 0 #000" }} data-testid="play-my-choice">{pick(q.options[myOpt])}</p>
          <p className="mt-6 text-lg font-semibold max-w-xs bg-black text-white px-3 py-2">{LINES.locked_in[lineSeed % LINES.locked_in.length][lang]}</p>
        </Screen>
      );
    } else {
      body = (
        <div className="flex-1 flex flex-col" data-testid="play-answering">
          <div className="px-3 pt-3 pb-2 bg-[var(--hh-surface)] border-b-2 border-black">
            <div className="flex items-center justify-between mb-2">
              <span className="hh-meta">{t("q_label", { a: state.question_number, b: state.question_total })}</span>
              <span className="text-2xl font-extrabold tabular-nums" data-testid="play-countdown">{cd.frozen ? <Pause size={22} /> : fmtSec(cd.remaining)}</span>
            </div>
            <TimerBar fraction={cd.fraction} frozen={cd.frozen} testid="play-countdown-bar" />
            <p className="mt-2 text-base font-semibold leading-snug line-clamp-3" data-testid="play-question-text">{q[`text_${lang}`]}</p>
          </div>
          <div className="hh-phone-choices flex-1 grid grid-cols-1 gap-3 p-4">
            {q.options.map((o, i) => {
              const a = ANSWER[i];
              return (
                <motion.button key={i} whileTap={{ scale: 0.97 }} onClick={() => answer(i)} data-testid={`play-answer-${a.key}`}
                  className="hh-phone-choice relative flex items-center gap-4 p-4 border-2 text-left min-h-[82px]"
                  style={{ background: "var(--hh-surface)", borderColor:"var(--hh-line)", boxShadow: "4px 4px 0 #000" }} aria-label={pick(o)}>
                  <Shape shape={a.shape} size={34} />
                  <span className="text-white font-semibold text-lg leading-snug break-words">{o[lang] || o.en}</span>
                </motion.button>
              );
            })}
          </div>
        </div>
      );
    }
  } else if (phase === "question_locked") {
    body = (
      <Screen testid="play-answers-locked">
        <div className="w-24 h-24 flex items-center justify-center border-2 border-black bg-[var(--hh-yellow)] text-black" style={{ boxShadow: "5px 5px 0 #000" }}><Lock size={48} /></div>
        <h1 className="mt-8 text-3xl font-extrabold max-w-xs leading-tight">{t("answers_locked_player")}</h1>
        {myOpt != null && q && (
          <p className="mt-6 flex items-center gap-2 text-lg font-semibold"><Shape shape={ANSWER[myOpt].shape} fill={ANSWER[myOpt].color} size={22} /> {pick(q.options[myOpt])}</p>
        )}
      </Screen>
    );
  } else if (phase === "reveal" && state.my_result) {
    const r = state.my_result;
    const ok = r.correct;
    const kind = ok ? "correct" : r.answered ? "wrong" : "no_answer";
    const lines = LINES[kind];
    const correctOpt = q && state.reveal ? q.options[state.reveal.correct_index] : null;
    body = (
      <Screen testid={`play-result-${kind}`} bg={ok ? "#A3E635" : r.answered ? "#F43F5E" : "#1F1F2B"} color={ok || r.answered ? "#000" : "var(--hh-text)"}>
        <motion.h1 initial={{ scale: 0.5, rotate: -6 }} animate={{ scale: 1, rotate: -3 }} transition={{ type: "spring", stiffness: 280, damping: 12 }}
          className="text-6xl font-extrabold">{ok ? t("correct_title") : r.answered ? t("wrong_title") : t("no_answer_title")}</motion.h1>
        <p className="mt-6 text-5xl font-extrabold tabular-nums" data-testid="play-result-points">{t("points_earned", { n: r.points })}</p>
        <div className="mt-5 flex gap-2 flex-wrap justify-center">
          {r.streak >= 2 && <span className="hh-chip" style={{ background: "#000", color: "#FFE14D" }}><Flame size={14} /> {t("streak_n", { n: r.streak })}</span>}
          {r.rank && <span className="hh-chip" style={{ background: "#000", color: "#fff" }} data-testid="play-rank">{t("rank_n", { n: r.rank })}</span>}
        </div>
        {!ok && correctOpt && (
          <p className="mt-6 text-base font-semibold"><span className="opacity-75">{t("the_answer_was")}:</span> <b>{pick(correctOpt)}</b></p>
        )}
        <p className="mt-6 text-lg font-semibold max-w-xs px-3 py-2 bg-black text-white" data-testid="play-result-line">{lines[lineSeed % lines.length][lang]}</p>
      </Screen>
    );
  } else if (phase === "scoreboard" || phase === "ended" || phase === "reveal") {
    const ended = phase === "ended";
    body = (
      <Screen testid={ended ? "play-ended" : "play-scoreboard"}>
        <p className="hh-meta">{ended ? t("final_rank") : t("your_rank")}</p>
        <div className="mt-3 text-[7rem] leading-none font-extrabold neon-yellow tabular-nums" data-testid="play-rank">#{me.rank || "-"}</div>
        <div className="mt-6 hh-panel-raised px-6 py-4 min-w-[240px]">
          <p className="hh-meta">{t("score")}</p>
          <p className="text-4xl font-extrabold tabular-nums" data-testid="play-score">{me.total.toLocaleString()}</p>
          <p className="text-sm text-[var(--hh-muted)] mt-1">{me.brain_points} {t("brain")} · {me.laugh_points} {t("laugh")}</p>
        </div>
        {ended && <p className="mt-8 text-xl font-extrabold flex items-center gap-2"><Trophy size={22} /> {t("thanks_venue")}</p>}
      </Screen>
    );
  } else {
    body = <Screen testid="play-waiting"><p className="text-lg text-[var(--hh-muted)]">{LINES.waiting[waitIdx][lang]}</p></Screen>;
  }

  return (
    <div className="hh-bg flex flex-col" style={{ minHeight: "100dvh" }}>
      <ReconnectBadge show={reconnecting} />
      <header className="flex items-center justify-between gap-2 px-3 py-2 border-b-2 border-black bg-[var(--hh-surface)]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-10 h-10 shrink-0 flex items-center justify-center text-xl border-2 border-black" style={{ background: me.color }} aria-hidden="true">{me.emoji}</span>
          <div className="min-w-0">
            <p className="font-extrabold truncate leading-tight" data-testid="play-header-name">{me.name}</p>
            <p className="text-xs text-[var(--hh-muted)] tabular-nums" data-testid="play-header-score">{me.total.toLocaleString()} {t("pts")}{me.rank && phase !== "lobby" && phase !== "cold_open" ? ` · #${me.rank}` : ""}</p>
          </div>
        </div>
        <LangToggle />
      </header>
      {state.frozen && (
        <div className="bg-[var(--hh-cyan)] text-black text-center font-extrabold py-2 border-b-2 border-black flex items-center justify-center gap-2" data-testid="play-paused">
          <Pause size={16} /> {t("paused")}
        </div>
      )}
      {React.cloneElement(body, { key: state.poll?.id || (body.props && body.props.testid) || "body" })}
    </div>
  );
}
