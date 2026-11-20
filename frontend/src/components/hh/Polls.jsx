import React, { useState } from "react";
import { motion } from "framer-motion";
import { Check, Lock, MessageSquare, ThumbsUp, Trophy, Volume2, Drum, Music2, Bike, Megaphone, Hand, Bell, CircleSlash, AudioLines } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerTrigger } from "@/components/ui/drawer";
import { toast } from "sonner";
import { useLang } from "@/lib/lang";
import { postRetry } from "@/lib/api";
import { Field, T2Button, t2Error, useSmallScreen } from "./QuestionManager";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { TimerBar, fmtSec } from "./kit";

export const VoteCount = ({ value }) => <NumberFlow value={value} transformTiming={{ duration: 220, easing: "ease-out" }} opacityTiming={{ duration: 160, easing: "ease-out" }} respectMotionPreference />;

export const PollHost = ({ s, act, busy }) => {
  const { t, lang } = useLang();
  const [source, setSource] = useState("preset:0");
  const [text, setText] = useState("");
  const [textVi, setTextVi] = useState("");
  const [seconds, setSeconds] = useState(45);
  const p = s.poll;
  const active = s.phase.startsWith("poll_");
  const start = () => act("poll_start", { time_limit_s: seconds, ...(source === "custom" ? { text_en: text, text_vi: textVi } : source.startsWith("preset:") ? { preset: Number(source.split(":")[1]) } : { question_id: source }) });
  return <section className="hh-panel p-4 space-y-4 min-w-0" data-testid="host-poll-panel">
    <div className="flex items-center gap-3 flex-wrap"><h2 className="text-lg font-semibold">{t("t2_write_in")}</h2><span className="hh-meta ml-auto">{t("t2_no_brain")}</span></div>
    {active && <ol className="hh-poll-steps" data-testid="poll-stage-steps">{["poll_open", "poll_review", "poll_vote"].map((step, i) => <li key={step} data-active={s.phase === step}><span>{String(i + 1).padStart(2, "0")}</span>{t(`t2_stage_${i}`)}</li>)}</ol>}
    {!active ? <>
      <p className="text-sm text-[var(--hh-muted)]">{t("t2_interrupt_help")}</p>
      <Select value={source} onValueChange={setSource}><SelectTrigger className="hh-input !h-auto min-w-0 [&>span]:whitespace-normal text-left" data-testid="run-prompt-select" aria-label={t("t2_choose_prompt")}><SelectValue /></SelectTrigger><SelectContent className="max-w-[calc(100vw-32px)]"><SelectItem value="custom" data-testid="prompt-custom">{t("t2_custom_prompt")}</SelectItem>{[0, 1, 2, 3].map(i => <SelectItem value={`preset:${i}`} key={i} data-testid={`prompt-preset-${i}`} className="whitespace-normal">{t(`t2_preset_${i}`)}</SelectItem>)}{s.host.poll_seeds?.map(q => <SelectItem key={q.id} value={q.id} className="whitespace-normal" data-testid={`prompt-seed-${q.id}`}>{q[`text_${lang}`] || q.text_en}</SelectItem>)}</SelectContent></Select>
      {source === "custom" && <><Field id="run-custom-prompt" label={t("t2_custom_prompt")} multiline value={text} onChange={e => setText(e.target.value)} maxLength={500} /><Field id="run-custom-prompt-vi" label={t("t2_optional_vi")} multiline value={textVi} onChange={e => setTextVi(e.target.value)} maxLength={500} /></>}
      <div className="grid sm:grid-cols-2 gap-4 items-end"><Field id="run-poll-time" label={t("t2_time_limit")} type="number" min={5} max={180} value={seconds} onChange={e => setSeconds(Number(e.target.value))} /><T2Button tone="pink" disabled={busy || seconds < 5 || seconds > 180 || (source === "custom" && !text.trim())} onClick={start} data-testid="run-start-button">{t("t2_start_poll")}</T2Button></div>
    </> : <>
      <p className="text-xl font-extrabold break-words" data-testid="host-poll-prompt">{p[`text_${lang}`]}</p>
      <p className="text-sm text-[var(--hh-muted)]" data-testid="host-poll-count">{t("t2_submissions", { n: p.submitted_count })} · {t(`phase_${s.phase}`)}</p>
      {s.phase === "poll_open" && <><p className="text-sm">{t("t2_wait_lock")}</p><div className="flex flex-wrap gap-3"><T2Button tone="yellow" disabled={busy} onClick={() => act("next", { expected_phase: s.phase })} data-testid="run-lock-button"><Lock />{t("next_poll_lock")}</T2Button><T2Button tone="ghost" disabled={busy} onClick={() => act("add_time")} data-testid="poll-add-time">{t("add10")}</T2Button><T2Button tone="ghost" disabled={busy} onClick={() => act("freeze")} data-testid="poll-freeze">{t(s.frozen ? "unfreeze" : "freeze")}</T2Button></div></>}
      {["poll_review", "poll_vote"].includes(s.phase) && <>
        <div className="hh-chip text-[var(--hh-yellow)]" data-testid="moderation-approved-count">{t("t2_approved_count", { n: p.groups.filter(g => g.status === "approved").length })}</div>
        <Collapsible><CollapsibleTrigger className="text-xs text-[var(--hh-muted)] underline underline-offset-4 min-h-11" data-testid="poll-scoring-help">{t("t2_scoring_help")}</CollapsibleTrigger><CollapsibleContent className="text-sm text-[var(--hh-muted)] pb-3">{t("t2_scoring_rules")}</CollapsibleContent></Collapsible>
        <div className="divide-y divide-[var(--hh-line)]" data-testid="moderation-queue">{p.groups.length === 0 && <p data-testid="moderation-empty">{t("t2_no_submissions")}</p>}{p.groups.map(g => <article key={g.id} className={`hh-moderation-row ${g.status === "hidden" ? "is-hidden" : ""}`} data-testid={`moderation-answer-${g.id}`}>
          <div className="min-w-0 space-y-2"><div className="flex flex-wrap gap-2 justify-between"><span className={`hh-row-meta ${g.status === "approved" ? "text-[var(--hh-cyan)]" : ""}`}>{t(`t2_status_${g.status}`)}</span><span className="hh-row-meta" data-testid={`moderation-count-${g.id}`}>×{g.count} · {t("t2_votes", { n: g.votes })}</span></div>
          <p className="text-lg font-semibold break-words">{lang === "vi" ? g.text_vi : g.text}</p>
          <ul className="text-xs text-[var(--hh-muted)] flex flex-wrap gap-x-3 gap-y-1">{g.authors.map((a, i) => <li key={i} data-testid={`moderation-author-${g.id}-${i}`} className="break-words">{a.name} · {t(`verdict_${a.verdict}`)}{a.anonymous ? ` · ${t("t2_anonymous")}` : ""}</li>)}</ul></div>
          {p.kind === "poll" && <div className="flex gap-2 shrink-0"><T2Button tone="ghost" className="!text-[var(--hh-cyan)]" data-testid={`moderation-approve-${g.id}`} disabled={busy || g.status === "approved" || g.verdict === "block" || p.groups.filter(x => x.status === "approved").length >= 6} onClick={() => act("poll_moderate", { poll_id: p.id, answer_id: g.id, verdict: "approve" })}><Check />{t("t2_approve")}</T2Button><T2Button tone="ghost" data-testid={`moderation-hide-${g.id}`} disabled={busy || g.status === "hidden"} onClick={() => act("poll_moderate", { poll_id: p.id, answer_id: g.id, verdict: "hide" })}>{t("t2_hide")}</T2Button></div>}
        </article>)}</div>
      </>}
      {s.phase === "poll_hof" && <HallOfFame s={s} surface="host" />}
    </>}
  </section>;
};

