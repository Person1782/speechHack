import React, { useCallback, useEffect, useState } from "react";
import { ExternalLink, FilePlus2, Newspaper, Search, Trash2 } from "lucide-react";
import { useLang } from "@/lib/lang";
import { http, uid, errCode } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogAction, AlertDialogCancel } from "@/components/ui/alert-dialog";

const Action = ({ children, primary = false, ...props }) => <Button className={`hh-btn ${primary ? "hh-cyan" : "hh-ghost"} !h-auto whitespace-normal`} {...props}>{children}</Button>;

export const Newsroom = ({ code, hostKey, onOpenDraft, revision = 0 }) => {
  const { t, lang } = useLang();
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const message = useCallback(e => { const key = `t2_${errCode(e)}`; return t(key) === key ? t("error_generic") : t(key); }, [t]);
  const load = useCallback(async () => {
    try {
      const r = await http.get(`/rooms/${code}/news`, { params: { key: hostKey } });
      setData(r.data); setSearch(r.data.latest_search); setError("");
    } catch (e) { setError(message(e)); }
  }, [code, hostKey, message]);
  useEffect(() => { load(); }, [load, revision]);
  const performSearch = async e => {
    e?.preventDefault(); setBusy(true); setError("");
    try { const r = await http.post(`/rooms/${code}/news/search`, { query, language: lang.toUpperCase(), client_request_id: uid() }, { params: { key: hostKey }, timeout: 30000 }); setSearch(r.data); setSelected(r.data.results[0] || null); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  };
  const draft = async source => {
    setBusy(true);
    try { const r = await http.post(`/rooms/${code}/news/drafts`, { source_id: source.id, client_request_id: uid() }, { params: { key: hostKey } }); if (r.data.status === "published") { toast.info(t("t2_news_already_published")); return; } await load(); onOpenDraft(r.data); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  };
  const remove = async id => {
    setBusy(true);
    try { await http.post(`/rooms/${code}/news/drafts/${id}/delete`, {}, { params: { key: hostKey } }); await load(); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  };
  const date = value => { const d = new Date(value); return value && !Number.isNaN(d.valueOf()) ? d.toLocaleDateString(lang === "vi" ? "vi-VN" : "en-GB", { day: "numeric", month: "short", year: "numeric" }) : t("t2_news_date_unknown"); };
  const results = search?.results || [];
  const current = selected && results.find(x => x.id === selected.id) || results[0];
  return <section className="space-y-5 min-w-0" data-testid="newsroom">
    <div className="flex gap-3 items-start"><Newspaper className="mt-1 shrink-0 text-[var(--hh-cyan)]" size={20} /><div><h3 className="text-lg font-semibold">{t("t2_news_title")}</h3><p className="mt-1 text-sm text-[var(--hh-muted)] leading-relaxed">{t("t2_news_help")}</p></div><span className="hh-meta ml-auto shrink-0">You.com</span></div>
    {!data && !error && <Skeleton className="h-32" data-testid="newsroom-loading" />}
    {data && !data.available && <Alert data-testid="newsroom-unavailable"><AlertDescription>{t("t2_news_not_configured")}</AlertDescription></Alert>}
    <form onSubmit={performSearch} className="grid sm:grid-cols-[minmax(0,1fr)_auto] gap-3" data-testid="newsroom-command-strip"><Input value={query} onChange={e => setQuery(e.target.value)} maxLength={180} minLength={2} required className="hh-input" placeholder={t("t2_news_query_placeholder")} aria-label={t("t2_news_query_label")} data-testid="newsroom-query-input" /><Action primary type="submit" disabled={!data?.available || busy || query.trim().length < 2} data-testid="newsroom-search-button"><Search size={16} />{t(busy ? "t2_news_searching" : "t2_news_search")}</Action></form>
    <div className="flex flex-wrap gap-4 justify-between text-xs text-[var(--hh-muted)]"><span data-testid="newsroom-freshness-chip">{t("t2_news_last_week")}</span><span data-testid="newsroom-research-notice">{t("t2_news_verify")}</span></div>
    {error && <Alert data-testid="newsroom-error"><AlertDescription>{error}</AlertDescription><Action disabled={busy} onClick={data ? performSearch : load} data-testid="newsroom-retry">{t("t2_retry")}</Action></Alert>}
    {busy && <div className="grid gap-3" data-testid="newsroom-search-loading">{[0, 1, 2].map(i => <Skeleton key={i} className="h-20" />)}</div>}
    {!busy && search && <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)] gap-5 min-w-0">
      <div className="min-w-0" data-testid="newsroom-results-list">{results.length === 0 && <p className="py-6 text-sm text-[var(--hh-muted)]" data-testid="newsroom-empty">{t("t2_news_empty")}</p>}{results.map((source, i) => <article key={source.id} className={`py-4 border-b border-[var(--hh-line)] min-w-0 ${current?.id === source.id ? "border-l-2 border-l-[var(--hh-cyan)] pl-3" : ""}`} data-testid={`newsroom-result-${i}`}>
        <Button variant="ghost" className="p-0 h-auto text-left justify-start font-semibold whitespace-normal hover:bg-transparent min-w-0 w-full" data-testid={`newsroom-result-select-${i}`} onClick={() => setSelected(source)}><span className="break-words min-w-0">{source.title}</span></Button>
        <p className="text-xs text-[var(--hh-muted)] mt-2 break-words" data-testid={`newsroom-source-date-${i}`}>{new URL(source.url).hostname} · {date(source.published_at)}</p>
        <p className="text-sm text-[var(--hh-muted)] leading-relaxed line-clamp-2 mt-2">{source.description || source.excerpts[0]}</p>
        <div className="flex flex-wrap gap-2 mt-3"><Action disabled={busy} onClick={() => draft(source)} data-testid={`newsroom-create-draft-${i}`}><FilePlus2 size={15} />{t("t2_news_create_draft")}</Action><Action asChild><a href={source.url} target="_blank" rel="noreferrer noopener" data-testid={`newsroom-source-link-${i}`}><ExternalLink size={15} />{t("t2_news_open_source")}</a></Action></div>
      </article>)}</div>
      {current && <aside className="hidden lg:block border-l border-[var(--hh-line)] pl-5 min-w-0" data-testid="newsroom-inspector"><span className="hh-meta">{t("t2_news_source_notes")}</span><h4 className="mt-3 font-semibold break-words">{current.title}</h4><div className="space-y-4 mt-4 text-sm text-[var(--hh-muted)] leading-relaxed">{(current.excerpts.length ? current.excerpts : [current.description]).map((text, i) => <p key={i} className="break-words" data-testid={`newsroom-excerpt-${i}`}>{text}</p>)}</div></aside>}
    </div>}
    <div className="border-t border-[var(--hh-line)] pt-5" data-testid="newsroom-drafts"><h3 className="text-base font-semibold mb-3">{t("t2_news_drafts")} <span className="text-[var(--hh-muted)]">{data?.drafts.length || 0}</span></h3>{data?.drafts.length ? <ol className="divide-y divide-[var(--hh-line)]">{data.drafts.map((d, i) => <li key={d.id} className="py-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3" data-testid={`newsroom-draft-${i}`}><Button variant="ghost" className="p-0 h-auto min-h-11 justify-start text-left whitespace-normal hover:bg-transparent" onClick={() => onOpenDraft(d)} data-testid={`newsroom-edit-draft-${i}`}><span className="min-w-0"><span className="block font-medium break-words">{d.fields[`text_${lang}`] || d.fields.text_en || d.source.title}</span><span className="hh-row-meta">{t("t2_news_unpublished")} · {date(d.updated_at)}</span></span></Button><Action disabled={busy} onClick={() => setDeleting(d.id)} aria-label={t("t2_delete")} data-testid={`newsroom-delete-draft-${i}`}><Trash2 size={16} /></Action></li>)}</ol> : <p className="text-sm text-[var(--hh-muted)]" data-testid="newsroom-drafts-empty">{t("t2_news_no_drafts")}</p>}</div>
    <AlertDialog open={!!deleting} onOpenChange={open => !open && setDeleting(null)}><AlertDialogContent className="max-w-[92vw] sm:max-w-lg"><AlertDialogHeader><AlertDialogTitle>{t("t2_news_delete_title")}</AlertDialogTitle><AlertDialogDescription>{t("t2_news_delete_help")}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel data-testid="newsroom-delete-cancel">{t("cancel")}</AlertDialogCancel><AlertDialogAction className="hh-btn hh-cyan" data-testid="newsroom-delete-confirm" onClick={() => { const id = deleting; setDeleting(null); remove(id); }}>{t("t2_delete")}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </section>;
};
