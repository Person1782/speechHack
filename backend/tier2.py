"""Tier 2: question management, moderated write-ins, Hall of Fame and sound events.
Room-version compare-and-swap keeps ballots and awards atomic across polling clients.
"""
import copy
import unicodedata
import uuid
from typing import Optional, Literal
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from game import flatten_plan, after_reveal_step
from moderation import check_text, sexual_content


class OK(BaseModel):
    ok: bool = True
    id: Optional[str] = None
    duplicate: bool = False


class Option(BaseModel):
    en: str = Field(default="", max_length=160)
    vi: str = Field(default="", max_length=160)


class Notes(BaseModel):
    opener: str = Field(default="", max_length=600)
    follow_up: str = Field(default="", max_length=600)
    backup: str = Field(default="", max_length=600)


class QuestionInput(BaseModel):
    round_type: Literal["classic", "poll", "decoy", "caption"] = "classic"
    text_en: str = Field(min_length=1, max_length=500)
    text_vi: str = Field(default="", max_length=500)
    options: list[Option] = Field(default_factory=list, max_length=4)
    correct_index: Optional[int] = None
    setup_line: str = Field(default="", max_length=600)
    punchline: str = Field(default="", max_length=600)
    notes: Notes = Field(default_factory=Notes)
    hint_joke: str = Field(default="", max_length=600)
    fake_explanations: list[str] = Field(default_factory=list, max_length=4)
    media_hint: str = Field(default="", max_length=100)
    time_limit_s: int = Field(default=20, ge=5, le=180)
    explanation_en: str = Field(default="", max_length=600)
    explanation_vi: str = Field(default="", max_length=600)
    client_request_id: Optional[str] = None

    @model_validator(mode="after")
    def valid_question(self):
        if not self.text_en.strip():
            raise ValueError("question_required")
        if self.round_type != "poll":
            if len(self.options) != 4 or any(not o.en.strip() for o in self.options):
                raise ValueError("four_options_required")
            if self.correct_index not in range(4):
                raise ValueError("correct_answer_required")
        if any(len(x) > 600 for x in self.fake_explanations):
            raise ValueError("explanation_too_long")
        if sexual_content(str(self.model_dump(exclude={"client_request_id"}))):
            raise ValueError("content_blocked")
        return self


class QuestionOut(QuestionInput):
    id: str
    editable: bool = True
    sources: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_question(self):
        # Read-time serialization must not re-moderate existing seed/history.
        # CREATE and EDIT continue to use QuestionInput's validation.
        return self


class QuestionList(BaseModel):
    questions: list[QuestionOut]


class OrderBody(BaseModel):
    ids: list[str] = Field(max_length=100)
    client_request_id: Optional[str] = None


class PollSubmit(BaseModel):
    poll_id: str
    device_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=80)
    anonymous: bool = False
    client_request_id: Optional[str] = None


class PollVote(BaseModel):
    poll_id: str
    device_id: str = Field(min_length=1, max_length=80)
    answer_id: str
    client_request_id: Optional[str] = None


class ClaimBody(BaseModel):
    poll_id: str
    device_id: str = Field(min_length=1, max_length=80)
    client_request_id: Optional[str] = None


def normalize_text(text):
    text = " ".join(text.strip().casefold().split()).replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


PRESETS = [
    ("Worst thing to say on a first date in Saigon", "Điều tệ nhất để nói trong buổi hẹn đầu ở Sài Gòn"),
    ("Give District 1 a new name", "Đặt tên mới cho Quận 1"),
    ("What is the motorbike thinking?", "Chiếc xe máy đang nghĩ gì?"),
    ("Explain crossing the street to a tourist", "Giải thích cách qua đường cho khách du lịch"),
]
SOUNDS = {"rimshot", "sad_trombone", "motorbike_horn", "air_horn", "drumroll", "applause", "ding", "buzz", "tick_tock", "siren", "pop", "cash_register"}
POLL_PHASES = {"poll_open", "poll_review", "poll_vote", "poll_hof"}


