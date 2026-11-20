"""Built-in moderation filter (Tiers 1-3). Returns (verdict, reason).
verdict: allow | flag | block
"""
import re

# Severe = never shown. Mild = waits for host.
SEVERE_EN = [
    "fuck", "fucking", "fucker", "motherfucker", "cunt", "nigger", "nigga", "faggot", "fag",
    "retard", "retarded", "whore", "slut", "rape", "rapist", "kys", "kill yourself", "nazi",
    "pussy", "cock", "dick", "blowjob", "porn", "chink", "spic", "tranny",
]
MILD_EN = [
    "shit", "bitch", "asshole", "bastard", "damn", "crap", "piss", "sexy", "sex", "boobs",
    "ugly", "fat", "stupid", "idiot", "loser", "wtf", "stfu", "die", "kill",
]
SEVERE_VI = [
    "địt", "đụ", "đéo", "lồn", "cặc", "buồi", "đĩ", "điếm", "chó đẻ", "đm", "đcm", "dcm", "vcl",
    "clm", "cmm", "dit", "djt", "du ma", "đù má", "đụ má", "địt mẹ", "dit me", "loz", "lìn",
]
MILD_VI = ["ngu", "óc chó", "oc cho", "khốn nạn", "mẹ mày", "me may", "vl", "cl", "dm", "béo", "xấu", "mập"]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?:\+?\d[\s.\-]?){9,}")
URL_RE = re.compile(r"(https?://|www\.)\S+|\b[\w-]+\.(com|net|org|vn|io|me|ly|co|info|xyz|tv|gg)\b", re.I)
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "@": "a", "$": "s", "5": "s", "7": "t"})


def _has(text: str, words) -> str:
    for w in words:
        if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text):
            return w
    return ""


def check_text(text: str):
    """Return (verdict, reason)."""
    if text is None:
        return "allow", ""
    raw = " ".join(str(text).lower().split())
    if not raw:
        return "allow", ""
    if EMAIL_RE.search(raw):
        return "block", "personal info: email"
    if PHONE_RE.search(raw):
        return "block", "personal info: phone number"
    leet = raw.translate(LEET)
    squashed = re.sub(r"[\s._\-*]+", "", leet)
    for t in (raw, leet):
        w = _has(t, SEVERE_EN) or _has(t, SEVERE_VI)
        if w:
            return "block", f"blocked word: {w}"
    for w in ("fuck", "cunt", "nigger", "faggot"):
        if w in squashed:
            return "block", f"blocked word: {w}"
    if URL_RE.search(raw):
        return "flag", "contains a link"
    for t in (raw, leet):
        w = _has(t, MILD_EN) or _has(t, MILD_VI)
        if w:
            return "flag", f"needs a look: {w}"
    return "allow", ""


def sexual_content(text: str) -> bool:
    """Conservative local EN/VI sexual-content gate; host review still required."""
    import unicodedata
    raw = unicodedata.normalize("NFC", str(text).casefold()).translate(LEET)
    plain = "".join(c for c in unicodedata.normalize("NFD", raw.replace("đ", "d")) if not unicodedata.combining(c))
    # Preserve Vietnamese tones on single words: buổi != buồi, lớn != lồn,
    # các != cặc, cụm != cum. Accent folding is safe only for multiword phrases.
    words = ["sex", "sexy", "sexual", "porn", "porno", "pornography", "blowjob", "handjob", "orgasm", "orgy", "penis", "vagina", "boobs", "boob", "cock", "dick", "pussy", "nude", "nudes", "naked", "horny", "erection", "masturbation", "masturbate", "semen", "anal", "cum", "địt", "đụ", "lồn", "cặc", "buồi", "that's what she said", "thats what she said", "netflix and chill", "size matters", "happy ending", "hard and wet"]
    phrases = ["tinh duc", "khieu dam", "khieu goi", "lam tinh", "duong vat", "am dao", "thu dam", "dit nhau", "dit me", "buoi to"]
    return bool(_has(raw, words) or _has(plain, phrases))
