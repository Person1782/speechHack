"""Host-only You.com research. Search evidence never auto-publishes a question."""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from tier2 import QuestionInput, OK
from moderation import sexual_content

YOU_SEARCH_URL = "https://ydc-index.io/v1/search"


class NewsQuery(BaseModel):
    query: str = Field(min_length=2, max_length=180)
    language: Literal["EN", "VI"] = "EN"
    client_request_id: Optional[str] = None


class Source(BaseModel):
    id: str
    title: str
    url: str
    description: str = ""
    excerpts: list[str] = Field(default_factory=list)
    published_at: Optional[str] = None
    provider: str = "You.com"


class SearchOut(BaseModel):
    id: str
    query: str
    searched_at: str
    results: list[Source]
    cached: bool = False


class DraftFields(QuestionInput):
    text_en: str = Field(default="", max_length=500)
    correct_index: Optional[int] = None

    @model_validator(mode="after")
    def valid_question(self):
        if sexual_content(str(self.model_dump(exclude={"client_request_id"}))):
            raise ValueError("content_blocked")
        if any(len(x) > 600 for x in self.fake_explanations):
            raise ValueError("explanation_too_long")
        return self


class DraftOut(BaseModel):
    id: str
    fields: DraftFields
    source: Source
    updated_at: str
    status: str = "draft"
    published_question_id: Optional[str] = None


class NewsState(BaseModel):
    available: bool
    latest_search: Optional[SearchOut] = None
    drafts: list[DraftOut]


class SourceInput(BaseModel):
    source_id: str
    client_request_id: Optional[str] = None


class PublishInput(QuestionInput):
    reviewed: bool = False


def normalize_results(data):
    results = data.get("results", {}).get("web", [])
    out, seen = [], set()
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", ""))
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or url in seen:
            continue
        title = str(item.get("title") or parsed.hostname)[:500]
        description = str(item.get("description") or "")[:2000]
        contents = item.get("contents") or {}
        snippets = contents.get("highlights", []) if isinstance(contents, dict) else []
        snippets = snippets or item.get("snippets", []) or []
        if isinstance(snippets, str):
            snippets = [snippets]
        excerpts = [s[:1600] for s in snippets if isinstance(s, str)][:3]
        if sexual_content(" ".join([title, description, *excerpts])):
            continue
        out.append({"id": str(uuid.uuid4()), "title": title, "url": url, "description": description,
                    "excerpts": excerpts, "published_at": str(item["page_age"]) if item.get("page_age") else None, "provider": "You.com"})
        seen.add(url)
    return out[:8]


async def you_search(query, language):
    key = os.environ.get("YDC_API_KEY")
    if not key:
        raise HTTPException(503, "news_not_configured")
    payload = {"query": query + " news", "count": 8, "freshness": "week", "language": language,
               "safesearch": "moderate", "extraction": {"extraction_mode": "highlights", "highlights": {"total_max_tokens": 2048}}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0), follow_redirects=False) as client:
            for attempt in range(2):
                response = await client.post(YOU_SEARCH_URL, headers={"X-API-Key": key}, json=payload)
                if response.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(0.4)
                    continue
                if response.status_code in (401, 403):
                    raise HTTPException(502, "news_credentials")
                if response.status_code == 402:
                    raise HTTPException(502, "news_credits")
                if response.status_code == 429:
                    raise HTTPException(429, "news_rate_limited")
                if response.status_code != 200:
                    raise HTTPException(502, "news_unavailable")
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("results"), dict):
                    raise HTTPException(502, "news_unavailable")
                return normalize_results(data)
    except httpx.TimeoutException:
        raise HTTPException(504, "news_timeout")
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(502, "news_unavailable")


