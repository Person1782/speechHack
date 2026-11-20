import { useCallback, useEffect, useRef, useState } from "react";
import { http } from "@/lib/api";

/** Poll GET /rooms/{code}/state every 1500 ms with since_version. */
export function useRoomState(code, role, { hostKey, device, pauseWhenHidden = true, enabled = true } = {}) {
  const [state, setState] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ok | notfound | forbidden
  const [reconnecting, setReconnecting] = useState(false);
  const offset = useRef(0);
  const bestRtt = useRef(Infinity);
  const version = useRef(-1);
  const timer = useRef(null);
  const fails = useRef(0);
  const inflight = useRef(false);
  const stopped = useRef(false);
  const pollRef = useRef(null);

  const schedule = useCallback((ms) => {
    clearTimeout(timer.current);
    if (stopped.current) return;
    if (pauseWhenHidden && document.hidden) return; // resumes on visibilitychange
    timer.current = setTimeout(() => pollRef.current && pollRef.current(), ms);
  }, [pauseWhenHidden]);

  const poll = useCallback(async () => {
    if (inflight.current || stopped.current) return;
    inflight.current = true;
    clearTimeout(timer.current);
    const t0 = Date.now();
    try {
      const { data } = await http.get(`/rooms/${code}/state`, {
        params: { role, key: hostKey || undefined, device: device || undefined, since_version: version.current },
      });
      const t1 = Date.now();
      const rtt = t1 - t0;
      if (rtt <= bestRtt.current * 1.3 + 30) {
        bestRtt.current = Math.min(bestRtt.current, rtt);
        offset.current = data.server_now - (t0 + t1) / 2;
      }
      fails.current = 0;
      setReconnecting(false);
      if (!data.unchanged) {
        version.current = data.version;
        setState(data);
      }
      setStatus("ok");
      inflight.current = false;
      schedule(1500);
    } catch (e) {
      inflight.current = false;
      const st = e.response && e.response.status;
      if (st === 404) { setStatus("notfound"); stopped.current = true; return; }
      if (st === 403) { setStatus("forbidden"); stopped.current = true; return; }
      fails.current += 1;
      setReconnecting(true);
      schedule(Math.min(5000, 800 * 2 ** (fails.current - 1)));
    }
  }, [code, role, hostKey, device, schedule]);

  pollRef.current = poll;

  useEffect(() => {
    if (!enabled || !code) return undefined;
    stopped.current = false;
    version.current = -1;
    poll();
    const onVis = () => {
      if (!document.hidden) poll();
    };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("online", onVis);
    return () => {
      stopped.current = true;
      clearTimeout(timer.current);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("online", onVis);
    };
  }, [code, role, hostKey, device, enabled, poll]);

  const refresh = useCallback(() => { inflight.current = false; poll(); }, [poll]);
  const serverNow = useCallback(() => Date.now() + offset.current, []);
  return { state, status, reconnecting, refresh, serverNow };
}

/** Remaining ms on the server-controlled clock. */
export function useCountdown(state, serverNow) {
  const [now, setNow] = useState(() => serverNow());
  const ends = state && state.phase_ends_at;
  useEffect(() => {
    if (!ends) return undefined;
    const id = setInterval(() => setNow(serverNow()), 100);
    return () => clearInterval(id);
  }, [ends, serverNow]);
  if (!state) return { remaining: 0, fraction: 0, active: false };
  const limit = state.limit_ms || 20000;
  if (state.frozen && state.frozen_remaining_ms != null) {
    return { remaining: state.frozen_remaining_ms, fraction: state.frozen_remaining_ms / limit, active: true, frozen: true };
  }
  if (!ends) return { remaining: 0, fraction: 0, active: false };
  const remaining = Math.max(0, ends - now);
  return { remaining, fraction: Math.max(0, Math.min(1, remaining / limit)), active: true };
}

export function useWakeLock(enabled = true) {
  useEffect(() => {
    if (!enabled || !("wakeLock" in navigator)) return undefined;
    let lock = null;
    let cancelled = false;
    const req = async () => {
      try {
        if (document.visibilityState === "visible") lock = await navigator.wakeLock.request("screen");
      } catch (e) { /* not allowed: ignore */ }
    };
    req();
    const onVis = () => { if (!cancelled && document.visibilityState === "visible") req(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVis);
      if (lock) lock.release().catch(() => {});
    };
  }, [enabled]);
}

export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · Heckle & Hint` : "Heckle & Hint";
  }, [title]);
}

export function useRotating(len, ms = 6000) {
  const [i, setI] = useState(() => Math.floor(Math.random() * Math.max(1, len)));
  useEffect(() => {
    if (len <= 1) return undefined;
    const id = setInterval(() => setI((x) => (x + 1) % len), ms);
    return () => clearInterval(id);
  }, [len, ms]);
  return i;
}