export const Soundboard = ({ s, act, busy }) => {
  const { t } = useLang();
  const effects = [["rimshot", Drum], ["sad_trombone", Music2], ["motorbike_horn", Bike], ["air_horn", Megaphone], ["drumroll", AudioLines], ["applause", Hand], ["ding", Bell], ["buzz", CircleSlash]];
  return <section className="hh-panel p-4 space-y-4" data-testid="soundboard"><div className="flex items-center gap-3"><h2 className="font-semibold text-lg">{t("t2_soundboard")}</h2><Label htmlFor="sound-toggle" className="ml-auto text-xs text-[var(--hh-muted)]">{t("t2_sound_on")}</Label><Switch id="sound-toggle" data-testid="host-sound-toggle" checked={s.sound_on} disabled={busy} onCheckedChange={v => act("settings", { settings: { sound_on: v } })} /></div><p className="text-xs text-[var(--hh-muted)] leading-relaxed">{t("t2_screen_only")}</p><div className="grid grid-cols-4 gap-2">{effects.map(([sound, Icon]) => <T2Button key={sound} tone="ghost" className="hh-sound-key aspect-square flex-col !px-1 !py-2 !text-[11px] !font-medium" disabled={busy || !s.sound_on} onClick={() => act("sound", { sound })} data-testid={`soundboard-button-${sound.replaceAll("_", "-")}`}><Icon size={21} strokeWidth={1.5} /><span>{t(`t2_sound_${sound}`)}</span></T2Button>)}</div></section>;
};