class NewsService:
    def __init__(self, server):
        self.s = server
        self.db = server.db
        self.locks = {}

    async def host(self, code, key):
        room = await self.s.get_room(code)
        self.s.require_host(room, key)
        return room

    async def draft(self, code, draft_id):
        draft = await self.db.news_drafts.find_one({"id": draft_id, "room_code": code, "deleted": False}, {"_id": 0})
        if not draft:
            raise HTTPException(404, "news_draft_missing")
        return draft

    async def setup(self):
        for name in ("news_searches", "news_drafts"):
            await self.db[name].create_index("expire_at", expireAfterSeconds=0)
            await self.db[name].create_index("id", unique=True)
            await self.db[name].create_index("room_code")

    def register(self, api):
        @api.get("/rooms/{code}/news", response_model=NewsState)
        async def news_state(code: str, key: Optional[str] = None):
            room = await self.host(code, key)
            latest = await self.db.news_searches.find_one({"room_code": room["code"]}, {"_id": 0}, sort=[("created_ms", -1)])
            drafts = await self.db.news_drafts.find({"room_code": room["code"], "deleted": False, "status": "draft"}, {"_id": 0}).sort("updated_at", -1).to_list(50)
            return {"available": bool(os.environ.get("YDC_API_KEY")), "latest_search": latest, "drafts": drafts}

        @api.post("/rooms/{code}/news/search", response_model=SearchOut)
        async def search(code: str, body: NewsQuery, key: Optional[str] = None):
            room = await self.host(code, key)
            query = " ".join(body.query.split())
            if len(query) < 2 or sexual_content(query):
                raise HTTPException(400, "content_blocked")
            # Atomic lease across workers; cache repeated clicks without another paid request.
            cache_key = query.casefold() + ":" + body.language
            cached = await self.db.news_searches.find_one({"room_code": room["code"], "cache_key": cache_key, "created_ms": {"$gt": self.s.now_ms() - 600000}}, {"_id": 0}, sort=[("created_ms", -1)])
            if cached:
                return dict(cached, cached=True)
            now = self.s.now_ms()
            lease = await self.db.rooms.update_one({"code": room["code"], "$or": [{"news_search_until": {"$lt": now}}, {"news_search_until": {"$exists": False}}]}, {"$set": {"news_search_until": now + 30000}})
            if not lease.modified_count:
                raise HTTPException(429, "news_rate_limited")
            if await self.db.news_searches.count_documents({"room_code": room["code"], "created_ms": {"$gt": now - 86400000}}) >= 20:
                raise HTTPException(429, "news_daily_limit")
            try:
                results = await you_search(query, body.language)
                doc = {"id": str(uuid.uuid4()), "room_code": room["code"], "query": query, "cache_key": cache_key, "created_ms": now,
                       "searched_at": datetime.now(timezone.utc).isoformat(), "results": results, "expire_at": room["expire_at"]}
                await self.db.news_searches.insert_one(doc.copy())
                return doc
            finally:
                await self.db.rooms.update_one({"code": room["code"]}, {"$set": {"news_search_until": self.s.now_ms() + 2000}})

        @api.post("/rooms/{code}/news/drafts", response_model=DraftOut)
        async def create_draft(code: str, body: SourceInput, key: Optional[str] = None):
            room = await self.host(code, key)
            old = await self.db.news_drafts.find_one({"room_code": room["code"], "source.id": body.source_id, "deleted": False}, {"_id": 0})
            if old:
                return old
            snapshot = await self.db.news_searches.find_one({"room_code": room["code"], "results.id": body.source_id}, {"_id": 0})
            if not snapshot:
                raise HTTPException(404, "news_source_missing")
            if await self.db.news_drafts.count_documents({"room_code": room["code"], "deleted": False, "status": "draft"}) >= 50:
                raise HTTPException(409, "news_draft_limit")
            source = next(x for x in snapshot["results"] if x["id"] == body.source_id)
            fields = DraftFields(options=[{"en": "", "vi": ""} for _ in range(4)]).model_dump(exclude={"client_request_id"})
            doc = {"id": str(uuid.uuid4()), "room_code": room["code"], "fields": fields, "source": source, "deleted": False,
                   "status": "draft", "updated_at": datetime.now(timezone.utc).isoformat(), "expire_at": room["expire_at"]}
            await self.db.news_drafts.insert_one(doc.copy())
            return doc

        @api.post("/rooms/{code}/news/drafts/{draft_id}/save", response_model=OK)
        async def save_draft(code: str, draft_id: str, body: DraftFields, key: Optional[str] = None):
            room = await self.host(code, key)
            draft = await self.draft(room["code"], draft_id)
            if draft["status"] != "draft":
                raise HTTPException(409, "news_already_published")
            await self.db.news_drafts.update_one({"id": draft_id, "status": "draft", "deleted": False}, {"$set": {"fields": body.model_dump(exclude={"client_request_id"}), "updated_at": datetime.now(timezone.utc).isoformat()}})
            return OK(id=draft_id)

        @api.post("/rooms/{code}/news/drafts/{draft_id}/delete", response_model=OK)
        async def delete_draft(code: str, draft_id: str, key: Optional[str] = None):
            room = await self.host(code, key)
            draft = await self.draft(room["code"], draft_id)
            if draft["status"] != "draft":
                raise HTTPException(409, "news_already_published")
            await self.db.news_drafts.update_one({"id": draft_id, "status": "draft"}, {"$set": {"deleted": True, "updated_at": datetime.now(timezone.utc).isoformat()}})
            return OK()

        @api.post("/rooms/{code}/news/drafts/{draft_id}/publish", response_model=OK)
        async def publish(code: str, draft_id: str, body: PublishInput, key: Optional[str] = None):
            room = await self.host(code, key)
            if not body.reviewed or body.round_type != "classic":
                raise HTTPException(400, "news_review_required")
            # Serialize this room's publication; deterministic question id is an additional retry guard.
            lock = self.locks.setdefault(room["code"], asyncio.Lock())
            async with lock:
                room = await self.s.get_room(code)
                draft = await self.draft(room["code"], draft_id)
                if draft["status"] == "published":
                    return OK(id=draft["published_question_id"], duplicate=True)
                if len(room["flat"]) >= 100:
                    raise HTTPException(409, "question_limit")
                qid = str(uuid.uuid5(uuid.NAMESPACE_URL, "heckle-hint-news:" + draft_id))
                data = body.model_dump(exclude={"client_request_id", "reviewed"})
                data["text_vi"] = data["text_vi"] or data["text_en"]
                for o in data["options"]:
                    o["vi"] = o["vi"] or o["en"]
                data.update(id=qid, room_code=room["code"], custom_time=True, sources=[draft["source"]], news_draft_id=draft_id,
                            index=len(room["flat"]), expire_at=room["expire_at"], deleted=False)
                await self.db.questions.update_one({"id": qid}, {"$set": data}, upsert=True)
                if qid not in [e["qid"] for e in room["flat"]]:
                    try:
                        await self.s.t2.save_plan(room, [e["qid"] for e in room["flat"]] + [qid])
                    except Exception:
                        await self.db.questions.update_one({"id": qid}, {"$set": {"deleted": True}})
                        raise
                await self.db.news_drafts.update_one({"id": draft_id}, {"$set": {"status": "published", "published_question_id": qid, "fields": body.model_dump(exclude={"client_request_id", "reviewed"}), "updated_at": datetime.now(timezone.utc).isoformat()}})
                return OK(id=qid)
