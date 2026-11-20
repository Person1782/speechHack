import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Check, Users } from "lucide-react";
import { useLang } from "@/lib/lang";
import { useTitle } from "@/hooks/useRoomState";
import { Btn, LangToggle, Wordmark } from "@/components/hh/kit";
import { http, saveHostKey } from "@/lib/api";
import { DeckPicker } from "@/components/hh/DeckLibrary";
import { deckOwnerKey } from "@/lib/decks";

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="hh-meta block mb-2">{label}</span>
      {children}
      {hint && <span className="block mt-1.5 text-sm text-[var(--hh-muted)]">{hint}</span>}
    </label>
  );
}

function ChoiceCard({ active, onClick, title, desc, testid, accent = "var(--hh-cyan)" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      aria-pressed={active}
      className="text-left p-4 border-2 transition-[background-color,border-color] duration-150 min-h-[56px] w-full"
      style={{ borderColor: active ? "#000" : "var(--hh-line)", background: active ? accent : "var(--hh-surface)", color: active ? "#000" : "var(--hh-text)", boxShadow: active ? "4px 4px 0 #000" : "none" }}
    >
      <span className="flex items-center justify-between font-extrabold text-lg">{title}{active && <Check size={20} />}</span>
      {desc && <span className="block text-sm mt-1" style={{ opacity: active ? 0.85 : 0.7 }}>{desc}</span>}
    </button>
  );
}

export default function HostSetup() {
  const { t } = useLang();
  const nav = useNavigate();
  useTitle(t("setup_title"));
  const [f, setF] = useState({ host_name: "", venue_name: "", default_lang: "en", night_preset: "demo", load_demo: true, deck_id: "" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await http.post("/rooms", {...f, owner_key: f.deck_id ? deckOwnerKey() : undefined});
      saveHostKey(data.code, data.host_key);
      nav(`/host/${data.code}?key=${data.host_key}`);
    } catch (err) {
      toast.error(t("error_generic"));
      setBusy(false);
    }
  };

  return (
    <div className="hh-bg">
      <header className="flex items-center justify-between px-4 py-4 border-b-2 border-black bg-[var(--hh-surface)]">
        <button onClick={() => nav("/")} className="flex items-center gap-2" data-testid="setup-back" aria-label={t("back_home")}>
          <ArrowLeft size={18} /> <Wordmark size="sm" />
        </button>
        <LangToggle />
      </header>
      <form onSubmit={create} className="max-w-xl mx-auto px-4 py-8 pb-40 flex flex-col gap-7">
        <div>
          <p className="hh-meta neon-pink" style={{ color: "var(--hh-pink)" }}>01 / {t("host_a_night")}</p>
          <h1 className="text-4xl sm:text-5xl font-extrabold leading-[1.02] mt-2">{t("setup_title")}</h1>
          <p className="text-[var(--hh-muted)] mt-2">{t("setup_sub")}</p>
        </div>

        <div className="hh-panel hh-spine p-5 flex flex-col gap-5">
          <Field label={t("stage_name")}>
            <input className="hh-input" maxLength={40} value={f.host_name} placeholder={t("stage_name_ph")} onChange={(e) => set("host_name", e.target.value)} data-testid="setup-stage-name" />
          </Field>
          <Field label={t("venue")}>
            <input className="hh-input" maxLength={60} value={f.venue_name} placeholder={t("venue_ph")} onChange={(e) => set("venue_name", e.target.value)} data-testid="setup-venue" />
          </Field>
        </div>

        <div>
          <span className="hh-meta block mb-2">{t("default_lang")}</span>
          <div className="grid grid-cols-2 gap-3">
            <ChoiceCard active={f.default_lang === "en"} onClick={() => set("default_lang", "en")} title={t("lang_en")} testid="setup-lang-en" />
            <ChoiceCard active={f.default_lang === "vi"} onClick={() => set("default_lang", "vi")} title={t("lang_vi")} testid="setup-lang-vi" />
          </div>
        </div>

        <DeckPicker selected={f.deck_id} onChange={id => set("deck_id", id)} />

        {!f.deck_id && <div>
          <span className="hh-meta block mb-2">{t("night_preset")}</span>
          <div className="grid gap-3">
            <ChoiceCard active={f.night_preset === "demo"} onClick={() => set("night_preset", "demo")} title={t("preset_demo")} desc={t("preset_demo_d")} testid="setup-preset-demo" accent="var(--hh-yellow)" />
            <ChoiceCard active={f.night_preset === "full"} onClick={() => set("night_preset", "full")} title={t("preset_full")} desc={t("preset_full_d")} testid="setup-preset-full" accent="var(--hh-yellow)" />
          </div>
        </div>}

        <ChoiceCard active={f.load_demo} onClick={() => set("load_demo", !f.load_demo)} title={<span className="flex items-center gap-2"><Users size={18} /> {t("load_demo")}</span>} desc={t("load_demo_d")} testid="setup-load-demo" accent="var(--hh-lime)" />

        <div className="fixed bottom-0 left-0 right-0 p-4 bg-[var(--hh-surface)] border-t-2 border-black z-20">
          <div className="max-w-xl mx-auto">
            <Btn type="submit" variant="pink" size="xl" className="w-full" disabled={busy} data-testid="host-create-room-button">
              {busy ? t("creating") : t("create_room")}
            </Btn>
          </div>
        </div>
      </form>
    </div>
  );
}
