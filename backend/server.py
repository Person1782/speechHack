import asyncio
import copy
import hashlib
import logging
import os
import random
import secrets
import time
import uuid
import sys
from tier2 import Tier2, POLL_PHASES, SOUNDS, PRESETS, QuestionInput
from news import NewsService
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import APIRouter, Body, FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware

import seed_data as SD
from game import (ANSWER_GRACE_MS, MAX_TEAMS, after_reveal_step, build_round_plan, calc_points,
                  flatten_plan, gen_code, is_fast_wrong, rank_teams, recompute_scores, sim_choice)
from moderation import check_text

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
logger = logging.getLogger("heckle")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

ROOM_TTL = timedelta(hours=48)
QUESTION_PHASES = ("question_open", "question_locked", "reveal")


def _ttl():
    return IndexModel([("expire_at", ASCENDING)], name="ttl", expireAfterSeconds=0)


INDEXES: dict = {
    # Private reusable material outlives individual rooms; no player data is stored here.
    "decks": [IndexModel([("id", ASCENDING)], name="id", unique=True),
              IndexModel([("owner_hash", ASCENDING), ("create_request_id", ASCENDING)], name="owner_request", unique=True)],
    "rooms": [IndexModel([("code", ASCENDING)], name="code", unique=True), _ttl(),
              IndexModel([("phase", ASCENDING)], name="phase")],
    "questions": [IndexModel([("id", ASCENDING)], name="id", unique=True),
                  IndexModel([("room_code", ASCENDING), ("index", ASCENDING)], name="room_index"), _ttl()],
    "teams": [IndexModel([("id", ASCENDING)], name="id", unique=True),
              IndexModel([("room_code", ASCENDING), ("device_id", ASCENDING)], name="room_device", unique=True),
              IndexModel([("room_code", ASCENDING), ("number", ASCENDING)], name="room_number"), _ttl()],
    "answers": [IndexModel([("question_id", ASCENDING), ("team_id", ASCENDING)], name="q_team", unique=True),
                IndexModel([("room_code", ASCENDING), ("client_request_id", ASCENDING)], name="room_crid", unique=True),
                _ttl()],
    "events": [IndexModel([("room_code", ASCENDING), ("at", DESCENDING)], name="room_at"), _ttl()],
    "decision_log": [IndexModel([("room_code", ASCENDING), ("at", DESCENDING)], name="room_at"), _ttl()],
    "requests": [IndexModel([("room_code", ASCENDING), ("crid", ASCENDING)], name="room_crid", unique=True), _ttl()],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


def now_ms() -> int:
    return int(time.time() * 1000)


def clean(doc):
    if isinstance(doc, dict):
        return {k: clean(v) for k, v in doc.items() if k != "_id"}
    if isinstance(doc, list):
        return [clean(v) for v in doc]
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc


app = FastAPI(title="Heckle & Hint")
api = APIRouter(prefix="/api")


# ------------------------------------------------------------------ helpers
async def get_room(code: str) -> dict:
    room = await db.rooms.find_one({"code": (code or "").upper()}, {"_id": 0})
    if not room:
        raise HTTPException(404, "room_not_found")
    return room


def require_host(room: dict, key: Optional[str]):
    if not key or not secrets.compare_digest(str(key), room["host_key"]):
        raise HTTPException(403, "host_key_required")


async def bump(code: str, set_fields: Optional[dict] = None, cond: Optional[dict] = None, extra: Optional[dict] = None) -> bool:
    update: Dict[str, Any] = {"$inc": {"version": 1}}
    if set_fields:
        update["$set"] = set_fields
    if extra:
        update.update(extra)
    res = await db.rooms.update_one({"code": code, **(cond or {})}, update)
    return res.modified_count > 0


async def log_decision(room: dict, item_ref: str, item_text: str, verdict: str, reason: str, actor: str):
    await db.decision_log.insert_one({
        "room_code": room["code"], "at": now_ms(), "item_ref": item_ref, "item_text": item_text,
        "verdict": verdict, "reason": reason, "actor": actor, "expire_at": room["expire_at"]})


async def add_event(room: dict, etype: str, payload: dict):
    await db.events.insert_one({"id": uuid.uuid4().hex[:10], "room_code": room["code"], "type": etype,
                                "payload": payload, "at": now_ms(), "expire_at": room["expire_at"]})


async def claim_request(room: dict, crid: Optional[str]) -> bool:
    """Returns False if this client_request_id was already processed (idempotent retry)."""
    if not crid:
        return True
    try:
        await db.requests.insert_one({"room_code": room["code"], "crid": crid, "at": now_ms(), "expire_at": room["expire_at"]})
        return True
    except DuplicateKeyError:
        return False


def team_display(t: dict, blackout: bool) -> Optional[str]:
    if blackout or t.get("name_status") != "shown":
        return None
    return t["name"]


def team_public(t: dict, blackout: bool = False) -> dict:
    return {"id": t["id"], "number": t["number"], "name": team_display(t, blackout), "emoji": t["emoji"],
            "color": t["color"], "brain_points": t.get("brain_points", 0), "laugh_points": t.get("laugh_points", 0),
            "total": t.get("brain_points", 0) + t.get("laugh_points", 0), "streak": t.get("streak", 0)}


def q_public(q: dict) -> dict:
    return {"id": q["id"], "round_type": q["round_type"], "text_en": q["text_en"], "text_vi": q["text_vi"],
            "options": q["options"], "media_hint": q.get("media_hint", ""), "time_limit_s": q.get("time_limit_s", 20)}


def current_entry(room: dict):
    qi = room.get("question_index", -1)
    flat = room.get("flat", [])
    return flat[qi] if 0 <= qi < len(flat) else None


def next_action(room: dict) -> str:
    phase = room["phase"]
    flat = room.get("flat", [])
    if phase in POLL_PHASES:
        return {"poll_open": "poll_lock", "poll_review": "poll_vote", "poll_vote": "poll_finish", "poll_hof": "poll_resume"}[phase]
    if phase == "lobby":
        return "start_show"
    if phase == "cold_open":
        return "start_round"
    if phase == "round_intro":
        return "open_question"
    if phase == "question_open":
        return "lock"
    if phase == "question_locked":
        return "reveal"
    if phase == "reveal":
        kind, _ = after_reveal_step(flat, room["question_index"], room["settings"]["night_preset"])
        return "show_scoreboard" if kind == "scoreboard" else "next_question"
    if phase == "scoreboard":
        pd = room.get("phase_data") or {}
        if pd.get("round_end"):
            return "final_results" if pd.get("final") else "next_round"
        return "next_question"
    return "none"


# ------------------------------------------------------------------ models
class CreateRoom(BaseModel):
    host_name: str = ""
    venue_name: str = ""
    default_lang: str = "en"
    follow_links: Dict[str, str] = {}
    bar_reward_text: str = "10% off your next round"
    roast_enabled: bool = True
    chaos_enabled: bool = True
    sound_on: bool = True
    night_preset: str = "demo"
    load_demo: bool = False
    deck_id: Optional[str] = None
    owner_key: Optional[str] = None


class DeckIdentity(BaseModel):
    owner_key: str = Field(min_length=16, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    client_request_id: str = Field(min_length=8, max_length=100)

    @field_validator("name", "description", mode="before")
    @classmethod
    def trim_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


class DeckInput(DeckIdentity):
    questions: list[QuestionInput] = Field(min_length=1, max_length=100)


def library_owner(key: Optional[str]) -> str:
    if not isinstance(key, str) or not 16 <= len(key) <= 100:
        raise HTTPException(403, "deck_key_required")
    return hashlib.sha256(key.encode()).hexdigest()


def deck_public(deck: dict) -> dict:
    return {k: copy.deepcopy(deck[k]) for k in ("id", "name", "description", "questions", "created_at", "updated_at")}


async def owned_deck(deck_id: str, key: Optional[str]) -> dict:
    deck = await db.decks.find_one({"id": deck_id, "owner_hash": library_owner(key)}, {"_id": 0})
    if not deck:
        raise HTTPException(404, "deck_not_found")
    return deck


def deck_questions(questions: list[QuestionInput]) -> list:
    result = []
    for index, q in enumerate(questions):
        item = q.model_dump(exclude={"client_request_id"})
        item["id"] = uuid.uuid4().hex
        item["index"] = index
        item["text_en"] = item["text_en"].strip()
        item["text_vi"] = item["text_vi"].strip() or item["text_en"]
        for option in item["options"]:
            option["en"] = option["en"].strip()
            option["vi"] = option["vi"].strip() or option["en"]
        item["custom_time"] = True
        result.append(item)
    return result


async def save_new_deck(body: DeckInput) -> dict:
    owner = library_owner(body.owner_key)
    existing = await db.decks.find_one({"owner_hash": owner, "create_request_id": body.client_request_id}, {"_id": 0})
    if existing:
        return existing
    stamp = now_ms()
    deck = {"id": uuid.uuid4().hex, "owner_hash": owner, "name": body.name, "description": body.description,
            "questions": deck_questions(body.questions), "created_at": stamp, "updated_at": stamp,
            "create_request_id": body.client_request_id, "processed_requests": []}
    try:
        await db.decks.insert_one(copy.deepcopy(deck))
        return deck
    except DuplicateKeyError:
        return await db.decks.find_one({"owner_hash": owner, "create_request_id": body.client_request_id}, {"_id": 0})


class JoinBody(BaseModel):
    device_id: str
    name: str
    emoji: str = "🍜"
    fun_fact: str = ""
    lang: str = "en"
    roast_level: str = "mild"
    mic_ready: bool = False
    client_request_id: Optional[str] = None


class AnswerBody(BaseModel):
    device_id: str
    question_id: str
    option_index: int
    client_request_id: str


# ------------------------------------------------------------------ demo data
async def load_demo_teams(room: dict) -> int:
    existing = await db.teams.count_documents({"room_code": room["code"], "is_demo": True})
    if existing:
        return 0
    added = 0
    for d in SD.DEMO_TEAMS:
        count = await db.teams.count_documents({"room_code": room["code"]})
        if count >= MAX_TEAMS:
            break
        r = await db.rooms.find_one_and_update({"code": room["code"]}, {"$inc": {"team_seq": 1}},
                                               return_document=ReturnDocument.AFTER)
        n = r["team_seq"]
        t = new_team_doc(room, f"demo-{uuid.uuid4().hex}", n, d["name"], d["emoji"], d["fun_fact"], "en",
                         d["roast"], d["mic"], is_demo=True)
        t["name_status"] = "shown"
        t["fun_fact_status"] = "approved"
        t["joined_ms"] = now_ms() - 60000
        await db.teams.insert_one(t)
        added += 1
    await db.rooms.update_one({"code": room["code"]}, {"$set": {"settings.simulate_crowd": True}})
    await log_decision(room, "demo", f"{added} demo teams", "allow", "demo data loaded", "host")
    return added


def new_team_doc(room, device_id, number, name, emoji, fun_fact, lang, roast, mic, is_demo=False):
    return {
        "id": uuid.uuid4().hex, "room_code": room["code"], "device_id": device_id, "number": number,
        "name": name, "name_status": "shown", "name_verdict": "allow", "name_reason": "",
        "emoji": emoji, "color": SD.TEAM_COLORS[(number - 1) % len(SD.TEAM_COLORS)],
        "fun_fact": fun_fact, "fun_fact_status": "pending" if fun_fact else "none",
        "fun_fact_verdict": "allow", "fun_fact_reason": "", "lang": lang, "roast_level": roast,
        "mic_ready": bool(mic), "hidden": False, "is_demo": is_demo, "brain_points": 0, "laugh_points": 0,
        "dong": 50000, "streak": 0, "cold": 0, "best_streak": 0, "fast_wrong_count": 0, "total_ms": 0,
        "secret_word": random.choice(SD.SECRET_WORDS), "ally_team_id": None,
        "joined_ms": now_ms(), "last_seen": now_ms(), "expire_at": room["expire_at"],
    }


# ------------------------------------------------------------------ answers & ticking
def elapsed_ms(room: dict, now: int) -> int:
    pd = room.get("phase_data") or {}
    paused = pd.get("paused_ms", 0)
    if room.get("frozen") and pd.get("frozen_at"):
        paused += now - pd["frozen_at"]
    return max(0, now - pd.get("open_ms", now) - paused)


def answers_open(room: dict, now: int) -> bool:
    if room["phase"] != "question_open":
        return False
    if room.get("frozen"):
        return True
    ends = room.get("phase_ends_at")
    return bool(ends) and now <= ends + ANSWER_GRACE_MS


async def submit_answer(room: dict, team: dict, q: dict, option: int, crid: str):
    """Insert an answer. Returns (answer, created)."""
    now = now_ms()
    pd = room["phase_data"]
    ms = elapsed_ms(room, now)
    limit = pd.get("limit_ms", 20000)
    correct = option == q["correct_index"]
    doc = {"id": uuid.uuid4().hex, "room_code": room["code"], "question_id": q["id"], "team_id": team["id"],
           "option_index": option, "is_correct": correct, "ms_taken": min(ms, limit),
           "points_pending": calc_points(ms, limit) if correct else 0,
           "fast_wrong": (not correct) and is_fast_wrong(ms, limit), "points_awarded": None,
           "client_request_id": crid, "created_at": now, "expire_at": room["expire_at"]}
    try:
        await db.answers.insert_one(doc)
        return doc, True
    except DuplicateKeyError:
        existing = await db.answers.find_one({"question_id": q["id"], "team_id": team["id"]}, {"_id": 0})
        return existing, False


async def eligible_teams(room: dict):
    pd = room.get("phase_data") or {}
    open_ms = pd.get("open_ms", 0)
    teams = await db.teams.find({"room_code": room["code"], "hidden": False}, {"_id": 0}).to_list(100)
    return [t for t in teams if t.get("joined_ms", 0) <= open_ms]


async def lock_question(room: dict, reason: str) -> bool:
    return await bump(room["code"], {"phase": "question_locked", "phase_ends_at": None, "frozen": False,
                                     "phase_started_at": now_ms(), "phase_data.lock_reason": reason},
                      cond={"phase": "question_open", "question_index": room["question_index"]})


async def maybe_auto_lock(room: dict) -> bool:
    if room["phase"] != "question_open":
        return False
    now = now_ms()
    if not room.get("frozen") and room.get("phase_ends_at") and now > room["phase_ends_at"] + ANSWER_GRACE_MS:
        return await lock_question(room, "timer")
    elig = await eligible_teams(room)
    if elig:
        qid = room["phase_data"]["qid"]
        ids = [t["id"] for t in elig]
        n = await db.answers.count_documents({"question_id": qid, "team_id": {"$in": ids}})
        if n >= len(ids):
            return await lock_question(room, "all_answered")
    return False


async def tick_room(room: dict) -> bool:
    if room.get("phase") == "poll_open":
        return await t2.tick(room)
    if room.get("phase") != "question_open":
        return False
    changed = False
    pd = room.get("phase_data") or {}
    now = now_ms()
    if room["settings"].get("simulate_crowd") and pd.get("sim") and not room.get("frozen") and answers_open(room, now):
        due = [s for s in pd["sim"] if s["at"] <= now]
        if due:
            done = {a["team_id"] for a in await db.answers.find({"question_id": pd["qid"]}, {"team_id": 1}).to_list(100)}
            todo = [s for s in due if s["team_id"] not in done]
            if todo:
                q = await db.questions.find_one({"id": pd["qid"]}, {"_id": 0})
                for s in todo:
                    team = await db.teams.find_one({"id": s["team_id"], "hidden": False}, {"_id": 0})
                    if team:
                        _, created = await submit_answer(room, team, q, s["option"], f"sim-{pd['qid']}-{team['id']}")
                        changed = changed or created
                if changed:
                    await bump(room["code"])
    if await maybe_auto_lock(room):
        changed = True
    return changed


async def ticker_loop():
    while True:
        try:
            rooms = await db.rooms.find({"phase": {"$in": ["question_open", "poll_open"]}}, {"_id": 0}).to_list(200)
            for r in rooms:
                await tick_room(r)
        except Exception as exc:  # never die
            logger.error("ticker: %s", exc)
        await asyncio.sleep(0.4)


# ------------------------------------------------------------------ transitions
async def recompute(room: dict, revealed: list):
    teams = await db.teams.find({"room_code": room["code"]}, {"_id": 0}).to_list(100)
    ans = await db.answers.find({"room_code": room["code"], "question_id": {"$in": revealed}}, {"_id": 0}).to_list(5000)
    by_q: Dict[str, Dict[str, dict]] = {}
    for a in ans:
        by_q.setdefault(a["question_id"], {})[a["team_id"]] = a
    stats, awarded = recompute_scores([t["id"] for t in teams], revealed, by_q)
    for t in teams:
        await db.teams.update_one({"id": t["id"]}, {"$set": stats[t["id"]]})
    for qid, per in awarded.items():
        for tid, pts in per.items():
            if tid in by_q.get(qid, {}):
                await db.answers.update_one({"question_id": qid, "team_id": tid}, {"$set": {"points_awarded": pts}})


async def open_question(room: dict, qi: int):
    entry = room["flat"][qi]
    q = await db.questions.find_one({"id": entry["qid"]}, {"_id": 0})
    if q["round_type"] == "poll":
        await bump(room["code"], {"question_index": qi, "round_index": entry["round_index"]})
        await t2.start(await get_room(room["code"]), q["text_en"], q["text_vi"], q.get("time_limit_s", 45), scheduled=True, media_hint=q.get("media_hint", ""), qid=q["id"])
        return
    limit_s = q.get("time_limit_s", 20) if q.get("custom_time") else (entry["time"] if entry["time"] != 20 else q.get("time_limit_s", 20))
    limit = int(limit_s * 1000)
    now = now_ms()
    await db.answers.delete_many({"question_id": q["id"]})
    revealed = [x for x in room.get("revealed", []) if x != q["id"]]
    if len(revealed) != len(room.get("revealed", [])):
        await recompute(room, revealed)
    sim = []
    if room["settings"].get("simulate_crowd"):
        demo = await db.teams.find({"room_code": room["code"], "is_demo": True, "hidden": False}, {"_id": 0}).to_list(50)
        for t in demo:
            sim.append({"team_id": t["id"], "at": now + random.randint(2000, 6000), "option": sim_choice(q["correct_index"], len(q["options"]))})
    await bump(room["code"], {
        "phase": "question_open", "status": "live", "question_index": qi, "round_index": entry["round_index"],
        "phase_started_at": now, "phase_ends_at": now + limit, "frozen": False, "revealed": revealed,
        "phase_data": {"qid": q["id"], "open_ms": now, "limit_ms": limit, "paused_ms": 0, "frozen_at": None,
                       "frozen_remaining_ms": None, "sim": sim}})


async def do_reveal(room: dict):
    entry = current_entry(room)
    q = await db.questions.find_one({"id": entry["qid"]}, {"_id": 0})
    revealed = [x for x in room.get("revealed", []) if x != q["id"]] + [q["id"]]
    await recompute(room, revealed)
    answers = await db.answers.find({"question_id": q["id"]}, {"_id": 0}).to_list(100)
    hidden = {t["id"] for t in await db.teams.find({"room_code": room["code"], "hidden": True}, {"id": 1}).to_list(100)}
    answers = [a for a in answers if a["team_id"] not in hidden]
    counts = [0] * len(q["options"])
    for a in answers:
        if 0 <= a["option_index"] < len(counts):
            counts[a["option_index"]] += 1
    correct = [a for a in answers if a["is_correct"]]
    fastest = min(correct, key=lambda a: a["ms_taken"]) if correct else None
    wrong_counts = [(c, i) for i, c in enumerate(counts) if i != q["correct_index"] and c > 0]
    popular_wrong = max(wrong_counts) if wrong_counts else None
    if room["settings"].get("sound_on", True):
        await add_event(room, "sound", {"sound": "ding" if correct else "buzz"})
    await bump(room["code"], {
        "phase": "reveal", "phase_ends_at": None, "frozen": False, "revealed": revealed, "phase_started_at": now_ms(),
        "phase_data": {"qid": q["id"], "counts": counts,
                       "fastest": {"team_id": fastest["team_id"], "ms": fastest["ms_taken"]} if fastest else None,
                       "popular_wrong": {"index": popular_wrong[1], "count": popular_wrong[0]} if popular_wrong else None}})


async def show_scoreboard(room: dict, round_end: bool):
    teams = await db.teams.find({"room_code": room["code"], "hidden": False}, {"_id": 0}).to_list(100)
    t2.scores(room, teams)
    ranked = rank_teams(teams)
    new_ranks = {t["id"]: i + 1 for i, t in enumerate(ranked)}
    prev = room.get("rank_snapshot") or {}
    moves = {tid: prev[tid] - r for tid, r in new_ranks.items() if tid in prev}
    climber = max(moves.items(), key=lambda kv: kv[1]) if moves else None
    faller = min(moves.items(), key=lambda kv: kv[1]) if moves else None
    entry = current_entry(room)
    final = bool(round_end and entry and entry["round_index"] == len(room["round_plan"]) - 1)
    await bump(room["code"], {
        "phase": "scoreboard", "phase_ends_at": None, "frozen": False, "phase_started_at": now_ms(), "rank_snapshot": new_ranks,
        "phase_data": {"round_end": round_end, "final": final, "prev_ranks": prev, "moves": moves,
                       "climber_id": climber[0] if climber and climber[1] > 0 else None,
                       "faller_id": faller[0] if faller and faller[1] < 0 else None}})


async def do_next(room: dict):
    phase = room["phase"]
    if phase in POLL_PHASES:
        await t2.next(room)
        return
    if phase == "reveal" and await t2.start_wrong_vote(room):
        return
    flat = room["flat"]
    qi = room.get("question_index", -1)
    if phase == "lobby":
        teams = await db.teams.find({"room_code": room["code"], "hidden": False}, {"_id": 0}).to_list(100)
        snap = {t["id"]: i + 1 for i, t in enumerate(rank_teams(teams))}
        await bump(room["code"], {"phase": "cold_open", "status": "live", "phase_started_at": now_ms(),
                                  "rank_snapshot": snap, "phase_data": {}})
    elif phase == "cold_open":
        await bump(room["code"], {"phase": "round_intro", "round_index": 0, "question_index": -1,
                                  "phase_started_at": now_ms(), "phase_data": {"next_qi": 0}})
    elif phase == "round_intro":
        await open_question(room, (room.get("phase_data") or {}).get("next_qi", max(qi, 0)))
    elif phase == "question_open":
        await lock_question(room, "host")
    elif phase == "question_locked":
        await do_reveal(room)
    elif phase == "reveal":
        kind, val = after_reveal_step(flat, qi, room["settings"]["night_preset"])
        if kind == "scoreboard":
            await show_scoreboard(room, val)
        else:
            await open_question(room, val)
    elif phase == "scoreboard":
        pd = room.get("phase_data") or {}
        if pd.get("final"):
            await bump(room["code"], {"phase": "ended", "status": "ended", "phase_started_at": now_ms(), "phase_data": {}})
        elif pd.get("round_end"):
            nxt = qi + 1
            await bump(room["code"], {"phase": "round_intro", "round_index": flat[nxt]["round_index"],
                                      "phase_started_at": now_ms(), "phase_data": {"next_qi": nxt}})
        else:
            await open_question(room, qi + 1)


async def discard_current(room: dict):
    entry = current_entry(room)
    if entry and entry["qid"] not in room.get("revealed", []):
        await db.answers.delete_many({"question_id": entry["qid"]})


# ------------------------------------------------------------------ state
async def build_state(room: dict, role: str, me: Optional[dict]) -> dict:
    now = now_ms()
    phase = room["phase"]
    blackout = bool(room.get("blackout")) and role == "screen"
    entry = current_entry(room)
    q = None
    if entry and phase in QUESTION_PHASES:
        q = await db.questions.find_one({"id": entry["qid"]}, {"_id": 0})
    teams = await db.teams.find({"room_code": room["code"]}, {"_id": 0}).sort("number", 1).to_list(100)
    visible = [t for t in teams if not t.get("hidden")]
    t2.scores(room, teams)
    if me:
        t2.scores(room, [me])
    ranked = rank_teams(visible)
    rank_of = {t["id"]: i + 1 for i, t in enumerate(ranked)}
    pd = room.get("phase_data") or {}
    answers = []
    if q:
        answers = await db.answers.find({"question_id": q["id"]}, {"_id": 0}).to_list(100)
    vis_ids = {t["id"] for t in visible}
    open_ms = pd.get("open_ms", 0)
    elig_ids = {t["id"] for t in visible if t.get("joined_ms", 0) <= open_ms} if q else set()
    rnd = room["round_plan"][room["round_index"]] if 0 <= room.get("round_index", -1) < len(room["round_plan"]) else None
    if phase == "round_intro" and pd.get("next_qi") is not None and pd["next_qi"] < len(room["flat"]):
        rnd = room["round_plan"][room["flat"][pd["next_qi"]]["round_index"]]
    facts = [] if blackout else [{"number": t["number"], "emoji": t["emoji"], "text": t["fun_fact"]}
                                 for t in visible if t.get("fun_fact_status") == "approved" and t.get("fun_fact")]
    events = await db.events.find({"room_code": room["code"], "at": {"$gt": now - 30000}}, {"_id": 0, "room_code": 0, "expire_at": 0}).sort("at", -1).to_list(10)
    s: Dict[str, Any] = {
        "version": room["version"], "server_now": now, "code": room["code"], "role": role,
        "phase": phase, "status": room["status"], "phase_started_at": room.get("phase_started_at"),
        "phase_ends_at": room.get("phase_ends_at"), "frozen": bool(room.get("frozen")),
        "frozen_remaining_ms": pd.get("frozen_remaining_ms") if room.get("frozen") else None,
        "limit_ms": pd.get("limit_ms"), "blackout": bool(room.get("blackout")),
        "default_lang": room["default_lang"], "host_name": room.get("host_name", ""), "venue_name": room.get("venue_name", ""),
        "round": ({"index": room["round_plan"].index(rnd), "name_en": rnd["name_en"], "name_vi": rnd["name_vi"],
                   "count": len(rnd["question_ids"])} if rnd else None),
        "round_total": len(room["round_plan"]),
        "question_index": room.get("question_index", -1),
        "question_number": (room["question_index"] + 1) if entry else 0,
        "question_total": len(room["flat"]),
        "question_in_round": (entry["pos"] + 1) if entry else 0,
        "team_count": len(visible),
        "answered_count": len([a for a in answers if a["team_id"] in elig_ids]),
        "eligible_count": len(elig_ids),
        "fun_facts": facts, "events": events,
    }
    if q:
        s["question"] = q_public(q)
    if phase == "reveal" and q:
        f = pd.get("fastest")
        ft = next((t for t in visible if f and t["id"] == f["team_id"]), None)
        s["reveal"] = {"counts": pd.get("counts", []), "correct_index": q["correct_index"],
                       "explanation_en": q.get("explanation_en", ""), "explanation_vi": q.get("explanation_vi", ""),
                       "fastest": {"team": team_public(ft, blackout), "ms": f["ms"]} if ft else None,
                       "popular_wrong": pd.get("popular_wrong")}
    if phase in ("reveal", "scoreboard", "ended"):
        top = ranked[:10]
        prev = pd.get("prev_ranks", {}) if phase == "scoreboard" else {}
        s["leaderboard"] = [{**team_public(t, blackout), "rank": i + 1, "prev_rank": prev.get(t["id"])} for i, t in enumerate(top)]
        if phase == "scoreboard":
            s["scoreboard"] = {"round_end": pd.get("round_end"), "final": pd.get("final"),
                               "climber_id": pd.get("climber_id"), "faller_id": pd.get("faller_id"),
                               "moves": {k: v for k, v in (pd.get("moves") or {}).items() if k in {t["id"] for t in top}}}
    if role == "screen":
        s["teams"] = [team_public(t, blackout) for t in visible]
    if role == "player":
        s["me"] = None
        if me:
            s["me"] = {"id": me["id"], "number": me["number"], "name": me["name"], "name_status": me["name_status"],
                       "emoji": me["emoji"], "color": me["color"], "brain_points": me.get("brain_points", 0),
                       "laugh_points": me.get("laugh_points", 0), "total": me.get("brain_points", 0) + me.get("laugh_points", 0),
                       "dong": me.get("dong", 0), "streak": me.get("streak", 0), "secret_word": me.get("secret_word"),
                       "roast_level": me["roast_level"], "mic_ready": me["mic_ready"], "hidden": me.get("hidden", False),
                       "rank": rank_of.get(me["id"]), "eligible": (me["id"] in elig_ids) if q else True}
            mine = next((a for a in answers if a["team_id"] == me["id"]), None)
            s["my_answer"] = {"option_index": mine["option_index"], "ms_taken": mine["ms_taken"]} if mine else None
            if phase == "reveal" and q:
                s["my_result"] = {"answered": bool(mine), "correct": bool(mine and mine["is_correct"]),
                                  "points": (mine or {}).get("points_awarded") or 0, "streak": me.get("streak", 0),
                                  "rank": rank_of.get(me["id"])}
    if role == "host":
        hq = None
        if entry:
            hq = await db.questions.find_one({"id": entry["qid"]}, {"_id": 0, "room_code": 0, "expire_at": 0})
        nxt = None
        nqi = pd.get("next_qi") if phase == "round_intro" else (room.get("question_index", -1) + 1)
        if phase in ("lobby", "cold_open"):
            nqi = 0
        if nqi is not None and 0 <= nqi < len(room["flat"]) and phase not in ("question_open", "question_locked"):
            nxt = await db.questions.find_one({"id": room["flat"][nqi]["qid"]}, {"_id": 0, "room_code": 0, "expire_at": 0})
        tmap = {t["id"]: t for t in teams}
        dist = None
        if q and phase in ("question_locked", "reveal"):
            dist = []
            for i, opt in enumerate(q["options"]):
                picks = sorted([a for a in answers if a["option_index"] == i and a["team_id"] in vis_ids], key=lambda a: a["ms_taken"])
                dist.append({"index": i, "count": len(picks), "teams": [
                    {"id": a["team_id"], "number": tmap[a["team_id"]]["number"], "name": tmap[a["team_id"]]["name"],
                     "emoji": tmap[a["team_id"]]["emoji"], "color": tmap[a["team_id"]]["color"], "ms": a["ms_taken"]}
                    for a in picks]})
        log = await db.decision_log.find({"room_code": room["code"]}, {"_id": 0, "room_code": 0, "expire_at": 0}).sort("at", -1).to_list(80)
        s["host"] = {
            "settings": room["settings"], "follow_links": room.get("follow_links", {}),
            "question": hq if (hq and phase in QUESTION_PHASES) else None, "next_question": nxt,
            "distribution": dist, "answered_team_ids": [a["team_id"] for a in answers] if q else [],
            "next_action": next_action(room), "rounds": [{"name_en": r["name_en"], "name_vi": r["name_vi"], "count": len(r["question_ids"])} for r in room["round_plan"]],
            "demo_loaded": any(t.get("is_demo") for t in teams), "decision_log": log,
            "lock_reason": pd.get("lock_reason"),
            "teams": [{"id": t["id"], "number": t["number"], "name": t["name"], "name_status": t["name_status"],
                       "name_verdict": t.get("name_verdict"), "name_reason": t.get("name_reason"), "emoji": t["emoji"],
                       "color": t["color"], "fun_fact": t.get("fun_fact", ""), "fun_fact_status": t.get("fun_fact_status"),
                       "fun_fact_verdict": t.get("fun_fact_verdict"), "fun_fact_reason": t.get("fun_fact_reason"),
                       "roast_level": t["roast_level"], "mic_ready": t["mic_ready"], "hidden": t.get("hidden", False),
                       "is_demo": t.get("is_demo", False), "last_seen": t.get("last_seen"),
                       "brain_points": t.get("brain_points", 0), "laugh_points": t.get("laugh_points", 0),
                       "total": t.get("brain_points", 0) + t.get("laugh_points", 0), "streak": t.get("streak", 0),
                       "cold": t.get("cold", 0), "fast_wrong_count": t.get("fast_wrong_count", 0),
                       "rank": rank_of.get(t["id"]), "answered": any(a["team_id"] == t["id"] for a in answers)}
                      for t in teams],
        }
    await t2.state(room, role, me, teams, s)
    return s


# ------------------------------------------------------------------ routes
@api.get("/")
async def root():
    return {"app": "Heckle & Hint", "ok": True}


@api.get("/meta")
async def meta():
    return {"puns": SD.PUNS, "emoji": SD.EMOJI}


@api.get("/question-bank")
async def question_bank(owner_key: Optional[str] = None):
    library_owner(owner_key)
    return {"questions": [{**copy.deepcopy(q), "id": f"seed-{i}", "index": i}
                          for i, q in enumerate(SD.QUESTIONS) if q["round_type"] in ("classic", "poll")]}


@api.get("/decks")
async def list_decks(owner_key: Optional[str] = None):
    owner = library_owner(owner_key)
    decks = await db.decks.find({"owner_hash": owner}, {"_id": 0}).sort("updated_at", DESCENDING).to_list(200)
    return {"decks": [deck_public(deck) for deck in decks]}


@api.post("/decks")
async def create_deck(body: DeckInput):
    return {"deck": deck_public(await save_new_deck(body))}


@api.post("/decks/{deck_id}")
async def update_deck(deck_id: str, body: DeckInput):
    deck = await owned_deck(deck_id, body.owner_key)
    if body.client_request_id in deck.get("processed_requests", []):
        return {"deck": deck_public(deck)}
    update = {"name": body.name, "description": body.description, "questions": deck_questions(body.questions), "updated_at": now_ms()}
    await db.decks.update_one({"id": deck_id, "owner_hash": library_owner(body.owner_key),
                               "processed_requests": {"$ne": body.client_request_id}},
                              {"$set": update, "$addToSet": {"processed_requests": body.client_request_id}})
    return {"deck": deck_public(await owned_deck(deck_id, body.owner_key))}


@api.post("/rooms/{code}/save-deck")
async def save_room_deck(code: str, body: DeckIdentity, key: Optional[str] = None):
    room = await get_room(code)
    require_host(room, key)
    questions = await t2.list_questions(room)
    if not questions:
        raise HTTPException(409, "keep_one_question")
    try:
        payload = DeckInput(**body.model_dump(), questions=questions)
    except ValueError:
        raise HTTPException(422, "invalid_deck")
    return {"deck": deck_public(await save_new_deck(payload))}


@api.post("/rooms")
async def create_room(body: CreateRoom):
    created = datetime.now(timezone.utc)
    expire = created + ROOM_TTL
    host_key = secrets.token_urlsafe(12)
    preset = "full" if body.night_preset == "full" else "demo"
    selected_deck = await owned_deck(body.deck_id, body.owner_key) if body.deck_id else None
    room = None
    for _ in range(20):
        code = gen_code()
        if await db.rooms.find_one({"code": code}, {"_id": 1}):
            continue
        qdocs = []
        source_questions = selected_deck["questions"] if selected_deck else SD.QUESTIONS
        for i, q in enumerate(source_questions):
            qdocs.append({**copy.deepcopy(q), "id": uuid.uuid4().hex, "room_code": code, "index": i, "expire_at": expire})
        # Preserve every question and poll in the comedian's selected order.
        plan = ([{"key": "custom_deck", "name_en": selected_deck["name"], "name_vi": selected_deck["name"],
                  "time": 20, "question_ids": [q["id"] for q in qdocs]}]
                if selected_deck else build_round_plan(preset, qdocs))
        links = {k: (body.follow_links.get(k) or "").strip()[:200] for k in ("zalo", "facebook", "instagram", "tiktok")}
        room = {
            "code": code, "host_key": host_key, "host_name": body.host_name.strip()[:40] or "The Comedian",
            "venue_name": body.venue_name.strip()[:60], "default_lang": "vi" if body.default_lang == "vi" else "en",
            "follow_links": links,
            "settings": {"roast_enabled": body.roast_enabled, "chaos_enabled": body.chaos_enabled, "sound_on": body.sound_on,
                         "auto_show_clean": False, "night_preset": preset, "bar_reward_text": body.bar_reward_text.strip()[:80] or "10% off your next round",
                         "bingo_phrases": [], "simulate_crowd": False},
            "status": "lobby", "phase": "lobby", "phase_data": {}, "phase_started_at": now_ms(), "phase_ends_at": None,
            "frozen": False, "round_plan": plan, "flat": flatten_plan(plan), "round_index": -1, "question_index": -1,
            "revealed": [], "rank_snapshot": {}, "version": 1, "comedian_meter": 0, "blackout": False, "team_seq": 0,
            "created_at": created, "expire_at": expire,
            "deck_id": selected_deck["id"] if selected_deck else None,
            "deck_name": selected_deck["name"] if selected_deck else None,
        }
        try:
            await db.rooms.insert_one(dict(room))
        except DuplicateKeyError:
            continue
        await db.questions.insert_many(qdocs)
        break
    if not room:
        raise HTTPException(500, "could_not_create_room")
    if body.load_demo:
        await load_demo_teams(room)
        await bump(room["code"])
    return {"code": room["code"], "host_key": host_key}


@api.get("/rooms/{code}/public")
async def room_public(code: str):
    room = await get_room(code)
    return {"code": room["code"], "host_name": room["host_name"], "venue_name": room["venue_name"],
            "default_lang": room["default_lang"], "status": room["status"]}


@api.get("/rooms/{code}/state")
async def room_state(code: str, role: str = "screen", key: Optional[str] = None, device: Optional[str] = None,
                     since_version: int = -1):
    room = await get_room(code)
    if role not in ("host", "player", "screen"):
        raise HTTPException(400, "bad_role")
    if role == "host":
        require_host(room, key)
    if await tick_room(room):
        room = await get_room(code)
    me = None
    if role == "player" and device:
        me = await db.teams.find_one({"room_code": room["code"], "device_id": device}, {"_id": 0})
        if me:
            now = now_ms()
            gap = now - (me.get("last_seen") or 0)
            if gap > 3000:
                await db.teams.update_one({"id": me["id"]}, {"$set": {"last_seen": now}})
                if gap > 8000:  # reconnecting team: let the host see the dot turn green
                    await bump(room["code"])
                    room = await get_room(code)
    if since_version == room["version"]:
        return {"unchanged": True, "version": room["version"], "server_now": now_ms()}
    return clean(await build_state(room, role, me))


@api.post("/rooms/{code}/join")
async def join_room(code: str, body: JoinBody):
    room = await get_room(code)
    existing = await db.teams.find_one({"room_code": room["code"], "device_id": body.device_id}, {"_id": 0})
    if existing:
        return {"ok": True, "team_id": existing["id"], "existing": True}
    name = " ".join((body.name or "").split())
    fact = " ".join((body.fun_fact or "").split())
    if not name:
        raise HTTPException(400, "name_required")
    if len(name) > 30:
        raise HTTPException(400, "name_too_long")
    if len(fact) > 80:
        raise HTTPException(400, "fact_too_long")
    if body.roast_level not in ("off", "mild", "spicy"):
        raise HTTPException(400, "bad_roast_level")
    if not body.device_id or len(body.device_id) > 80:
        raise HTTPException(400, "bad_device")
    if await db.teams.count_documents({"room_code": room["code"]}) >= MAX_TEAMS:
        raise HTTPException(409, "room_full")
    emoji = body.emoji if body.emoji in SD.EMOJI else SD.EMOJI[0]
    r = await db.rooms.find_one_and_update({"code": room["code"]}, {"$inc": {"team_seq": 1}}, return_document=ReturnDocument.AFTER)
    n = r["team_seq"]
    t = new_team_doc(room, body.device_id, n, name, emoji, fact, "vi" if body.lang == "vi" else "en", body.roast_level, body.mic_ready)
    nv, nr = check_text(name)
    t["name_verdict"], t["name_reason"] = nv, nr
    t["name_status"] = "shown" if nv == "allow" else "pending"
    if fact:
        fv, fr = check_text(fact)
        t["fun_fact_verdict"], t["fun_fact_reason"] = fv, fr
        t["fun_fact_status"] = "blocked" if fv == "block" else "pending"
    try:
        await db.teams.insert_one(t)
    except DuplicateKeyError:
        ex = await db.teams.find_one({"room_code": room["code"], "device_id": body.device_id}, {"_id": 0})
        return {"ok": True, "team_id": ex["id"], "existing": True}
    await log_decision(room, f"team:{t['id']}:name", name, nv, nr or "clean", "filter")
    if fact:
        await log_decision(room, f"team:{t['id']}:fun_fact", fact, t["fun_fact_verdict"], t["fun_fact_reason"] or "clean", "filter")
    await add_event(room, "team_joined", {"team_id": t["id"], "number": n})
    await bump(room["code"])
    return {"ok": True, "team_id": t["id"], "existing": False}


@api.post("/rooms/{code}/answer")
async def answer(code: str, body: AnswerBody):
    room = await get_room(code)
    team = await db.teams.find_one({"room_code": room["code"], "device_id": body.device_id}, {"_id": 0})
    if not team:
        raise HTTPException(404, "team_not_found")
    prior = await db.answers.find_one({"room_code": room["code"], "client_request_id": body.client_request_id}, {"_id": 0})
    if prior:
        return {"ok": True, "duplicate": True, "answer": {"option_index": prior["option_index"], "ms_taken": prior["ms_taken"]}}
    pd = room.get("phase_data") or {}
    if room["phase"] != "question_open" or pd.get("qid") != body.question_id or not answers_open(room, now_ms()):
        raise HTTPException(409, "answers_closed")
    if team.get("joined_ms", 0) > pd.get("open_ms", 0):
        raise HTTPException(409, "joined_late")
    q = await db.questions.find_one({"id": body.question_id}, {"_id": 0})
    if not (0 <= body.option_index < len(q["options"])):
        raise HTTPException(400, "bad_option")
    a, created = await submit_answer(room, team, q, body.option_index, body.client_request_id)
    if created:
        await bump(room["code"])
        await maybe_auto_lock(await get_room(code))
    return {"ok": True, "duplicate": not created, "answer": {"option_index": a["option_index"], "ms_taken": a["ms_taken"]}}


TEAM_OPS = {"approve_name", "hide", "unhide", "approve_fact", "hide_fact"}
SETTING_KEYS = {"simulate_crowd", "sound_on", "roast_enabled", "chaos_enabled", "auto_show_clean", "bar_reward_text"}


@api.post("/rooms/{code}/host/{action}")
async def host_action(code: str, action: str, key: Optional[str] = Query(None), body: Dict[str, Any] = Body(default={})):
    room = await get_room(code)
    require_host(room, key)
    crid = body.get("client_request_id")
    if not await claim_request(room, crid):
        return {"ok": True, "duplicate": True}
    phase = room["phase"]
    # Guard against double taps / stale consoles: NEXT only applies to the phase the host saw.
    if "expected_phase" in body and body["expected_phase"] != phase:
        return {"ok": True, "stale": True}
    if "expected_qi" in body and body["expected_qi"] != room.get("question_index"):
        return {"ok": True, "stale": True}
    flat = room["flat"]
    qi = room.get("question_index", -1)

    if action == "poll_start":
        source = None
        if body.get("question_id"):
            source = await db.questions.find_one({"room_code": room["code"], "id": body["question_id"], "round_type": "poll", "deleted": {"$ne": True}}, {"_id": 0})
            if not source:
                raise HTTPException(404, "question_not_found")
        elif body.get("preset") is not None:
            preset = body["preset"]
            if not isinstance(preset, int) or preset not in range(len(PRESETS)):
                raise HTTPException(400, "bad_prompt")
            source = {"text_en": PRESETS[preset][0], "text_vi": PRESETS[preset][1]}
        source = source or body
        limit = body.get("time_limit_s", source.get("time_limit_s", 45))
        if not isinstance(limit, int):
            raise HTTPException(400, "bad_prompt")
        await t2.start(room, str(source.get("text_en", "")), str(source.get("text_vi", "")), limit, media_hint=source.get("media_hint", ""))
    elif action == "poll_moderate":
        await t2.moderate(room["code"], body)
    elif action == "sound":
        sound = body.get("sound")
        if sound not in SOUNDS:
            raise HTTPException(400, "bad_sound")
        if room["settings"].get("sound_on", True):
            await add_event(room, "sound", {"sound": sound})
            await bump(room["code"])
    elif action == "next":
        await do_next(room)
    elif action == "add_time":
        if phase not in ("question_open", "poll_open"):
            raise HTTPException(409, "no_timer")
        if room.get("frozen"):
            await bump(code.upper(), {"phase_data.frozen_remaining_ms": (room["phase_data"].get("frozen_remaining_ms") or 0) + 10000},
                       extra={"$inc": {"version": 1, "phase_data.limit_ms": 10000}})
        else:
            await db.rooms.update_one({"code": room["code"]}, {"$inc": {"version": 1, "phase_ends_at": 10000, "phase_data.limit_ms": 10000}})
    elif action == "freeze":
        now = now_ms()
        if room.get("frozen"):
            pd = room["phase_data"]
            rem = pd.get("frozen_remaining_ms")
            upd = {"frozen": False, "phase_data.frozen_at": None, "phase_data.frozen_remaining_ms": None,
                   "phase_data.paused_ms": pd.get("paused_ms", 0) + (now - (pd.get("frozen_at") or now))}
            if rem is not None:
                upd["phase_ends_at"] = now + rem
            await bump(room["code"], upd)
        else:
            ends = room.get("phase_ends_at")
            await bump(room["code"], {"frozen": True, "phase_data.frozen_at": now,
                                      "phase_data.frozen_remaining_ms": max(0, ends - now) if ends else None, "phase_ends_at": None})
    elif action == "skip":
        if phase not in ("question_open", "question_locked"):
            raise HTTPException(409, "nothing_to_skip")
        await discard_current(room)
        kind, val = after_reveal_step(flat, qi, room["settings"]["night_preset"])
        if kind == "scoreboard":
            await show_scoreboard(room, val)
        else:
            await open_question(room, val)
    elif action == "previous":
        if qi < 0 or phase not in ("question_open", "question_locked", "reveal", "scoreboard"):
            raise HTTPException(409, "nothing_before")
        await discard_current(room)
        target = qi - 1 if qi > 0 else 0
        await open_question(await get_room(code), target)
    elif action == "end_round":
        if phase not in ("round_intro", "question_open", "question_locked", "reveal", "scoreboard") or qi < -1:
            raise HTTPException(409, "no_round")
        if phase == "round_intro":
            nq = room["phase_data"].get("next_qi", 0)
            ri = flat[nq]["round_index"]
        else:
            if phase == "scoreboard" and room["phase_data"].get("round_end"):
                return {"ok": True, "stale": True}
            ri = flat[qi]["round_index"]
        await discard_current(room)
        last = max(i for i, e in enumerate(flat) if e["round_index"] == ri)
        await db.rooms.update_one({"code": room["code"]}, {"$set": {"question_index": last, "round_index": ri}})
        await show_scoreboard(await get_room(code), True)
    elif action == "reset":
        await db.answers.delete_many({"room_code": room["code"]})
        await db.teams.update_many({"room_code": room["code"]}, {"$set": {
            "brain_points": 0, "laugh_points": 0, "streak": 0, "cold": 0, "best_streak": 0, "fast_wrong_count": 0, "total_ms": 0, "dong": 50000}})
        await bump(room["code"], {"active_poll": None, "laugh_awards": {}, "hof_done": [], "phase": "lobby", "status": "lobby", "phase_data": {}, "phase_ends_at": None, "frozen": False,
                                  "round_index": -1, "question_index": -1, "revealed": [], "rank_snapshot": {}, "blackout": False,
                                  "phase_started_at": now_ms()})
        await log_decision(room, "room", "reset", "allow", "room reset", "host")
    elif action == "blackout":
        val = body.get("value")
        val = (not room.get("blackout")) if val is None else bool(val)
        await bump(room["code"], {"blackout": val})
        await log_decision(room, "room:blackout", "BLACKOUT " + ("on" if val else "off"), "block" if val else "allow", "host blackout", "host")
    elif action == "load_demo":
        if phase != "lobby":
            raise HTTPException(409, "lobby_only")
        await load_demo_teams(room)
        await bump(room["code"])
    elif action == "settings":
        upd = {f"settings.{k}": v for k, v in (body.get("settings") or {}).items() if k in SETTING_KEYS}
        if "default_lang" in body:
            upd["default_lang"] = "vi" if body["default_lang"] == "vi" else "en"
        if upd:
            await bump(room["code"], upd)
    elif action == "team":
        op = body.get("op")
        tid = body.get("team_id")
        team = await db.teams.find_one({"room_code": room["code"], "id": tid}, {"_id": 0})
        if not team or op not in TEAM_OPS:
            raise HTTPException(400, "bad_team_op")
        if op == "approve_name":
            await db.teams.update_one({"id": tid}, {"$set": {"name_status": "shown"}})
            await log_decision(room, f"team:{tid}:name", team["name"], "allow", "host approved", "host")
        elif op in ("hide", "unhide"):
            await db.teams.update_one({"id": tid}, {"$set": {"hidden": op == "hide"}})
            await log_decision(room, f"team:{tid}", team["name"], "block" if op == "hide" else "allow", f"host {op}", "host")
        elif op == "approve_fact":
            await db.teams.update_one({"id": tid}, {"$set": {"fun_fact_status": "approved"}})
            await log_decision(room, f"team:{tid}:fun_fact", team.get("fun_fact", ""), "allow", "host approved", "host")
        elif op == "hide_fact":
            await db.teams.update_one({"id": tid}, {"$set": {"fun_fact_status": "hidden"}})
            await log_decision(room, f"team:{tid}:fun_fact", team.get("fun_fact", ""), "block", "host hid", "host")
        await bump(room["code"])
        if op == "hide":
            await maybe_auto_lock(await get_room(code))
    else:
        raise HTTPException(404, "unknown_action")
    return {"ok": True}


t2 = Tier2(sys.modules[__name__])
t2.register(api)
news = NewsService(sys.modules[__name__])
news.register(api)
app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await news.setup()
    app.state.index_task = asyncio.create_task(ensure_indexes())
    app.state.ticker = asyncio.create_task(ticker_loop())


@app.on_event("shutdown")
async def shutdown():
    for t in (app.state.index_task, app.state.ticker):
        t.cancel()
        with suppress(asyncio.CancelledError):
            await t
    client.close()