const Authors = ({ authors }) => {
  const { t } = useLang();
  return <span>{authors?.length ? authors.map(a => a.name || t("team_n", { n: a.number })).join(" / ") : t("t2_anonymous")}</span>;
};

export const HallOfFame = ({ s, surface, onClaim, busy }) => {
  const { t, lang } = useLang();
  const h = s.hall_of_fame;
  return <section className={`hh-hof p-6 sm:p-10 space-y-6 min-w-0 ${surface === "screen" ? "m-4 lg:m-12" : ""}`} data-testid={`${surface}-hof-frame`}>
    <div className="flex items-center gap-3 text-[var(--hh-yellow)]"><Trophy className="shrink-0" /><h2 className={`font-semibold uppercase tracking-widest ${surface === "screen" ? "text-lg lg:text-2xl" : "text-sm"}`}>{t("t2_hof")}</h2></div>
    {h ? <><p className={`font-semibold tracking-tight leading-snug break-words ${surface === "screen" ? "text-3xl lg:text-6xl" : "text-2xl"}`} data-testid={`${surface}-hof-answer`}>“{lang === "vi" ? h.text_vi : h.text}”</p><p className="text-[var(--hh-muted)]" data-testid={`${surface}-hof-votes`}>{t("t2_votes", { n: h.votes })}</p><p className="text-[var(--hh-yellow)] font-semibold" data-testid={`${surface}-hof-revealed-name`}><Authors authors={h.claimed_names} /></p>{surface === "phone" && h.can_claim && <><p>{t("t2_claim_help")}</p><T2Button tone="yellow" disabled={busy} onClick={onClaim} data-testid="hof-claim-button">{t("t2_that_was_us")}</T2Button></>}{surface === "phone" && h.claimed && <p data-testid="hof-claim-confirmation">{t("t2_claimed")}</p>}</> : <p data-testid={`${surface}-hof-empty`}>{t("t2_no_winner")}</p>}
  </section>;
};

