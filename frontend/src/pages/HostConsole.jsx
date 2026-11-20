import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import {
  Check, ChevronRight, Copy, EyeOff, Eye, Flame, Lock, Mic, MonitorPlay, MoreHorizontal, Pause, Play as PlayIcon,
  Radar, RotateCcw, SkipBack, SkipForward, Snowflake, Square, Timer, Users, Zap,
} from "lucide-react";
import { useLang, tr } from "@/lib/lang";
import { useCountdown, useRoomState, useTitle, useWakeLock } from "@/hooks/useRoomState";
import { ANSWER, Btn, LangToggle, LoadingStage, ReconnectBadge, Shape, TimerBar, fmtSec } from "@/components/hh/kit";
import { getHostKey, normCode, postRetry } from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import WrongCode from "@/pages/WrongCode";
import { QuestionManager, t2Error } from "@/components/hh/QuestionManager";
import { PollHost, Soundboard } from "@/components/hh/Polls";

const ROAST_COLORS = { off: "#6B6B7E", mild: "#FFE14D", spicy: "#F43F5E" };
const VERDICT_COLORS = { allow: "#A3E635", flag: "#FFE14D", block: "#F43F5E" };

function Confirm({ open, onOpenChange, text, onYes, testid }) {
  const { t } = useLang();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="bg-[var(--hh-raised)] border-2 border-black text-[var(--hh-text)]" style={{ boxShadow: "6px 6px 0 #000" }} data-testid={testid}>
        <AlertDialogHeader>
          <AlertDialogTitle className="text-2xl font-extrabold">{text}</AlertDialogTitle>
          <AlertDialogDescription className="text-[var(--hh-muted)]">{t("confirm_sub")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="gap-3">
          <AlertDialogCancel className="hh-btn hh-ghost m-0" data-testid={`${testid}-cancel`}>{t("cancel")}</AlertDialogCancel>
          <AlertDialogAction className="hh-btn hh-red m-0" onClick={onYes} data-testid={`${testid}-yes`}>{t("confirm")}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function Section({ title, right, children, className = "", testid }) {
  return (
    <section className={`hh-panel p-4 min-w-0 ${className}`} data-testid={testid}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-3 gap-2">
          <h2 className="hh-meta">{title}</h2>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

function OptionRow({ o, i, correct, lang }) {
  const a = ANSWER[i];
  return (
    <div className="flex items-center gap-2.5 p-2 border-2" style={{ borderColor: correct ? "#A3E635" : "var(--hh-line)", background: correct ? "rgba(163,230,53,.12)" : "transparent" }}
      data-testid={`host-option-${a.key}`}>
      <Shape shape={a.shape} fill={a.color} size={20} />
      <span className="flex-1 font-semibold">{o[lang] || o.en}</span>
      {correct && <span className="hh-chip" style={{ background: "#A3E635", color: "#000" }} data-testid="host-correct-marker"><Check size={12} /> {tr(lang, "right_tag")}</span>}
    </div>
  );
}

function Teleprompter({ s }) {
  const { t, lang, pick } = useLang();
  const h = s.host;
  const q = h.question;
  const phase = s.phase;
  if (phase === "lobby" || phase === "cold_open" || phase === "round_intro" || phase === "scoreboard") {
    const nq = h.next_question;
    return (
      <Section title={t("teleprompter")} testid="host-teleprompter">
        {phase === "lobby" && <p className="text-lg font-semibold">{t("lobby_tip")}</p>}
        {phase === "cold_open" && <p className="text-xl font-extrabold">{t("say_cold_open")}</p>}
        {phase === "scoreboard" && <p className="text-xl font-extrabold">{t("say_scoreboard")}</p>}
        {phase === "round_intro" && s.round && (
          <p className="text-2xl font-extrabold neon-yellow">{t("round_n", { n: s.round.index + 1 })}: {pick({ en: s.round.name_en, vi: s.round.name_vi })}</p>
        )}
        {nq && (
          <div className="mt-4 border-t-2 border-[var(--hh-line)] pt-3" data-testid="host-up-next">
            <p className="hh-meta mb-1">{t("up_next")}</p>
            <p className="font-semibold">{nq[`text_${lang}`]}</p>
            {nq.setup_line && <p className="mt-2 text-[var(--hh-yellow)] font-semibold">“{nq.setup_line}”</p>}
          </div>
        )}
      </Section>
    );
  }
  if (phase === "ended") {
    return <Section title={t("teleprompter")} testid="host-teleprompter"><p className="text-lg font-semibold">{t("ended_host")}</p></Section>;
  }
  if (!q) return null;
  const revealed = phase === "reveal";
  const locked = phase === "question_locked";
  return (
    <Section title={`${t("teleprompter")} · ${t("q_label", { a: s.question_number, b: s.question_total })}`} testid="host-teleprompter"
      right={s.round && <span className="hh-chip" style={{ background: "var(--hh-yellow)", color: "#000" }}>{pick({ en: s.round.name_en, vi: s.round.name_vi })}</span>}>
      {!revealed && q.setup_line && (
        <div className="mb-3 p-3 border-2 border-black bg-[var(--hh-pink)] text-black" data-testid="host-setup-line">
          <p className="text-[11px] font-extrabold uppercase tracking-[.14em]">{t("say_first")}</p>
          <p className="text-lg font-extrabold leading-snug">{q.setup_line}</p>
        </div>
      )}
      <p className="text-xl font-extrabold leading-snug" data-testid="host-question-text">{q[`text_${lang}`]}</p>
      <div className="mt-3 grid gap-1.5">
        {q.options.map((o, i) => <OptionRow key={i} o={o} i={i} correct={i === q.correct_index} lang={lang} />)}
      </div>
      {locked && q.notes && (
        <div className="mt-4 p-3 border-2 border-dashed border-[var(--hh-line)] text-[var(--hh-muted)]" data-testid="host-notes">
          <p className="hh-meta mb-2">{t("notes_label")}</p>
          {["opener", "follow_up", "backup"].map((k) => q.notes[k] && (
            <p key={k} className="mb-1.5"><b className="text-[var(--hh-text)]">{t(`note_${k}`)}:</b> {q.notes[k]}</p>
          ))}
        </div>
      )}
      {revealed ? (
        <div className="mt-4 p-3 border-2 border-black bg-[var(--hh-yellow)] text-black" data-testid="host-punchline">
          <p className="text-[11px] font-extrabold uppercase tracking-[.14em]">{t("punchline")}</p>
          <p className="text-lg font-extrabold leading-snug">{q.punchline}</p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-[var(--hh-muted)] flex items-center gap-2" data-testid="host-punchline-locked"><Lock size={14} /> {t("punchline_locked")}</p>
      )}
      {revealed && q.explanation_en && <p className="mt-3 text-sm text-[var(--hh-muted)]">{pick({ en: q.explanation_en, vi: q.explanation_vi })}</p>}
    </Section>
  );
}

function JoinCard({ s, onLoadDemo, busy }) {
  const { t } = useLang();
  const url = `${window.location.origin}/join/${s.code}`;
  return (
    <Section title={t("join_card_title")} testid="host-join-card">
      <div className="flex gap-4 items-center">
        <div className="bg-white p-2 border-2 border-black shrink-0" data-testid="host-join-qr"><QRCodeSVG value={url} size={116} /></div>
        <div className="min-w-0">
          <div className="text-5xl font-extrabold neon-yellow tracking-[.12em]" data-testid="host-room-code">{s.code}</div>
          <p className="text-xs text-[var(--hh-muted)] break-all mt-1">{url}</p>
          <p className="mt-2 hh-chip" style={{ background: "var(--hh-pink)", color: "#000" }}><Users size={12} /> {t("teams_count", { n: s.team_count })}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 mt-4">
        <Btn variant="cyan" onClick={() => window.open(`/screen/${s.code}`, "_blank", "noopener")} data-testid="host-open-screen"><MonitorPlay size={20} /> {t("open_big_screen")}</Btn>
        {!s.host.demo_loaded && <Btn variant="ghost" onClick={onLoadDemo} disabled={busy} data-testid="host-load-demo-run"><Users size={18} /> {t("load_demo")}</Btn>}
      </div>
    </Section>
  );
}

function PaceControls({ s, act, busy, ask }) {
  const { t } = useLang();
  const p = s.phase;
  const inRound = ["round_intro", "question_open", "question_locked", "reveal", "scoreboard"].includes(p);
  if (!inRound) return null;
  const roundEndBoard = p === "scoreboard" && s.scoreboard && s.scoreboard.round_end;
  return (
    <Section title={t("pace")} testid="host-pace">
      <div className="grid grid-cols-3 gap-2.5">
        <Btn size="sm" variant="ghost" disabled={busy || p !== "question_open"} onClick={() => act("add_time")} data-testid="host-add-time"><Timer size={16} /> {t("add10")}</Btn>
        <Btn size="sm" variant={s.frozen ? "cyan" : "ghost"} disabled={busy} onClick={() => act("freeze")} data-testid="host-freeze">
          {s.frozen ? <PlayIcon size={16} /> : <Snowflake size={16} />} {s.frozen ? t("unfreeze") : t("freeze")}
        </Btn>
        <Btn size="sm" variant="ghost" disabled={busy || !["question_open", "question_locked"].includes(p)} onClick={() => ask("skip")} data-testid="host-skip"><SkipForward size={16} /> {t("skip")}</Btn>
        <Btn size="sm" variant="ghost" disabled={busy || s.question_index < 0 || p === "round_intro"} onClick={() => ask("previous")} data-testid="host-previous"><SkipBack size={16} /> {t("previous")}</Btn>
        <Btn size="sm" variant="ghost" className="col-span-2" disabled={busy || roundEndBoard} onClick={() => ask("end_round")} data-testid="host-end-round"><Square size={16} /> {t("end_round")}</Btn>
      </div>
    </Section>
  );
}

function RadarBars({ s }) {
  const { t, lang } = useLang();
  const h = s.host;
  const q = h.question;
  if (!h.distribution || !q) {
    const answered = h.teams.filter((tm) => tm.answered && !tm.hidden);
    return (
      <Section title={t("radar_title")} testid="host-radar-waiting">
        <p className="font-semibold">{t("radar_wait")}</p>
        {s.phase === "question_open" && (
          <>
            <p className="hh-meta mt-4 mb-2">{t("answered_of", { a: s.answered_count, b: s.eligible_count })}</p>
            <div className="flex flex-wrap gap-1.5">
              {answered.map((tm) => <span key={tm.id} className="hh-chip normal-case whitespace-normal max-w-full" style={{ borderLeft: `6px solid ${tm.color}` }}>{tm.emoji} {tm.name}</span>)}
            </div>
          </>
        )}
      </Section>
    );
  }
  const max = Math.max(1, ...h.distribution.map((d) => d.count));
  return (
    <Section title={t("radar_title")} right={<span className="hh-chip" style={{ background: "#000", color: "var(--hh-yellow)" }}><EyeOff size={12} /> {t("radar_private")}</span>} testid="host-riff-radar-bars">
      {h.lock_reason && <p className="text-sm text-[var(--hh-muted)] mb-3">{t(`lock_reason_${h.lock_reason === "all_answered" ? "all" : h.lock_reason}`)}</p>}
      <div className="grid grid-cols-1 gap-3">
        {h.distribution.map((d) => {
          const a = ANSWER[d.index];
          const correct = d.index === q.correct_index;
          return (
            <div key={d.index} data-testid={`host-radar-option-${a.key}`}>
              <div className="flex items-center gap-2 mb-1">
                <Shape shape={a.shape} fill={a.color} size={18} />
                <span className="font-extrabold flex-1 truncate">{q.options[d.index][lang]}</span>
                {correct && <Check size={18} className="text-[var(--hh-lime)]" />}
                <span className="font-extrabold tabular-nums text-xl">{d.count}</span>
              </div>
              <div className="h-4 bg-black border-2 border-black">
                <motion.div initial={{ width: 0 }} animate={{ width: `${(d.count / max) * 100}%` }} transition={{ duration: 0.25 }} className="h-full" style={{ background: a.color }} />
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {d.teams.length === 0 && <span className="text-sm text-[var(--hh-muted)]">{t("radar_nobody")}</span>}
                {d.teams.map((tm) => (
                  <span key={tm.id} className="hh-chip normal-case tracking-normal whitespace-normal max-w-full" style={{ borderLeft: `6px solid ${tm.color}` }}>
                    {tm.emoji} {tm.name} <span className="text-[var(--hh-muted)]">{(tm.ms / 1000).toFixed(1)}s</span>
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function TeamRow({ tm, now, onOpen }) {
  const { t } = useLang();
  const online = tm.is_demo || (tm.last_seen && now - tm.last_seen < 10000);
  return (
    <button onClick={() => onOpen(tm)} className="w-full text-left flex items-stretch border-2 border-black bg-[var(--hh-raised)] min-h-[64px]" style={{ opacity: tm.hidden ? 0.5 : 1 }}
      data-testid={`host-team-row-${tm.number}`}>
      <span className="w-2 shrink-0" style={{ background: tm.color }} />
      <span className="flex-1 min-w-0 p-2.5">
        <span className="flex items-center gap-2 min-w-0">
          <span className="text-xl" aria-hidden="true">{tm.emoji}</span>
          <span className="font-extrabold truncate">{tm.name}</span>
          <span className={`hh-dot shrink-0`} style={{ background: online ? "#A3E635" : "#55556A" }} title={online ? "online" : "offline"} data-testid={`host-team-conn-${tm.number}`} />
          {tm.mic_ready && <Mic size={14} className="text-[var(--hh-cyan)] shrink-0" aria-label="mic-ready" />}
        </span>
        <span className="flex flex-wrap items-center gap-1.5 mt-1.5">
          <span className="hh-chip" style={{ background: ROAST_COLORS[tm.roast_level], color: "#000" }} data-testid={`host-team-roast-${tm.number}`}>{t(`roast_${tm.roast_level}`)}</span>
          {tm.name_status !== "shown" && <span className="hh-chip" style={{ background: VERDICT_COLORS[tm.name_verdict] || "#FFE14D", color: "#000" }} data-testid={`host-team-pending-${tm.number}`}>{t("name_pending")} · {t(`verdict_${tm.name_verdict}`)}</span>}
          {tm.streak >= 2 && <span className="hh-chip" style={{ background: "#000", color: "#FFE14D" }}><Flame size={11} /> {t("tag_hot")} ×{tm.streak}</span>}
          {tm.cold >= 2 && tm.streak === 0 && <span className="hh-chip" style={{ background: "#000", color: "#22D3EE" }}><Snowflake size={11} /> {t("tag_cold")}</span>}
          {tm.is_demo && <span className="hh-chip" style={{ background: "#2C2C3B" }} data-testid={`host-team-demo-${tm.number}`}>{t("tag_demo")}</span>}
          {tm.hidden && <span className="hh-chip" style={{ background: "#2C2C3B" }}>{t("tag_hidden")}</span>}
        </span>
        {tm.fun_fact && (
          <span className={`block text-sm mt-1 truncate ${tm.fun_fact_status === "blocked" ? "line-through text-[#6B6B7E]" : "text-[var(--hh-muted)]"}`}>
            “{tm.fun_fact}” {tm.fun_fact_status === "pending" && <b className="text-[var(--hh-yellow)] not-italic">· {t("fact_pending")}</b>}
          </span>
        )}
      </span>
      <span className="flex flex-col items-end justify-center px-3 border-l-2 border-black bg-[var(--hh-surface)]">
        <span className="font-extrabold tabular-nums text-lg">{tm.total.toLocaleString()}</span>
        {tm.rank && <span className="text-xs text-[var(--hh-muted)]">#{tm.rank}</span>}
      </span>
    </button>
  );
}

function TeamSheet({ team, onClose, act, busy }) {
  const { t } = useLang();
  if (!team) return null;
  const op = async (o) => { await act("team", { op: o, team_id: team.id }); onClose(); };
  return (
    <Sheet open={!!team} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="bottom" className="bg-[var(--hh-raised)] border-t-2 border-black text-[var(--hh-text)]" data-testid="host-team-sheet">
        <SheetHeader className="text-left">
          <SheetTitle className="text-2xl font-extrabold text-[var(--hh-text)] flex items-center gap-2"><span>{team.emoji}</span> {team.name}</SheetTitle>
          <SheetDescription className="text-[var(--hh-muted)]">
            {t("team_n", { n: team.number })} · {t(`roast_${team.roast_level}`)} · {team.total} {t("pts")}
          </SheetDescription>
        </SheetHeader>
        {team.name_status !== "shown" && (
          <p className="mt-3 text-sm p-2 border-2" style={{ borderColor: VERDICT_COLORS[team.name_verdict] }}>
            {t(`verdict_${team.name_verdict}`)}{team.name_reason ? ` · ${team.name_reason}` : ""}
          </p>
        )}
        {team.fun_fact && (
          <p className={`mt-3 text-sm ${team.fun_fact_status === "blocked" ? "line-through text-[#6B6B7E]" : ""}`}>“{team.fun_fact}” <span className="text-[var(--hh-muted)]">· {t(`verdict_${team.fun_fact_verdict || "allow"}`)}{team.fun_fact_reason ? ` · ${team.fun_fact_reason}` : ""}</span></p>
        )}
        <div className="grid gap-3 mt-5 pb-4">
          {team.name_status !== "shown" && team.name_verdict !== "block" && (
            <Btn variant="lime" disabled={busy} onClick={() => op("approve_name")} data-testid="host-team-approve-name"><Check size={18} /> {t("approve_name")}</Btn>
          )}
          {team.fun_fact && team.fun_fact_status === "pending" && (
            <Btn variant="cyan" disabled={busy} onClick={() => op("approve_fact")} data-testid="host-team-approve-fact"><Check size={18} /> {t("approve_fact")}</Btn>
          )}
          {team.fun_fact && team.fun_fact_status === "approved" && (
            <Btn variant="ghost" disabled={busy} onClick={() => op("hide_fact")} data-testid="host-team-hide-fact"><EyeOff size={18} /> {t("hide_fact")}</Btn>
          )}
          {team.hidden ? (
            <Btn variant="ghost" disabled={busy} onClick={() => op("unhide")} data-testid="host-team-unhide"><Eye size={18} /> {t("unhide_team")}</Btn>
          ) : (
            <Btn variant="red" disabled={busy} onClick={() => op("hide")} data-testid="host-team-hide"><EyeOff size={18} /> {t("hide_team")}</Btn>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function MoreTab({ s, act, busy, ask, code, hostKey, refresh }) {
  const { t, lang } = useLang();
  const h = s.host;
  const copyHost = async () => {
    const link = `${window.location.origin}/host/${code}?key=${hostKey}`;
    try { await navigator.clipboard.writeText(link); toast.success(t("copied")); } catch (e) { window.prompt(t("copy_host_link"), link); }
  };
  return (
    <div className="grid gap-4">
      <QuestionManager code={code} hostKey={hostKey} refresh={refresh} version={s.question_total} />
      <Section title={t("copy_host_link")} testid="host-more-link">
        <p className="text-sm text-[var(--hh-yellow)] font-semibold mb-3" data-testid="host-link-warning">⚠ {t("host_link_warning")}</p>
        <div className="grid grid-cols-2 gap-3">
          <Btn variant="yellow" onClick={copyHost} data-testid="host-copy-link"><Copy size={18} /> {t("copy_host_link")}</Btn>
          <Btn variant="cyan" onClick={() => window.open(`/screen/${code}`, "_blank", "noopener")} data-testid="host-open-screen-more"><MonitorPlay size={18} /> {t("open_big_screen")}</Btn>
        </div>
      </Section>
      <Section title={t("simulate_crowd")} testid="host-more-sim">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-[var(--hh-muted)]">{t("simulate_crowd_d")}</p>
          <Switch checked={!!h.settings.simulate_crowd} disabled={busy} onCheckedChange={(v) => act("settings", { settings: { simulate_crowd: v } })} data-testid="host-simulate-toggle" />
        </div>
        <div className="mt-4">
          {h.demo_loaded ? (
            <p className="text-sm font-semibold text-[var(--hh-lime)]" data-testid="host-demo-loaded"><Check size={14} className="inline" /> {t("demo_loaded")}</p>
          ) : (
            <Btn variant="ghost" className="w-full" disabled={busy || s.phase !== "lobby"} onClick={() => act("load_demo")} data-testid="host-load-demo"><Users size={18} /> {t("load_demo")}</Btn>
          )}
          {!h.demo_loaded && s.phase !== "lobby" && <p className="text-xs text-[var(--hh-muted)] mt-2">{t("lobby_only")}</p>}
        </div>
      </Section>
      <Section title={t("night_plan")} testid="host-more-plan">
        <ol className="grid gap-1.5">
          {h.rounds.map((r, i) => (
            <li key={i} className="flex items-center justify-between border-2 border-[var(--hh-line)] p-2">
              <span className="font-semibold">{i + 1}. {lang === "vi" ? r.name_vi : r.name_en}</span>
              <span className="text-sm text-[var(--hh-muted)]">{t("questions_n", { n: r.count })}</span>
            </li>
          ))}
        </ol>
      </Section>
      <Section title={t("decision_log")} testid="host-decision-log">
        {h.decision_log.length === 0 ? <p className="text-sm text-[var(--hh-muted)]">{t("log_empty")}</p> : (
          <ul className="grid gap-1.5 max-h-[320px] overflow-y-auto">
            {h.decision_log.map((d, i) => (
              <li key={i} className="flex items-start gap-2 text-sm border-b border-[var(--hh-line)] pb-1.5">
                <span className="hh-chip shrink-0" style={{ background: VERDICT_COLORS[d.verdict], color: "#000" }}>{t(`verdict_${d.verdict}`)}</span>
                <span className="flex-1 min-w-0">
                  <span className="font-semibold break-words">{d.item_text}</span>
                  <span className="block text-xs text-[var(--hh-muted)]">{new Date(d.at).toLocaleTimeString()} · {t(`actor_${d.actor}`)} · {d.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title={t("danger_zone")} testid="host-more-danger">
        <Btn variant="red" className="w-full" disabled={busy} onClick={() => ask("reset")} data-testid="host-reset-room"><RotateCcw size={18} /> {t("reset_room")}</Btn>
      </Section>
    </div>
  );
}

export default function HostConsole() {
  const { code: raw } = useParams();
  const code = normCode(raw);
  const { t } = useLang();
  const hostKey = useMemo(() => getHostKey(code), [code]);
  const { state: s, status, reconnecting, refresh, serverNow } = useRoomState(code, "host", { hostKey, enabled: !!hostKey });
  const cd = useCountdown(s, serverNow);
  const [tab, setTab] = useState("run");
  const [busy, setBusy] = useState(false);
  const [sheetTeam, setSheetTeam] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [now, setNow] = useState(serverNow());
  useWakeLock(true);
  useTitle(s ? `${t("tab_run")} · ${s.code}` : t("tab_run"));

  useEffect(() => {
    const id = setInterval(() => setNow(serverNow()), 2000);
    return () => clearInterval(id);
  }, [serverNow]);

  // auto-switch to Riff Radar when answers lock
  const phase = s && s.phase;
  useEffect(() => {
    if (phase === "question_locked") setTab("radar");
    if (phase === "question_open" || phase === "round_intro" || phase?.startsWith("poll_")) setTab("run");
  }, [phase]);

  if (!hostKey || status === "forbidden") {
    return (
      <div className="hh-bg flex flex-col items-center justify-center p-6 text-center">
        <Lock size={56} className="text-[var(--hh-yellow)]" />
        <h1 className="text-3xl font-extrabold mt-6" data-testid="host-no-key">{t("no_key_title")}</h1>
        <p className="text-[var(--hh-muted)] mt-2 max-w-sm">{t("no_key_sub")}</p>
        <div className="mt-6"><LangToggle /></div>
      </div>
    );
  }
  if (status === "notfound") return <WrongCode />;
  if (!s) return <LoadingStage />;

  const act = async (action, body = {}) => {
    setBusy(true);
    try {
      const res = await postRetry(`/rooms/${code}/host/${action}`, body, { params: { key: hostKey } });
      if (res && res.stale) toast(t("stale_action"));
    } catch (e) {
      toast.error(t2Error(e, t));
    } finally {
      setBusy(false);
      refresh();
    }
  };
  const next = () => act("next", { expected_phase: s.phase, expected_qi: s.question_index });
  const ask = (kind) => setConfirm(kind);
  const confirmText = { reset: t("reset_confirm"), end_round: t("end_round_confirm"), skip: t("skip_confirm"), previous: t("previous_confirm") };
  const na = s.host.next_action;
  const timerActive = cd.active && ["question_open", "poll_open"].includes(s.phase);

  return (
    <div className="hh-bg hh-workspace flex flex-col" style={{ minHeight: "100dvh" }}>
      <ReconnectBadge show={reconnecting} />
      <header className="sticky top-0 z-40 bg-[var(--hh-surface)] border-b-2 border-black">
        <div className="hh-host-width mx-auto px-4 py-3 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="font-extrabold truncate leading-tight" data-testid="host-phase">{t(`phase_${s.phase}`)}</p>
            <p className="text-xs text-[var(--hh-muted)] truncate">
              {s.code} · <span data-testid="host-team-count">{t("teams_count", { n: s.team_count })}</span>
              {s.question_number > 0 && ` · ${t("q_label", { a: s.question_number, b: s.question_total })}`}
            </p>
          </div>
          {timerActive && (
            <span className="text-3xl font-extrabold tabular-nums px-2 border-2 border-black" style={{ background: cd.frozen ? "var(--hh-cyan)" : cd.fraction < 0.25 ? "var(--hh-red)" : "var(--hh-yellow)", color: "#000" }} data-testid="host-countdown">
              {cd.frozen ? <Pause size={22} className="inline" /> : fmtSec(cd.remaining)}
            </span>
          )}
          <button onClick={() => act("blackout")} disabled={busy} className={`hh-btn hh-black hh-size-sm ${s.blackout ? "on" : ""}`} data-testid="host-blackout-button" aria-pressed={s.blackout}>
            <EyeOff size={16} /> <span>{s.blackout ? t("blackout_on") : t("blackout")}</span>
          </button>
          <LangToggle />
        </div>
        <div className="border-t-2 border-black bg-black text-[var(--hh-yellow)] text-[11px] leading-snug font-semibold px-3 py-1 line-clamp-2" data-testid="host-house-rules" title={t("house_rules")}>
          ★ {t("house_rules")}
        </div>
        {s.blackout && <div className="bg-[var(--hh-yellow)] text-black text-sm font-extrabold px-3 py-1.5" data-testid="host-blackout-banner">{t("blackout_banner")}</div>}
      </header>

      <main className="hh-host-width flex-1 w-full mx-auto px-4 pt-6 pb-[190px] grid grid-cols-1 gap-6 content-start min-w-0">
        <div className="hh-workspace-title"><div><p className="hh-meta mb-2">{t("t2_backstage")}</p><h1 className="text-3xl sm:text-4xl font-semibold tracking-tight" data-testid="host-workspace-title">{t(tab === "more" ? "t2_show_library" : tab === "radar" ? "tab_radar" : "t2_live_control")}</h1></div><span className="hh-session-code" data-testid="host-session-code">{s.code}</span></div>
        {tab === "run" && (
          <div className="hh-run-grid" data-testid="run-workspace">
            <div className="space-y-5 min-w-0">
              {timerActive && <Section testid="host-timer"><div className="flex items-center gap-3"><TimerBar fraction={cd.fraction} frozen={cd.frozen} className="flex-1" testid="host-countdown-bar" /><span className="font-semibold text-sm tabular-nums" data-testid="host-answered-count">{s.poll ? t("t2_submissions", { n: s.poll.submitted_count }) : t("answered_of", { a: s.answered_count, b: s.eligible_count })}</span></div></Section>}
              {!s.poll && <Teleprompter s={s} />}
              <PollHost s={s} act={act} busy={busy} />
              <PaceControls s={s} act={act} busy={busy} ask={ask} />
            </div>
            <aside className="space-y-5 min-w-0" data-testid="run-soundboard-dock">
              <Soundboard s={s} act={act} busy={busy} />
              {s.phase === "lobby" && <JoinCard s={s} busy={busy} onLoadDemo={() => act("load_demo")} />}
              {s.poll && <Teleprompter s={s} />}
            </aside>
          </div>
        )}
        {tab === "radar" && (
          <>
            <RadarBars s={s} />
            <Section title={`${t("team_list")} · ${s.team_count}`} testid="host-team-list">
              {s.host.teams.length === 0 ? <p className="text-[var(--hh-muted)]">{t("no_teams")}</p> : (
                <div className="grid grid-cols-1 gap-2">
                  {[...s.host.teams].sort((a, b) => (a.rank || 999) - (b.rank || 999) || a.number - b.number).map((tm) => (
                    <TeamRow key={tm.id} tm={tm} now={now} onOpen={setSheetTeam} />
                  ))}
                </div>
              )}
            </Section>
          </>
        )}
        {tab === "more" && <MoreTab s={s} act={act} busy={busy} ask={ask} code={code} hostKey={hostKey} refresh={refresh} />}
      </main>

      {/* Giant NEXT, bottom-right where the thumb rests */}
      <div className={`fixed z-40 right-3 bottom-[78px] w-[min(300px,62vw)] ${tab === "more" ? "hidden" : ""}`}>
        <Btn variant="yellow" size="xl" className="w-full !min-h-[72px] text-xl" disabled={busy || na === "none"} onClick={next} data-testid="host-next-button">
          {t(`next_${na}`)} <ChevronRight size={26} />
        </Btn>
      </div>

      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-[var(--hh-surface)] border-t-2 border-black" data-testid="host-tabs">
        <div className="max-w-3xl mx-auto grid grid-cols-3">
          {[
            { k: "run", icon: Zap, label: t("tab_run") },
            { k: "radar", icon: Radar, label: t("tab_radar") },
            { k: "more", icon: MoreHorizontal, label: t("tab_more") },
          ].map(({ k, icon: Icon, label }) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`host-tab-${k}`} aria-pressed={tab === k}
              className="h-[64px] flex flex-col items-center justify-center gap-0.5 font-extrabold text-xs uppercase tracking-[.12em] border-r-2 border-black last:border-r-0"
              style={{ background: tab === k ? "var(--hh-pink)" : "transparent", color: tab === k ? "#000" : "var(--hh-muted)" }}>
              <Icon size={20} /> {label}
              {k === "radar" && s.phase === "question_locked" && tab !== "radar" && <span className="absolute mt-[-34px] ml-[44px] w-2.5 h-2.5 bg-[var(--hh-yellow)] border border-black" />}
            </button>
          ))}
        </div>
      </nav>

      <TeamSheet team={sheetTeam && s.host.teams.find((x) => x.id === sheetTeam.id)} onClose={() => setSheetTeam(null)} act={act} busy={busy} />
      <Confirm open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)} text={confirm ? confirmText[confirm] : ""} testid="host-confirm"
        onYes={() => { const k = confirm; setConfirm(null); act(k); }} />
    </div>
  );
}
