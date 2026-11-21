import React, { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2, Lock } from "lucide-react";
import { toast } from "sonner";
import { useLang } from "@/lib/lang";
import { http, postRetry, errCode } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogAction, AlertDialogCancel } from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from "@/components/ui/drawer";
import { Checkbox } from "@/components/ui/checkbox";
import { Newsroom } from "./Newsroom";
import { ResponseTypePicker, withResponseType } from "./ResponseTypePicker";
import { SaveRoomDeck } from "./DeckLibrary";

export const useSmallScreen = () => {
  const [small, setSmall] = useState(() => window.matchMedia("(max-width: 767px)").matches);
  useEffect(() => { const media = window.matchMedia("(max-width: 767px)"); const sync = () => setSmall(media.matches); media.addEventListener("change", sync); return () => media.removeEventListener("change", sync); }, []);
  return small;
};

export const T2Button = ({ tone = "cyan", className = "", children, ...props }) => <Button className={`hh-btn hh-${tone} !h-auto whitespace-normal ${className}`} {...props}>{children}</Button>;
export const Field = ({ label, id, multiline = false, ...props }) => <div className="grid gap-2 min-w-0"><Label htmlFor={id}>{label}</Label>{multiline ? <Textarea id={id} data-testid={id} className="hh-input resize-y" {...props} /> : <Input id={id} data-testid={id} className="hh-input" {...props} />}</div>;
export const t2Error = (e, t) => {
  const code = errCode(e);
  if (Array.isArray(code)) return code.some(x => String(x.msg).includes("content_blocked")) ? t("t2_content_blocked") : t("t2_validation");
  return t(`t2_${code}`) === `t2_${code}` ? t("error_generic") : t(`t2_${code}`);
};
const emptyQuestion = () => ({ round_type: "classic", text_en: "", text_vi: "", options: Array.from({ length: 4 }, () => ({ en: "", vi: "" })), correct_index: 0, setup_line: "", punchline: "", notes: { opener: "", follow_up: "", backup: "" }, hint_joke: "", fake_explanations: ["", ""], media_hint: "", time_limit_s: 20, explanation_en: "", explanation_vi: "" });

