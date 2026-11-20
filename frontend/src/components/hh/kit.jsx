import React from "react";
import { useLang } from "@/lib/lang";
import { WifiOff } from "lucide-react";

export const ANSWER = [
  { color: "#656576", shape: "a", key: "a" },
  { color: "#656576", shape: "b", key: "b" },
  { color: "#656576", shape: "c", key: "c" },
  { color: "#656576", shape: "d", key: "d" },
];

export const Btn = React.forwardRef(function Btn({ variant = "pink", size = "md", className = "", children, ...rest }, ref) {
  return (
    <button ref={ref} className={`hh-btn hh-${variant} hh-size-${size} ${className}`} {...rest}>
      {children}
    </button>
  );
});

// Lettered cue cards stay readable without relying on colour or game-show shapes.
export function Shape({ shape, size = 28, className = "" }) {
  const letter = ({triangle:'A',diamond:'B',circle:'C',square:'D'})[shape] || String(shape || '').toUpperCase();
  return <span className={`hh-answer-letter ${className}`} style={{width:size+10,height:size+10,fontSize:Math.max(14,size*.55)}} aria-hidden="true">{letter}</span>;
}

export function LangToggle({ className = "", onChange }) {
  const { lang, setLang } = useLang();
  return (
    <div className={`hh-lang ${className}`} data-testid="language-toggle" role="group" aria-label="Language">
      {["vi", "en"].map((l) => (
        <button
          key={l}
          type="button"
          data-testid={`language-toggle-${l}`}
          className={lang === l ? "on" : ""}
          aria-pressed={lang === l}
          onClick={() => { setLang(l); onChange && onChange(l); }}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function ReconnectBadge({ show }) {
  const { t } = useLang();
  if (!show) return null;
  return (
    <div className="hh-reconnect" data-testid="reconnect-badge" role="status">
      <WifiOff size={14} /> {t("reconnecting")}
    </div>
  );
}

export function Wordmark({ size = "md", className = "" }) {
  return (
    <div className={`hh-wordmark hh-wm-${size} ${className}`} aria-label="Heckle & Hint">
      <span className="wm-a">HECKLE</span>
      <span className="wm-amp">&amp;</span>
      <span className="wm-b">HINT</span>
    </div>
  );
}

export function TimerBar({ fraction, frozen, className = "", testid = "countdown-bar" }) {
  const low = fraction < 0.25;
  return (
    <div className={`hh-timerbar ${className}`} data-testid={testid}>
      <div
        className={`fill ${low ? "low" : ""} ${frozen ? "frozen" : ""}`}
        style={{ transform: `scaleX(${Math.max(0, Math.min(1, fraction))})` }}
      />
    </div>
  );
}

export function teamLabel(team, t) {
  if (!team) return "";
  return team.name || t("team_n", { n: team.number });
}

export function Stamp({ children, color = "#FFE14D", className = "", rotate = -4 }) {
  return (
    <span className={`hh-stamp ${className}`} style={{ borderColor: color, color, transform: `rotate(${rotate}deg)` }}>
      {children}
    </span>
  );
}

export function Marquee({ items, testid = "ticker" }) {
  if (!items || !items.length) return null;
  const doubled = [...items, ...items];
  const dur = Math.max(20, items.join(" ").length * 0.22);
  return (
    <div className="hh-marquee" data-testid={testid}>
      <div className="track" style={{ animationDuration: `${dur}s` }}>
        {doubled.map((x, i) => (
          <span key={i} className="item">{x}<span className="sep">✶</span></span>
        ))}
      </div>
    </div>
  );
}

export function FullCenter({ children, className = "" }) {
  return <div className={`min-h-dvh flex flex-col items-center justify-center p-6 ${className}`}>{children}</div>;
}

export function LoadingStage() {
  const { t } = useLang();
  return (
    <FullCenter>
      <div className="hh-loader" aria-hidden="true"><span /><span /><span /></div>
      <p className="mt-6 hh-meta" data-testid="loading">{t("loading")}</p>
    </FullCenter>
  );
}

export function fmtSec(ms) {
  return Math.ceil(Math.max(0, ms) / 1000);
}

export function reducedMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
