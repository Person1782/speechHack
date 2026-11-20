import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const http = axios.create({ baseURL: API, timeout: 8000 });

export function uid() {
  if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID().replace(/-/g, "");
  return Math.random().toString(36).slice(2) + Date.now().toString(36) + Math.random().toString(36).slice(2);
}

export function deviceId() {
  let d = localStorage.getItem("hh_device");
  if (!d) {
    d = uid();
    localStorage.setItem("hh_device", d);
  }
  return d;
}

export function getHostKey(code) {
  const params = new URLSearchParams(window.location.search);
  const k = params.get("key");
  if (k) {
    localStorage.setItem(`hh_host_${code}`, k);
    return k;
  }
  return localStorage.getItem(`hh_host_${code}`);
}

export function saveHostKey(code, key) {
  localStorage.setItem(`hh_host_${code}`, key);
}

// POST with retries; the same client_request_id is reused so retries are idempotent.
export async function postRetry(url, body = {}, { params, tries = 3 } = {}) {
  const payload = { client_request_id: uid(), ...body };
  let lastErr;
  for (let i = 0; i < tries; i++) {
    try {
      const { data } = await http.post(url, payload, { params });
      return data;
    } catch (e) {
      lastErr = e;
      const st = e.response && e.response.status;
      if (st && st < 500) throw e; // client errors: don't retry
      await new Promise((r) => setTimeout(r, 400 * (i + 1)));
    }
  }
  throw lastErr;
}

export function errCode(e) {
  return (e && e.response && e.response.data && e.response.data.detail) || "network";
}

export const CODE_RE = /^[A-HJ-NP-Z]{4}$/;
export function normCode(s) {
  return (s || "").toUpperCase().replace(/[^A-HJ-NP-Z]/g, "").slice(0, 4);
}