export const PollPhone = ({ s, code, device, refresh, cd }) => {
  const { t, lang } = useLang();
  const [text, setText] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const p = s.poll;
  const send = async (action, extra = {}) => {
    setBusy(true);
    try { await postRetry(`/rooms/${code}/poll/${action}`, { poll_id: p.id, device_id: device, ...extra }); refresh(); }
    catch (e) { toast.error(t2Error(e, t)); refresh(); }
    finally { setBusy(false); }
  };
  if (s.phase === "poll_hof") return <HallOfFame s={s} surface="phone" onClaim={() => send("claim")} busy={busy} />;
  return <main className="hh-audience w-full max-w-lg mx-auto p-4 space-y-6 min-w-0" data-testid="phone-poll">
    <span className="hh-chip text-[var(--hh-yellow)]">{t(p.kind === "wrong_vote" ? "t2_funny_wrong" : "t2_write_in")}</span>
    <h1 className="text-2xl font-extrabold leading-snug break-words" data-testid="phone-poll-prompt">{p[`text_${lang}`]}</h1>
    {s.phase === "poll_open" ? <>
      <div className="flex items-center gap-3"><TimerBar fraction={cd.fraction} frozen={cd.frozen} className="flex-1" testid="phone-poll-timer" /><span className="text-2xl font-extrabold tabular-nums" data-testid="phone-poll-seconds">{fmtSec(cd.remaining)}</span></div>
      {!p.eligible ? <p data-testid="phone-poll-late">{t("joined_late")}</p> : p.submitted ? <div className="hh-panel-raised p-5 space-y-3" data-testid="phone-locked-status"><Check className="text-[var(--hh-lime)]" /><p className="font-extrabold">{t("locked_in_title")}</p><p className="break-words">{p.my_text}</p><p className="text-sm text-[var(--hh-muted)]">{t("t2_review_wait")}</p></div> : <form className="space-y-4" onSubmit={e => { e.preventDefault(); send("submit", { text, anonymous }); }}>
        <Field id="phone-answer-textarea" label={t("t2_your_answer")} multiline maxLength={160} value={text} onChange={e => setText(Array.from(e.target.value).slice(0, 80).join(""))} required aria-describedby="answer-limit" /><p id="answer-limit" className="hh-meta" data-testid="phone-answer-char-count">{Array.from(text).length}/80</p>
        <div className="flex gap-3 items-center min-h-12"><Checkbox id="phone-anonymous-checkbox" data-testid="phone-anonymous-checkbox" checked={anonymous} onCheckedChange={v => setAnonymous(!!v)} /><Label htmlFor="phone-anonymous-checkbox" className="py-3">{t("t2_anonymous")}</Label></div><p className="text-sm text-[var(--hh-muted)]">{t("t2_anonymous_help")}</p><T2Button type="submit" tone="pink" className="w-full" disabled={busy || !text.trim() || (!s.frozen && cd.remaining <= 0)} data-testid="phone-submit-button">{t("t2_submit_answer")}</T2Button>
      </form>}
    </> : <>
      <p className="text-sm text-[var(--hh-muted)]">{t("t2_vote_rules")}</p>
      <div className="grid gap-4" data-testid="phone-approved-answers-list">{p.groups.length === 0 && <p className="hh-panel p-5" data-testid="phone-approved-empty">{t("t2_review_wait")}</p>}{p.groups.map((g, i) => <article key={g.id} className="hh-answer-card p-5 space-y-4" data-testid={`phone-answer-${g.id}`}><span className="hh-meta">{String(i + 1).padStart(2, "0")}</span><p className="text-xl font-semibold leading-relaxed break-words">{lang === "vi" ? g.text_vi : g.text}</p><div className="flex gap-3 items-center justify-between border-t border-[var(--hh-line)] pt-3"><p className="text-xs text-[var(--hh-muted)] break-words min-w-0"><Authors authors={g.authors} /></p><T2Button className="!min-h-11 !px-3 !py-2 !text-xs shrink-0" tone={g.voted ? "cyan" : "ghost"} disabled={busy || g.own || g.voted} onClick={() => send("vote", { answer_id: g.id })} data-testid={`phone-vote-${g.id}`}><ThumbsUp size={14} />{t(g.own ? "t2_own_answer" : g.voted ? "t2_voted" : "t2_vote")} · <VoteCount value={g.votes} /></T2Button></div></article>)}</div>
    </>}
  </main>;
};

