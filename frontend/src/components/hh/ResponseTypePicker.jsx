import React from "react";
import { CircleDot, MessageSquareText } from "lucide-react";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { useLang } from "@/lib/lang";
import "./ResponseTypePicker.css";


// Keep in-progress choices while switching; persisted poll payloads omit them.
export const withResponseType = (question, response) => {
  const singleType = question.round_type !== "poll" ? question.round_type : question._singleType || "classic";
  return {
    ...question,
    _singleType: singleType,
    round_type: response === "open_ended" ? "poll" : singleType,
    options: question.options?.length === 4 ? question.options : Array.from({ length: 4 }, () => ({ en: "", vi: "" })),
  };
};

export const ResponseTypePicker = ({ value, onChange, id = "question-response", disabled = false }) => {
  const { t } = useLang();
  return <fieldset className="hh-response-fieldset" data-testid={`${id}-picker`}>
    <legend className="mb-3 text-sm font-semibold">{t("response_type_label")}</legend>
    <RadioGroup value={value === "poll" ? "open_ended" : "single_choice"} onValueChange={onChange} disabled={disabled} aria-label={t("response_type_label")} className="hh-response-picker" data-testid={`${id}-group`}>
      {[["single_choice", CircleDot], ["open_ended", MessageSquareText]].map(([mode, Icon]) => <Label key={mode} htmlFor={`${id}-${mode}`} className="hh-response-option" data-selected={(value === "poll") === (mode === "open_ended")} data-disabled={disabled}>
        <span className="flex items-center justify-between gap-3"><Icon size={20} strokeWidth={1.8} /><RadioGroupItem id={`${id}-${mode}`} value={mode} data-testid={`${id}-${mode.replaceAll("_", "-")}`} /></span>
        <span className="hh-response-title">{t(`response_${mode}`)}</span>
        <span className="hh-response-help">{t(`response_${mode}_help`)}</span>
      </Label>)}
    </RadioGroup>
    {value === "poll" && <p className="mt-3 text-sm leading-relaxed text-[var(--hh-muted)]" data-testid={`${id}-open-help`}>{t("response_open_ended_rules")}</p>}
  </fieldset>;
};
