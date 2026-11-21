import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { STRINGS, LINES } from "@/i18n";

const LangCtx = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem("hh_lang") || "en");
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const setLang = useCallback((l) => {
    localStorage.setItem("hh_lang", l);
    setLangState(l);
    document.documentElement.lang = l;
  }, []);
  const value = useMemo(() => makeApi(lang, setLang), [lang, setLang]);
  return React.createElement(LangCtx.Provider, { value }, children);
}

export function fmt(str, vars) {
  if (!vars) return str;
  return str.replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined && vars[k] !== null ? vars[k] : ""));
}

export function tr(lang, key, vars) {
  const e = STRINGS[key];
  if (!e) return key;
  return fmt(e[lang] || e.en, vars);
}

function makeApi(lang, setLang) {
  const other = lang === "en" ? "vi" : "en";
  return {
    lang,
    other,
    setLang,
    t: (key, vars) => tr(lang, key, vars),
    tIn: (l, key, vars) => tr(l, key, vars),
    pick: (obj, l = lang) => (obj ? obj[l] || obj.en || "" : ""),
    line: (kind, seed) => {
      const arr = LINES[kind] || [];
      if (!arr.length) return "";
      const i = seed === undefined ? Math.floor(Math.random() * arr.length) : Math.abs(seed) % arr.length;
      return arr[i][lang];
    },
  };
}

export function useLang() {
  return useContext(LangCtx);
}
