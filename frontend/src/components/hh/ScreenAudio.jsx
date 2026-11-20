import React, { useEffect, useRef, useState } from "react";
import { Volume2 } from "lucide-react";
import { ShowAudio } from "@/lib/showAudio";
import { useLang } from "@/lib/lang";
import { T2Button } from "./QuestionManager";

export const ScreenAudio = ({ s, cd }) => {
  const { t } = useLang();
  const synth = useRef(null);
  const [unlocked, setUnlocked] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [unlockError, setUnlockError] = useState(false);
  const seen = useRef(new Set());
  const initialized = useRef(false);
  const lastTick = useRef("");
  const [lastPlayed, setLastPlayed] = useState("");
  const play = name => { try { if (synth.current?.play(name)) setLastPlayed(name); } catch (_) {} };
  useEffect(() => () => { synth.current?.close(); }, []);
  useEffect(() => { if (!s.sound_on || s.frozen) synth.current?.stop(); }, [s.sound_on, s.frozen]);
  useEffect(() => {
    const events = [...(s.sound_events || []), ...(s.events || []).filter(e => e.type !== "sound")].sort((a, b) => a.at - b.at);
    for (const e of events) {
      if (seen.current.has(e.id)) continue;
      seen.current.add(e.id);
      // Never replay historical cues on reload, unmute, or after unlocking audio.
      if (!initialized.current || !unlocked || !s.sound_on || s.server_now - e.at > 5000) continue;
      const name = e.type === "sound" ? e.payload.sound : ({ team_joined: "pop", viral_drop: "siren", bribe: "cash_register" })[e.type];
      if (name) play(name);
    }
    initialized.current = true;
    if (seen.current.size > 500) seen.current = new Set(events.map(e => e.id));
  }, [s, unlocked]);
  const sec = Math.ceil(cd.remaining / 1000);
  useEffect(() => {
    if (!unlocked || !s.sound_on || s.frozen || !cd.active || !["question_open", "poll_open"].includes(s.phase) || sec < 1 || sec > 5) return;
    const stamp = `${s.phase_started_at}:${sec}`;
    if (lastTick.current !== stamp) { lastTick.current = stamp; play("tick_tock"); }
  }, [sec, cd.active, unlocked, s.sound_on, s.frozen, s.phase, s.phase_started_at]);
  const unlock = async () => {
    setUnlocking(true); setUnlockError(false);
    try {
      if (!window.AudioContext && !window.webkitAudioContext) { setUnsupported(true); setUnlocked(true); return; }
      if (!synth.current) synth.current = new ShowAudio();
      if (await synth.current.unlock()) setUnlocked(true); else setUnlockError(true);
    } catch (_) { setUnlockError(true); }
    finally { setUnlocking(false); }
  };
  return <>
    <span className="sr-only" data-testid="screen-audio-status" data-ready={unlocked} data-muted={!s.sound_on} data-last-played={lastPlayed}>{t(unsupported ? "t2_audio_unsupported" : s.sound_on ? "t2_sound_on" : "t2_sound_off")}</span>
    {!unlocked && <div className="fixed inset-0 z-[100] bg-[var(--hh-bg)] flex flex-col items-center justify-center gap-6 p-6 text-center" data-testid="tv-audio-unlock-overlay"><Volume2 size={64} className="text-[var(--hh-cyan)]" /><h1 className="text-4xl lg:text-6xl font-extrabold text-[var(--hh-yellow)]">{t("t2_start_show_audio")}</h1><p className="max-w-lg text-lg text-[var(--hh-muted)]">{t("t2_audio_help")}</p>{unlockError && <p role="alert" data-testid="tv-audio-error">{t("t2_audio_retry")}</p>}<T2Button tone="pink" disabled={unlocking} onClick={unlock} className="text-xl min-h-20" data-testid="tv-audio-unlock-button">{t("t2_start_show_audio")}</T2Button><T2Button tone="ghost" onClick={() => { setUnsupported(true); setUnlocked(true); }} data-testid="tv-audio-silent-button">{t("t2_continue_silent")}</T2Button></div>}
  </>;
};