class Tier2:
    def __init__(self, server):
        self.s = server
        self.db = server.db

    async def change(self, code, fn):
        for _ in range(30):
            room = await self.s.get_room(code)
            fields, result = await fn(copy.deepcopy(room))
            if not fields:
                return result
            if await self.s.bump(room["code"], fields, cond={"version": room["version"]}):
                return result
        raise HTTPException(409, "room_busy")

    def check_poll(self, room, poll_id, phases):
        p = room.get("active_poll")
        if not p or p["id"] != poll_id or room["phase"] not in phases:
            raise HTTPException(409, "poll_closed")
        return p

    async def team(self, code, device):
        t = await self.db.teams.find_one({"room_code": code.upper(), "device_id": device, "hidden": False}, {"_id": 0})
        if not t:
            raise HTTPException(403, "team_required")
        return t

    def award(self, room, group, reason, amount, only=None):
        awards = room.setdefault("laugh_awards", {})
        for member in group["members"]:
            tid = member["team_id"]
            if only and tid != only:
                continue
            # Award keys are independent of retry IDs and persisted atomically with the ballot.
            key = f"{room['active_poll']['id']}:{group['id']}:{reason}:{tid}"
            awards.setdefault(key, {"team_id": tid, "points": amount})

    def scores(self, room, teams):
        totals = {}
        for a in room.get("laugh_awards", {}).values():
            totals[a["team_id"]] = totals.get(a["team_id"], 0) + a["points"]
        for t in teams:
            t["laugh_points"] = totals.get(t["id"], 0)
        return teams

    async def list_questions(self, room):
        docs = await self.db.questions.find({"room_code": room["code"]}, {"_id": 0}).to_list(200)
        by_id = {q["id"]: q for q in docs}
        return [dict(by_id[e["qid"]], editable=i > room["question_index"]) for i, e in enumerate(room["flat"]) if e["qid"] in by_id]

    async def save_plan(self, room, ids):
        old = room["flat"]
        locked = room["question_index"] + 1
        if ids[:locked] != [e["qid"] for e in old[:locked]]:
            raise HTTPException(409, "question_in_play")
        if not ids:
            raise HTTPException(409, "keep_one_question")
        plan = copy.deepcopy(room["round_plan"])
        # Preserve round boundaries while allowing movement among all future slots.
        slots = [e["round_index"] for e in old]
        for r in plan:
            r["question_ids"] = []
        for i, qid in enumerate(ids):
            ri = slots[min(i, len(slots) - 1)] if slots else 0
            plan[ri]["question_ids"].append(qid)
        plan = [r for r in plan if r["question_ids"]]
        flat = flatten_plan(plan)
        fields = {"round_plan": plan, "flat": flat}
        if room["question_index"] >= 0:
            fields["round_index"] = flat[room["question_index"]]["round_index"]
        if room["phase"] == "scoreboard" and room.get("phase_data", {}).get("final") and len(ids) > len(old):
            fields["phase_data.final"] = False
            fields["phase_data.round_end"] = False
        if not await self.s.bump(room["code"], fields, cond={"version": room["version"]}):
            raise HTTPException(409, "room_changed")

    def snapshot(self, room):
        snap = {k: copy.deepcopy(room.get(k)) for k in ("phase", "status", "phase_data", "phase_started_at", "phase_ends_at", "frozen", "question_index", "round_index")}
        snap["saved_at"] = self.s.now_ms()
        snap["remaining"] = max(0, (room.get("phase_ends_at") or self.s.now_ms()) - self.s.now_ms())
        return snap

    async def start(self, room, text_en, text_vi="", time_limit_s=45, scheduled=False, media_hint="", qid=None):
        if room["phase"] in POLL_PHASES:
            raise HTTPException(409, "poll_active")
        if not text_en.strip() or len(text_en) > 500 or len(text_vi) > 500 or not 5 <= time_limit_s <= 180:
            raise HTTPException(400, "bad_prompt")
        if sexual_content(text_en + " " + text_vi):
            raise HTTPException(400, "content_blocked")
        now = self.s.now_ms()
        p = {"id": str(uuid.uuid4()), "text_en": text_en.strip(), "text_vi": text_vi.strip() or text_en.strip(),
             "media_hint": media_hint, "opened_at": now, "groups": [], "approval_seq": 0, "winner_id": None,
             "claims": [], "resume": {"scheduled": True} if scheduled else self.snapshot(room), "kind": "poll", "qid": qid}
        fields = {"active_poll": p, "phase": "poll_open", "phase_ends_at": now + time_limit_s * 1000,
                  "phase_started_at": now, "frozen": False, "phase_data": {"open_ms": now, "limit_ms": time_limit_s * 1000, "paused_ms": 0}}
        if not await self.s.bump(room["code"], fields, cond={"version": room["version"]}):
            raise HTTPException(409, "room_changed")
        return p["id"]

    async def start_wrong_vote(self, room):
        e = self.s.current_entry(room)
        q = await self.db.questions.find_one({"id": e["qid"]}, {"_id": 0}) if e else None
        if not q or q["round_type"] not in ("decoy", "caption") or q["id"] in room.get("hof_done", []):
            return False
        answers = await self.db.answers.find({"question_id": q["id"], "is_correct": False}, {"_id": 0}).sort("ms_taken", 1).to_list(100)
        teams = {t["id"]: t for t in await self.db.teams.find({"room_code": room["code"], "hidden": False}, {"_id": 0}).to_list(100)}
        groups = []
        for i, opt in enumerate(q["options"]):
            members = [{"team_id": a["team_id"], "anonymous": True, "verdict": "allow"} for a in answers if a["option_index"] == i and a["team_id"] in teams]
            if members:
                groups.append({"id": str(uuid.uuid4()), "text": opt["en"], "text_vi": opt["vi"], "norm": normalize_text(opt["en"]), "members": members,
                               "verdict": "allow", "status": "approved", "order": i, "votes": []})
        if not groups:
            return False
        p = {"id": str(uuid.uuid4()), "text_en": q["text_en"], "text_vi": q["text_vi"], "groups": groups,
             "approval_seq": len(groups), "winner_id": None, "claims": [], "kind": "wrong_vote", "qid": q["id"],
             "resume": self.snapshot(room), "opened_at": self.s.now_ms()}
        await self.s.bump(room["code"], {"active_poll": p, "phase": "poll_vote", "phase_ends_at": None,
                                        "phase_data": {}, "hof_done": room.get("hof_done", []) + [q["id"]]})
        return True

    async def tick(self, room):
        if room["phase"] != "poll_open" or room.get("frozen"):
            return False
        p = room["active_poll"]
        original_version = room["version"]
        now = self.s.now_ms()
        if room.get("phase_ends_at") and now >= room["phase_ends_at"]:
            return await self.s.bump(room["code"], {"phase": "poll_review", "phase_ends_at": None}, cond={"phase": "poll_open", "active_poll.id": p["id"]})
        if room["settings"].get("simulate_crowd") and now - p["opened_at"] >= 2500:
            demos = await self.db.teams.find({"room_code": room["code"], "is_demo": True, "hidden": False}, {"_id": 0}).to_list(30)
            for i, team in enumerate(demos):
                await self.submit(room["code"], PollSubmit(poll_id=p["id"], device_id=team["device_id"], text=["My motorbike needed a holiday", "The traffic light had commitment issues", "One more coffee. For science.", "A fridge with a driving licence"][i % 4]))
            room = await self.s.get_room(room["code"])
        if room.get("phase_ends_at") and now >= room["phase_ends_at"]:
            return await self.s.bump(room["code"], {"phase": "poll_review", "phase_ends_at": None}, cond={"phase": "poll_open", "active_poll.id": p["id"]})
        return original_version != (await self.s.get_room(room["code"]))["version"]

    async def next(self, room):
        p = room["active_poll"]
        if room["phase"] == "poll_hof":
            return await self.resume(room)
        async def op(r):
            poll = self.check_poll(r, p["id"], {room["phase"]})
            fields = {"phase_ends_at": None, "frozen": False}
            if r["phase"] == "poll_open":
                fields["phase"] = "poll_review"
            elif r["phase"] == "poll_review":
                fields["phase"] = "poll_vote"
            else:
                candidates = sorted([g for g in poll["groups"] if g["status"] == "approved" and g["votes"]], key=lambda g: (-len(g["votes"]), g["order"]))
                poll["winner_id"] = candidates[0]["id"] if candidates else None
                if candidates and poll["kind"] == "poll":
                    self.award(r, candidates[0], "winner", 300)
                fields.update({"phase": "poll_hof", "active_poll": poll, "laugh_awards": r.get("laugh_awards", {})})
            return fields, OK()
        await self.change(room["code"], op)

    async def resume(self, room):
        snap = room["active_poll"]["resume"]
        if snap.get("scheduled"):
            await self.s.bump(room["code"], {"active_poll": None, "phase": "reveal"})
            kind, val = after_reveal_step(room["flat"], room["question_index"], room["settings"]["night_preset"])
            if kind == "scoreboard":
                await self.s.show_scoreboard(room, val)
            else:
                await self.s.open_question(room, val)
            return
        fields = {k: copy.deepcopy(v) for k, v in snap.items() if k not in ("remaining", "saved_at")}
        if snap.get("phase_ends_at"):
            fields["phase_ends_at"] = self.s.now_ms() + snap["remaining"]
        paused = self.s.now_ms() - snap["saved_at"]
        pd = fields.get("phase_data") or {}
        if snap["phase"] == "question_open":
            pd["paused_ms"] = pd.get("paused_ms", 0) + paused
            if pd.get("frozen_at"):
                pd["frozen_at"] += paused
            for sim in pd.get("sim", []):
                sim["at"] += paused
        fields.update({"phase_data": pd, "active_poll": None})
        await self.s.bump(room["code"], fields, cond={"phase": "poll_hof", "active_poll.id": room["active_poll"]["id"]})

    async def submit(self, code, body):
        team = await self.team(code, body.device_id)
        text = " ".join(body.text.split())
        if not text:
            raise HTTPException(400, "answer_required")
        async def op(r):
            p = self.check_poll(r, body.poll_id, {"poll_open"})
            if any(any(m["team_id"] == team["id"] for m in g["members"]) for g in p["groups"]):
                return {}, OK(duplicate=True)
            if not r.get("frozen") and self.s.now_ms() >= (r.get("phase_ends_at") or 0):
                raise HTTPException(409, "poll_closed")
            verdict, _ = check_text(text)
            if sexual_content(text):
                verdict = "block"
            norm = normalize_text(text)
            g = next((g for g in p["groups"] if g["norm"] == norm), None)
            if not g:
                g = {"id": str(uuid.uuid4()), "text": text, "norm": norm, "members": [], "status": "pending", "verdict": verdict, "votes": []}
                p["groups"].append(g)
            if verdict == "block" or (verdict == "flag" and g["verdict"] == "allow"):
                g["verdict"] = verdict
            g["members"].append({"team_id": team["id"], "anonymous": body.anonymous, "verdict": verdict})
            return {"active_poll": p}, OK()
        return await self.change(code, op)

    async def vote(self, code, body):
        team = await self.team(code, body.device_id)
        async def op(r):
            p = self.check_poll(r, body.poll_id, {"poll_review", "poll_vote"})
            g = next((g for g in p["groups"] if g["id"] == body.answer_id and g["status"] == "approved"), None)
            if not g:
                raise HTTPException(409, "answer_unavailable")
            if any(m["team_id"] == team["id"] for m in g["members"]):
                raise HTTPException(403, "self_vote")
            if team["id"] in g["votes"]:
                return {}, OK(duplicate=True)
            g["votes"].append(team["id"])
            return {"active_poll": p}, OK()
        return await self.change(code, op)

    async def claim(self, code, body):
        team = await self.team(code, body.device_id)
        async def op(r):
            p = self.check_poll(r, body.poll_id, {"poll_hof"})
            g = next((g for g in p["groups"] if g["id"] == p["winner_id"]), None)
            if not g or not any(m["team_id"] == team["id"] for m in g["members"]):
                raise HTTPException(403, "not_your_answer")
            if team["id"] in p["claims"]:
                return {}, OK(duplicate=True)
            p["claims"].append(team["id"])
            self.award(r, g, "claim", 200, only=team["id"])
            return {"active_poll": p, "laugh_awards": r["laugh_awards"]}, OK()
        return await self.change(code, op)

    async def moderate(self, code, body):
        async def op(r):
            p = self.check_poll(r, body.get("poll_id"), {"poll_review", "poll_vote"})
            g = next((g for g in p["groups"] if g["id"] == body.get("answer_id")), None)
            if not g or body.get("verdict") not in ("approve", "hide"):
                raise HTTPException(400, "bad_moderation")
            if body["verdict"] == "approve":
                if g["verdict"] == "block":
                    raise HTTPException(403, "content_blocked")
                if g["status"] == "approved":
                    return {}, OK(duplicate=True)
                if sum(g["status"] == "approved" for g in p["groups"]) >= 6:
                    raise HTTPException(409, "approval_limit")
                p["approval_seq"] += 1
                g.update(status="approved", order=p["approval_seq"])
                self.award(r, g, "approved", 100)
            else:
                g["status"] = "hidden"
            return {"active_poll": p, "laugh_awards": r.get("laugh_awards", {})}, OK()
        return await self.change(code, op)

    async def state(self, room, role, me, teams, state):
        state["sound_on"] = bool(room["settings"].get("sound_on", True))
        if role == "screen":
            state["sound_events"] = await self.db.events.find({"room_code": room["code"], "type": "sound", "at": {"$gt": self.s.now_ms() - 10000}}, {"_id": 0, "room_code": 0, "expire_at": 0}).sort("at", 1).to_list(100)
        if role == "host":
            state["host"]["poll_seeds"] = [{"id": q["id"], "text_en": q["text_en"], "text_vi": q["text_vi"]} for q in await self.db.questions.find({"room_code": room["code"], "round_type": "poll", "deleted": {"$ne": True}}, {"_id": 0}).to_list(100)]
        p = room.get("active_poll")
        if not p or room["phase"] not in POLL_PHASES:
            return
        tmap = {t["id"]: t for t in teams if not t.get("hidden")}
        tid = me["id"] if me else None
        groups = []
        for g in p["groups"]:
            if role != "host" and (g["status"] != "approved" or room["phase"] in ("poll_open", "poll_hof")):
                continue
            members = [m for m in g["members"] if m["team_id"] in tmap]
            if not members:
                continue
            item = {"id": g["id"], "text": g["text"], "text_vi": g.get("text_vi", g["text"]), "count": len(members), "votes": len(g["votes"]), "order": g.get("order", 0)}
            if role == "host":
                item.update(status=g["status"], verdict=g["verdict"], authors=[{"name": tmap[m["team_id"]]["name"], "number": tmap[m["team_id"]]["number"], "anonymous": m["anonymous"], "verdict": m["verdict"]} for m in members])
            else:
                item["authors"] = [{"name": self.s.team_display(tmap[m["team_id"]], False), "number": tmap[m["team_id"]]["number"]} for m in members if not m["anonymous"]]
                if role == "player":
                    item["own"] = any(m["team_id"] == tid for m in members)
                    item["voted"] = tid in g["votes"]
            groups.append(item)
        mine = next((g for g in p["groups"] if any(m["team_id"] == tid for m in g["members"])), None) if tid else None
        state["poll"] = {"id": p["id"], "kind": p["kind"], "text_en": p["text_en"], "text_vi": p["text_vi"], "media_hint": p.get("media_hint", ""),
                         "groups": sorted(groups, key=lambda g: g["order"]), "submitted_count": sum(len(g["members"]) for g in p["groups"])}
        if role == "player":
            state["poll"].update(submitted=bool(mine), my_text=mine["text"] if mine else None, eligible=bool(me))
        if room["phase"] == "poll_hof":
            winner = next((g for g in p["groups"] if g["id"] == p["winner_id"]), None)
            state["hall_of_fame"] = None
            if winner:
                state["hall_of_fame"] = {"text": winner["text"], "text_vi": winner.get("text_vi", winner["text"]), "votes": len(winner["votes"]),
                                         "claimed_names": [{"name": self.s.team_display(tmap[x], False), "number": tmap[x]["number"]} for x in p["claims"] if x in tmap]}
                if role == "player":
                    state["hall_of_fame"].update(can_claim=any(m["team_id"] == tid for m in winner["members"]) and tid not in p["claims"], claimed=tid in p["claims"])
        if role == "screen" and room.get("blackout"):
            state["poll"]["groups"] = []
            state["hall_of_fame"] = None

    def register(self, api):
        @api.get("/rooms/{code}/questions", response_model=QuestionList)
        async def question_list(code: str, key: Optional[str] = None):
            room = await self.s.get_room(code)
            self.s.require_host(room, key)
            return {"questions": await self.list_questions(room)}

        @api.post("/rooms/{code}/questions", response_model=OK)
        async def question_add(code: str, body: QuestionInput, key: Optional[str] = None):
            room = await self.s.get_room(code)
            self.s.require_host(room, key)
            if len(room["flat"]) >= 100:
                raise HTTPException(409, "question_limit")
            if body.client_request_id:
                old = await self.db.questions.find_one({"room_code": room["code"], "request_id": body.client_request_id})
                if old:
                    return OK(id=old["id"], duplicate=True)
            qid = str(uuid.uuid4())
            data = body.model_dump(exclude={"client_request_id"})
            data["custom_time"] = True
            data["text_vi"] = data["text_vi"] or data["text_en"]
            for o in data["options"]:
                o["vi"] = o["vi"] or o["en"]
            data.update(id=qid, room_code=room["code"], index=len(room["flat"]), expire_at=room["expire_at"], request_id=body.client_request_id)
            await self.db.questions.insert_one(data)
            try:
                await self.save_plan(room, [e["qid"] for e in room["flat"]] + [qid])
            except Exception:
                await self.db.questions.update_one({"id": qid}, {"$set": {"deleted": True}})
                raise
            return OK(id=qid)

        @api.post("/rooms/{code}/question-order", response_model=OK)
        async def question_order(code: str, body: OrderBody, key: Optional[str] = None):
            room = await self.s.get_room(code)
            self.s.require_host(room, key)
            ids = [e["qid"] for e in room["flat"]]
            if len(body.ids) != len(ids) or set(body.ids) != set(ids):
                raise HTTPException(400, "bad_order")
            await self.save_plan(room, body.ids)
            return OK()

        @api.post("/rooms/{code}/questions/{qid}", response_model=OK)
        async def question_edit(code: str, qid: str, body: QuestionInput, key: Optional[str] = None):
            room = await self.s.get_room(code)
            self.s.require_host(room, key)
            ids = [e["qid"] for e in room["flat"]]
            if qid not in ids:
                raise HTTPException(404, "question_not_found")
            if ids.index(qid) <= room["question_index"]:
                raise HTTPException(409, "question_in_play")
            data = body.model_dump(exclude={"client_request_id"})
            data["custom_time"] = True
            data["text_vi"] = data["text_vi"] or data["text_en"]
            for o in data["options"]:
                o["vi"] = o["vi"] or o["en"]
            await self.db.questions.update_one({"id": qid, "room_code": room["code"]}, {"$set": data})
            await self.s.bump(room["code"])
            return OK(id=qid)

        @api.post("/rooms/{code}/questions/{qid}/delete", response_model=OK)
        async def question_delete(code: str, qid: str, key: Optional[str] = None):
            room = await self.s.get_room(code)
            self.s.require_host(room, key)
            ids = [e["qid"] for e in room["flat"]]
            if qid not in ids:
                return OK(duplicate=True)
            if ids.index(qid) <= room["question_index"]:
                raise HTTPException(409, "question_in_play")
            await self.save_plan(room, [x for x in ids if x != qid])
            await self.db.questions.update_one({"id": qid, "room_code": room["code"]}, {"$set": {"deleted": True}})
            return OK()

        @api.post("/rooms/{code}/poll/submit", response_model=OK)
        async def submit(code: str, body: PollSubmit):
            return await self.submit(code, body)

        @api.post("/rooms/{code}/poll/vote", response_model=OK)
        async def vote(code: str, body: PollVote):
            return await self.vote(code, body)

        @api.post("/rooms/{code}/poll/claim", response_model=OK)
        async def claim(code: str, body: ClaimBody):
            return await self.claim(code, body)