export const QuestionManager = ({ code, hostKey, refresh, version }) => {
  const { t, lang } = useLang();
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState("");
  const [editor, setEditor] = useState(null);
  const [editorError, setEditorError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [managerTab, setManagerTab] = useState("questions");
  const [newsRevision, setNewsRevision] = useState(0);
  const small = useSmallScreen();
  const EditorRoot = small ? Drawer : Dialog;
  const EditorContent = small ? DrawerContent : DialogContent;
  const EditorHeader = small ? DrawerHeader : DialogHeader;
  const EditorTitle = small ? DrawerTitle : DialogTitle;
  const EditorDescription = small ? DrawerDescription : DialogDescription;
  const selected = questions?.find(q => q.id === selectedId) || questions?.[0];
  const load = useCallback(async () => {
    try { const { data } = await http.get(`/rooms/${code}/questions`, { params: { key: hostKey } }); setQuestions(data.questions); setError(""); }
    catch (e) { setError(t2Error(e, t)); }
  }, [code, hostKey, t]);
  useEffect(() => { load(); }, [load, version]);
  const write = async (path, body = {}) => {
    setBusy(true);
    try { await postRetry(`/rooms/${code}/${path}`, body, { params: { key: hostKey } }); await load(); refresh(); return true; }
    catch (e) { const msg = t2Error(e, t); toast.error(msg); setEditorError(msg); return false; }
    finally { setBusy(false); }
  };
  const move = (i, delta) => { const ids = questions.map(q => q.id); [ids[i], ids[i + delta]] = [ids[i + delta], ids[i]]; write("question-order", { ids }); };
  const change = (key, value) => setEditor(e => ({ ...e, ...(e.draft_id && key !== "reviewed" ? { reviewed: false } : {}), [key]: value }));
  const openEditor = q => { setEditorError(""); setEditor(q ? JSON.parse(JSON.stringify(q)) : emptyQuestion()); };
  const openDraft = draft => { setEditorError(""); setEditor({ ...emptyQuestion(), ...draft.fields, draft_id: draft.id, sources: [draft.source], reviewed: false }); };
  const saveDraft = async () => {
    if (await write(`news/drafts/${editor.draft_id}/save`, editor)) { setNewsRevision(x => x + 1); setEditor(null); toast.success(t("t2_news_draft_saved")); }
  };
  const save = async e => {
    e.preventDefault();
    const payload = { ...editor, options: editor.round_type === "poll" ? [] : editor.options, correct_index: editor.round_type === "poll" ? null : editor.correct_index };
    const path = editor.draft_id ? `news/drafts/${editor.draft_id}/publish` : editor.id ? `questions/${editor.id}` : "questions";
    if (await write(path, payload)) { setEditor(null); setNewsRevision(x => x + 1); toast.success(t(editor.draft_id ? "t2_news_published" : "t2_saved")); }
  };
  return <section className="hh-panel p-4 space-y-4 min-w-0" data-testid="question-manager">
    <div className="flex flex-wrap justify-between gap-3 items-center"><div><h2 className="text-xl font-extrabold" data-testid="question-manager-title">{t("t2_question_manager")}</h2><p className="text-sm text-[var(--hh-muted)] mt-1">{t("t2_manager_help")}</p></div><T2Button onClick={() => openEditor()} data-testid="question-manager-add-button"><Plus />{t("t2_add_question")}</T2Button></div>
    <div className="flex flex-wrap gap-3"><SaveRoomDeck code={code} hostKey={hostKey} /></div>
    <Tabs value={managerTab} onValueChange={setManagerTab}><TabsList className="grid grid-cols-2 h-auto max-w-md"><TabsTrigger value="questions" data-testid="manager-questions-tab">{t("t2_questions_tab")}</TabsTrigger><TabsTrigger value="news" data-testid="manager-news-tab">{t("t2_news_tab")}</TabsTrigger></TabsList></Tabs>
    {managerTab === "news" ? <Newsroom code={code} hostKey={hostKey} revision={newsRevision} onOpenDraft={openDraft} /> : <>
    {error && <div role="alert" data-testid="question-manager-error" className="text-[var(--hh-yellow)]"><p>{error}</p><T2Button onClick={load} data-testid="question-manager-retry">{t("t2_retry")}</T2Button></div>}
    {!questions && !error && <Skeleton className="h-32 w-full" data-testid="question-manager-loading" />}
    {questions && <div className="grid xl:grid-cols-[minmax(0,1fr)_320px] gap-6 min-w-0">
      <ol className="hh-question-list min-w-0" data-testid="question-manager-list">{questions.map((q, i) => <li key={q.id} className={`hh-question-row ${selected?.id === q.id ? "is-selected" : ""}`} data-testid={`question-row-${i}`}>
        <span className="hh-question-index">{String(i + 1).padStart(2, "0")}</span>
        <Button variant="ghost" className="h-auto whitespace-normal text-left justify-start p-0 hover:bg-transparent min-w-0 font-semibold" data-testid={`question-select-${i}`} onClick={() => small && q.editable ? openEditor(q) : setSelectedId(q.id)}><span className="min-w-0"><span className="line-clamp-2 break-words" data-testid={`question-text-${i}`}>{q[`text_${lang}`] || q.text_en}</span><span className="hh-row-meta">{t(`t2_type_${q.round_type}`)} · {q.time_limit_s} {t("t2_seconds")}{!q.editable && ` · ${t("t2_in_play")}`}</span></span></Button>
        <div className="hh-row-actions">
          <T2Button tone="ghost" disabled={busy || !q.editable || i === 0 || !questions[i - 1]?.editable} onClick={() => move(i, -1)} aria-label={t("t2_move_up")} data-testid={`question-up-${i}`}><ArrowUp /></T2Button>
          <T2Button tone="ghost" disabled={busy || !q.editable || i === questions.length - 1} onClick={() => move(i, 1)} aria-label={t("t2_move_down")} data-testid={`question-down-${i}`}><ArrowDown /></T2Button>
          <T2Button tone="ghost" disabled={busy || !q.editable} onClick={() => openEditor(q)} aria-label={t("t2_edit")} data-testid={`question-edit-${i}`}>{q.editable ? <Pencil /> : <Lock />}</T2Button>
          <T2Button tone="ghost" disabled={busy || !q.editable || questions.length === 1} onClick={() => setDeleting(q)} aria-label={t("t2_delete")} data-testid={`question-delete-${i}`}><Trash2 /></T2Button>
        </div>
      </li>)}</ol>
      {selected && <aside className="hidden xl:block min-w-0" data-testid="question-inspector"><div className="sticky top-28 space-y-5 border-l border-[var(--hh-line)] pl-6"><span className="hh-meta">{t("t2_preview")}</span><span className="block hh-row-meta">{t(`t2_type_${selected.round_type}`)}</span><h3 className="text-2xl font-semibold tracking-tight leading-snug break-words" data-testid="question-preview-text">{selected[`text_${lang}`] || selected.text_en}</h3><div className="grid gap-2">{selected.options.map((o, i) => <p key={i} className={`text-sm border-b border-[var(--hh-line)] py-3 break-words ${i === selected.correct_index ? "text-[var(--hh-cyan)]" : "text-[var(--hh-muted)]"}`}><span className="mr-3">{String.fromCharCode(65 + i)}</span>{o[lang] || o.en}</p>)}</div><p className="text-sm text-[var(--hh-muted)] break-words">{selected.setup_line}</p><T2Button tone="ghost" disabled={!selected.editable} onClick={() => openEditor(selected)} data-testid="question-preview-edit"><Pencil />{t("t2_edit_question")}</T2Button></div></aside>}
    </div>}
    </>}
    <EditorRoot open={!!editor} onOpenChange={o => !o && !busy && setEditor(null)} {...(small ? { shouldScaleBackground: false } : {})}><EditorContent className={`hh-editor ${small ? "h-[92dvh] max-h-[92dvh]" : "!w-[92vw] !max-w-2xl max-h-[90dvh] overflow-y-auto p-6"}`} data-testid="question-editor">
      <EditorHeader className="text-left"><EditorTitle>{t(editor?.id ? "t2_edit_question" : "t2_add_question")}</EditorTitle><EditorDescription>{t("t2_translation_help")}</EditorDescription></EditorHeader>
      {editor && <form onSubmit={save} className={`grid gap-5 min-h-0 ${small ? "overflow-y-auto px-4 pb-6" : ""}`}>
        {editor.sources?.length > 0 && <div className="border-l-2 border-[var(--hh-cyan)] pl-3 space-y-2" data-testid="editor-source-references"><span className="hh-meta">{t("t2_news_source_notes")}</span>{editor.sources.map((source, i) => <div key={i} className="space-y-2"><a className="text-sm underline underline-offset-4 break-words" href={source.url} target="_blank" rel="noreferrer noopener" data-testid={`editor-source-link-${i}`}>{source.title}</a>{editor.draft_id && <p className="text-xs text-[var(--hh-muted)] break-words">{source.description || source.excerpts?.[0]}</p>}</div>)}</div>}
        <ResponseTypePicker value={editor.round_type} onChange={mode => setEditor(current => ({ ...withResponseType(current, mode), ...(current.draft_id ? { reviewed: false } : {}) }))} />
        {editor.round_type !== "poll" && !editor.draft_id && <div className="grid gap-2"><Label>{t("response_single_style")}</Label><Select value={editor.round_type} onValueChange={v => change("round_type", v)}><SelectTrigger data-testid="question-type-select" className="hh-input" aria-label={t("response_single_style")}><SelectValue /></SelectTrigger><SelectContent>{["classic", "decoy", "caption"].map(x => <SelectItem key={x} value={x} data-testid={`question-type-${x}`}>{t(`t2_type_${x}`)}</SelectItem>)}</SelectContent></Select></div>}
        <Tabs defaultValue="core"><TabsList className="grid grid-cols-3 h-auto"><TabsTrigger value="core" data-testid="editor-core-tab">{t("t2_core")}</TabsTrigger><TabsTrigger value="notes" data-testid="editor-notes-tab">{t("notes_label")}</TabsTrigger><TabsTrigger value="timing" data-testid="editor-timing-tab">{t("t2_timing")}</TabsTrigger></TabsList>
          <TabsContent value="core" className="space-y-4 pt-3">
            {["en", "vi"].map(l => <Field key={l} id={`question-text-${l}`} label={`${t("t2_question_text")} · ${l.toUpperCase()}`} multiline maxLength={500} required={l === "en"} value={editor[`text_${l}`]} onChange={e => change(`text_${l}`, e.target.value)} />)}
            {editor.round_type !== "poll" && <><div className="grid gap-3">{editor.options.map((o, i) => <div key={i} className="grid sm:grid-cols-2 gap-3 hh-panel p-3">{["en", "vi"].map(l => <Field key={l} id={`question-option-${i}-${l}`} label={`${String.fromCharCode(65 + i)} · ${l.toUpperCase()}`} value={o[l]} maxLength={160} required={l === "en"} onChange={e => change("options", editor.options.map((x, j) => i === j ? { ...x, [l]: e.target.value } : x))} />)}</div>)}</div>
            <div className="grid gap-2"><Label>{t("correct_answer")}</Label><Select value={editor.correct_index == null ? "" : String(editor.correct_index)} onValueChange={v => change("correct_index", Number(v))}><SelectTrigger className="hh-input" data-testid="question-correct-select"><SelectValue placeholder={t("t2_news_choose_correct")} /></SelectTrigger><SelectContent>{[0, 1, 2, 3].map(i => <SelectItem key={i} value={String(i)} data-testid={`question-correct-${i}`}>{String.fromCharCode(65 + i)}</SelectItem>)}</SelectContent></Select></div></>}
          </TabsContent>
          <TabsContent value="notes" className="space-y-4 pt-3">
            {["setup_line", "punchline", "hint_joke"].map(k => <Field key={k} id={`question-${k}`} label={t(`t2_${k}`)} multiline maxLength={600} value={editor[k]} onChange={e => change(k, e.target.value)} />)}
            {["opener", "follow_up", "backup"].map(k => <Field key={k} id={`question-note-${k}`} label={t(`note_${k}`)} multiline maxLength={600} value={editor.notes[k]} onChange={e => change("notes", { ...editor.notes, [k]: e.target.value })} />)}
            {[0, 1].map(i => <Field key={i} id={`question-fake-${i}`} label={`${t("t2_fake_explanation")} ${i + 1}`} multiline maxLength={600} value={editor.fake_explanations[i] || ""} onChange={e => { const fakes = [...editor.fake_explanations]; fakes[i] = e.target.value; change("fake_explanations", fakes); }} />)}
            {["en", "vi"].map(l => <Field key={l} id={`question-explanation-${l}`} label={`${t("t2_explanation")} · ${l.toUpperCase()}`} multiline maxLength={600} value={editor[`explanation_${l}`]} onChange={e => change(`explanation_${l}`, e.target.value)} />)}
          </TabsContent>
          <TabsContent value="timing" className="space-y-4 pt-3"><Field id="question-emoji-scene" label={t("t2_emoji_scene")} maxLength={100} value={editor.media_hint} onChange={e => change("media_hint", e.target.value)} /><Field id="question-time-limit" label={t("t2_time_limit")} type="number" min={5} max={180} value={editor.time_limit_s} onChange={e => change("time_limit_s", Number(e.target.value))} /></TabsContent>
        </Tabs>
        {editorError && <p role="alert" className="text-[var(--hh-yellow)]" data-testid="question-editor-error">{editorError}</p>}
        {editor.draft_id && <div className="flex gap-3 items-start border-t border-[var(--hh-line)] pt-4"><Checkbox id="newsroom-reviewed" data-testid="newsroom-reviewed-checkbox" checked={editor.reviewed} onCheckedChange={value => change("reviewed", !!value)} /><Label htmlFor="newsroom-reviewed" className="leading-relaxed">{t(editor.round_type === "poll" ? "response_news_review_open" : "t2_news_review_check")}</Label></div>}
        <div className={`sticky bottom-0 bg-[var(--hh-bg)] pt-3 grid ${editor.draft_id ? "grid-cols-2" : "grid-cols-2"} gap-3`}><T2Button tone="ghost" type="button" disabled={busy} onClick={() => setEditor(null)} data-testid="question-editor-cancel">{t("cancel")}</T2Button>{editor.draft_id && <T2Button tone="ghost" type="button" disabled={busy} onClick={saveDraft} data-testid="newsroom-save-draft-button">{t("t2_news_save_draft")}</T2Button>}<T2Button tone="pink" type="submit" className={editor.draft_id ? "col-span-2" : ""} disabled={busy || (!!editor.draft_id && (!editor.reviewed || (editor.round_type !== "poll" && editor.correct_index == null)))} data-testid="question-manager-save-button">{t(busy ? "t2_saving" : editor.draft_id ? "t2_news_publish" : "t2_save")}</T2Button></div>
      </form>}
    </EditorContent></EditorRoot>
    <AlertDialog open={!!deleting} onOpenChange={o => !o && setDeleting(null)}><AlertDialogContent className="max-w-[92vw] sm:max-w-lg" data-testid="question-delete-dialog"><AlertDialogHeader><AlertDialogTitle>{t("t2_delete_question")}</AlertDialogTitle><AlertDialogDescription>{t("t2_delete_help")}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel data-testid="question-delete-cancel">{t("cancel")}</AlertDialogCancel><AlertDialogAction className="hh-btn hh-red" data-testid="question-delete-confirm" onClick={async () => { const q = deleting; setDeleting(null); await write(`questions/${q.id}/delete`); }}>{t("t2_delete")}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </section>;
};
