import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Dice5, Mic, Check } from "lucide-react";
import { useLang } from "@/lib/lang";
import { useTitle } from "@/hooks/useRoomState";
import { Btn, LangToggle, LoadingStage, Wordmark } from "@/components/hh/kit";
import { http, deviceId, postRetry, errCode, normCode } from "@/lib/api";
import WrongCode from "@/pages/WrongCode";

const EMOJI = ["🍜", "🥖", "☕", "🛵", "🌶️", "🥭", "🍺", "🎤", "🦆", "🐉", "🐙", "🦀", "🌴", "🔥", "⚡", "🐸", "🦊", "🐯", "🍍", "🥥", "🎸", "👾", "🦄", "🌙"];
const ROAST = [
  { v: "off", color: "#A0A0B2", emoji: "🕊️" },
  { v: "mild", color: "#FFE14D", emoji: "🌶️" },
  { v: "spicy", color: "#F43F5E", emoji: "🔥" },
];

export default function Join() {
  const { code: raw } = useParams();
  const code = normCode(raw);
  const { t, lang } = useLang();
  const nav = useNavigate();
  useTitle(t("join_title"));
  const [status, setStatus] = useState("loading");
  const [room, setRoom] = useState(null);
  const [puns, setPuns] = useState([]);
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState(EMOJI[Math.floor(Math.random() * EMOJI.length)]);
  const [fact, setFact] = useState("");
  const [roast, setRoast] = useState("mild");
  const [mic, setMic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const dev = deviceId();

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [{ data: pub }, { data: st }] = await Promise.all([
          http.get(`/rooms/${code}/public`),
          http.get(`/rooms/${code}/state`, { params: { role: "player", device: dev } }),
        ]);
        if (!alive) return;
        if (st.me) { nav(`/play/${code}`, { replace: true }); return; }
        setRoom(pub);
        setStatus("ok");
      } catch (e) {
        if (!alive) return;
        setStatus(e.response && e.response.status === 404 ? "notfound" : "error");
      }
      try { const { data } = await http.get("/meta"); if (alive) setPuns(data.puns || []); } catch (e) { /* dice falls back */ }
    })();
    return () => { alive = false; };
  }, [code, dev, nav]);

  if (code.length !== 4 || status === "notfound") return <WrongCode />;
  if (status === "loading") return <LoadingStage />;

  const roll = () => {
    const list = puns.length ? puns : ["Phở Real", "Durian Duran", "Xe Ôm Nom Nom"];
    let n = list[Math.floor(Math.random() * list.length)];
    if (n === name && list.length > 1) n = list[(list.indexOf(n) + 1) % list.length];
    setName(n);
    setErr("");
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) { setErr(t("name_required")); return; }
    setBusy(true);
    try {
      await postRetry(`/rooms/${code}/join`, { device_id: dev, name: name.trim(), emoji, fun_fact: fact.trim(), lang, roast_level: roast, mic_ready: mic });
      nav(`/play/${code}`, { replace: true });
    } catch (ex) {
      const c = errCode(ex);
      setErr(c === "room_full" ? t("room_full") : c === "name_required" ? t("name_required") : t("error_generic"));
      toast.error(c === "room_full" ? t("room_full") : t("error_generic"));
      setBusy(false);
    }
  };

  return (
    <div className="hh-bg">
      <header className="flex items-center justify-between px-4 py-3 border-b-2 border-black bg-[var(--hh-surface)] sticky top-0 z-20">
        <Wordmark size="sm" />
        <div className="flex items-center gap-2">
          <span className="hh-chip" data-testid="join-room-code" style={{ background: "var(--hh-yellow)", color: "#000" }}>{code}</span>
          <LangToggle />
        </div>
      </header>
      <form onSubmit={submit} className="max-w-md mx-auto px-4 pt-6 pb-36 flex flex-col gap-7">
        <div>
          <p className="hh-meta">{room && room.venue_name ? room.venue_name : t("ticket_admit")}</p>
          <h1 className="text-4xl font-extrabold leading-[1.02] mt-1">{t("join_title")}</h1>
          <p className="text-[var(--hh-muted)] mt-2">{t("join_sub")}</p>
        </div>

        <div>
          <label className="hh-meta block mb-2" htmlFor="team-name">{t("team_name")}</label>
          <div className="flex gap-3">
            <input id="team-name" className="hh-input flex-1 min-w-0 text-lg" maxLength={30} value={name} placeholder={t("name_ph")}
              onChange={(e) => { setName(e.target.value); setErr(""); }} data-testid="join-team-name-input" />
            <Btn type="button" variant="yellow" onClick={roll} aria-label={t("dice")} title={t("dice")} data-testid="join-random-name-button" className="w-[60px] px-0">
              <Dice5 size={26} />
            </Btn>
          </div>
          <div className="flex justify-between mt-1.5 text-sm">
            <span className="text-[var(--hh-red)] font-semibold" data-testid="join-error">{err}</span>
            <span className="text-[var(--hh-muted)]">{t("chars_left", { n: 30 - name.length })}</span>
          </div>
        </div>

        <div>
          <span className="hh-meta block mb-2">{t("emoji_label")}</span>
          <div className="grid grid-cols-6 gap-2" data-testid="join-emoji-picker" role="radiogroup">
            {EMOJI.map((em, i) => (
              <button type="button" key={em} role="radio" aria-checked={emoji === em} onClick={() => setEmoji(em)} data-testid={`join-emoji-${i}`}
                className="aspect-square text-2xl flex items-center justify-center border-2 transition-[background-color,transform] duration-150 active:scale-95"
                style={{ borderColor: emoji === em ? "#000" : "var(--hh-line)", background: emoji === em ? "var(--hh-pink)" : "var(--hh-surface)", boxShadow: emoji === em ? "3px 3px 0 #000" : "none" }}>
                {em}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="hh-meta block mb-2" htmlFor="fun-fact">{t("fun_fact_label")}</label>
          <input id="fun-fact" className="hh-input" maxLength={80} value={fact} placeholder={t("fun_fact_ph")} onChange={(e) => setFact(e.target.value)} data-testid="join-fun-fact-input" />
          <span className="block text-right text-sm text-[var(--hh-muted)] mt-1.5">{t("chars_left", { n: 80 - fact.length })}</span>
        </div>

        <div>
          <span className="hh-meta block mb-2">{t("roast_label")}</span>
          <div className="grid grid-cols-3 gap-2.5" role="radiogroup">
            {ROAST.map((r) => {
              const on = roast === r.v;
              return (
                <button type="button" key={r.v} role="radio" aria-checked={on} onClick={() => setRoast(r.v)} data-testid={`join-roast-level-${r.v}`}
                  className="aspect-square flex flex-col items-start justify-between p-2.5 border-2 text-left transition-[background-color] duration-150"
                  style={{ borderColor: on ? "#000" : "var(--hh-line)", background: on ? r.color : "var(--hh-surface)", color: on ? "#000" : "var(--hh-text)", boxShadow: on ? "4px 4px 0 #000" : "none" }}>
                  <span className="text-2xl" aria-hidden="true">{r.emoji}</span>
                  <span>
                    <span className="block font-extrabold text-lg leading-none">{t(`roast_${r.v}_t`)}</span>
                    <span className="block text-[11px] leading-tight mt-1 font-semibold" style={{ opacity: on ? 0.85 : 0.7 }}>{t(`roast_${r.v}_d`)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <button type="button" onClick={() => setMic(!mic)} aria-pressed={mic} data-testid="join-mic-ready-toggle"
          className="flex items-center gap-3 p-4 border-2 text-left min-h-[64px]"
          style={{ borderColor: mic ? "#000" : "var(--hh-line)", background: mic ? "var(--hh-cyan)" : "var(--hh-surface)", color: mic ? "#000" : "var(--hh-text)", boxShadow: mic ? "4px 4px 0 #000" : "none" }}>
          <span className="w-10 h-10 flex items-center justify-center border-2 border-black shrink-0" style={{ background: mic ? "#000" : "var(--hh-raised)", color: mic ? "var(--hh-cyan)" : "var(--hh-muted)" }}>
            {mic ? <Check size={20} /> : <Mic size={20} />}
          </span>
          <span className="font-semibold">{t("mic_ready")}</span>
        </button>

        <p className="text-xs text-[var(--hh-muted)]">{t("privacy_note")}</p>

        <div className="fixed bottom-0 left-0 right-0 p-4 bg-[var(--hh-surface)] border-t-2 border-black z-20">
          <div className="max-w-md mx-auto flex items-center gap-3">
            <div className="w-[64px] h-[64px] shrink-0 flex items-center justify-center text-3xl border-2 border-black bg-[var(--hh-raised)]" aria-hidden="true">{emoji}</div>
            <Btn type="submit" variant="pink" size="xl" className="flex-1" disabled={busy} data-testid="join-submit-button">
              {busy ? t("joining") : t("join_submit")}
            </Btn>
          </div>
        </div>
      </form>
    </div>
  );
}