export const PollScreen = ({ s, cd }) => {
  const { t, lang } = useLang();
  const small = useSmallScreen();
  const p = s.poll;
  if (s.phase === "poll_hof") return <HallOfFame s={s} surface="screen" />;
  const ranked = [...p.groups].sort((a, b) => b.votes - a.votes || a.order - b.order).slice(0, 5);
  const ranking = <ol className="grid gap-3" data-testid="tv-top5-list">{ranked.map((g, i) => <motion.li layout="position" transition={{ duration: 0.2 }} key={g.id} className="flex gap-3 items-start border-b border-[var(--hh-line)] py-4 min-w-0" data-testid={`tv-top5-${i}`}><span className="font-semibold text-lg text-[var(--hh-muted)]">{String(i + 1).padStart(2, "0")}</span><span className="flex-1 min-w-0 break-words text-lg">{lang === "vi" ? g.text_vi : g.text}</span><span className="text-3xl font-semibold text-[var(--hh-yellow)]"><VoteCount value={g.votes} /></span></motion.li>)}</ol>;
  return <main className="hh-tv-poll p-4 lg:px-14 lg:py-6 flex-1 overflow-y-auto min-w-0 space-y-5" data-testid="tv-poll">
    <div className="flex gap-4 items-center flex-wrap"><span className="hh-meta">{t(p.kind === "wrong_vote" ? "t2_funny_wrong" : "t2_write_in")}</span><span className="text-sm text-[var(--hh-muted)]" data-testid="tv-poll-submitted">{t("t2_submissions", { n: p.submitted_count })}</span></div>
    <h1 className="text-3xl lg:text-5xl font-semibold tracking-tight leading-tight break-words" data-testid="tv-poll-prompt">{p[`text_${lang}`]}</h1>
    {s.phase === "poll_open" ? <div className="hh-panel p-6 lg:p-10 space-y-8"><p className="text-xl lg:text-3xl text-[var(--hh-muted)]">{t("t2_answer_on_phone")}</p>{p.media_hint && <p className="text-6xl" data-testid="tv-poll-emoji">{p.media_hint}</p>}<div className="flex gap-5 items-center"><span className="text-5xl lg:text-7xl font-semibold tabular-nums text-[var(--hh-yellow)]" data-testid="tv-poll-seconds">{fmtSec(cd.remaining)}</span><TimerBar fraction={cd.fraction} frozen={cd.frozen} className="flex-1 !h-2" testid="tv-poll-timer" /></div></div> : s.blackout ? <p className="text-2xl" data-testid="tv-poll-blackout">{t("blackout_banner")}</p> : <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-8">
      <div className="grid lg:grid-cols-2 gap-4 content-start" data-testid="tv-approved-cards">{p.groups.length === 0 && <p className="text-2xl col-span-full" data-testid="tv-approved-empty">{t("t2_review_wait")}</p>}{p.groups.map((g, i) => <motion.article initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.16 }} key={g.id} className="hh-answer-card p-5 space-y-3 min-w-0" data-testid={`tv-approved-${g.id}`}><span className="hh-meta">{String(i + 1).padStart(2, "0")}</span><p className="text-xl lg:text-3xl font-semibold leading-snug break-words">{lang === "vi" ? g.text_vi : g.text}</p><p className="text-sm text-[var(--hh-muted)] break-words"><Authors authors={g.authors} /></p></motion.article>)}</div>
      {small ? <Drawer shouldScaleBackground={false}><DrawerTrigger asChild><T2Button tone="ghost" data-testid="tv-top5-trigger">{t("t2_live_top5")}</T2Button></DrawerTrigger><DrawerContent className="max-h-[80dvh] p-4"><DrawerHeader><DrawerTitle>{t("t2_live_top5")}</DrawerTitle><DrawerDescription>{t("t2_vote_rules")}</DrawerDescription></DrawerHeader><div className="overflow-y-auto">{ranking}</div></DrawerContent></Drawer> : <aside className="border-l border-[var(--hh-line)] pl-6 min-w-0"><h2 className="text-lg uppercase tracking-widest font-semibold text-[var(--hh-yellow)]">{t("t2_live_top5")}</h2>{ranking}</aside>}
    </div>}
  </main>;
};
