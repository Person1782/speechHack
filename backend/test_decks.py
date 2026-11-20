"""Deck integration tests against a real, isolated local MongoDB database."""
import importlib
import os
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient


def uid():
    return uuid.uuid4().hex


@pytest.fixture(scope="module")
def api():
    database = "heckle_deck_test_" + uid()
    previous = {key: os.environ.get(key) for key in ("MONGO_URL", "DB_NAME")}
    os.environ["MONGO_URL"] = "mongodb://127.0.0.1:27017"
    os.environ["DB_NAME"] = database
    sys.path.insert(0, str(Path(__file__).parent))
    server = importlib.import_module("server")
    with TestClient(server.app) as client:
        yield client
    with MongoClient("mongodb://127.0.0.1:27017") as mongo:
        mongo.drop_database(database)
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def classic():
    return {"round_type": "classic", "text_en": "What is two plus two?", "text_vi": "Hai cộng hai bằng mấy?",
            "options": [{"en": str(x), "vi": str(x)} for x in (1, 2, 3, 4)], "correct_index": 3,
            "setup_line": "Private setup", "punchline": "Private punchline", "notes": {"opener": "Private note"}, "time_limit_s": 15}


def poll():
    return {"round_type": "poll", "text_en": "What is the worst excuse for being late?", "text_vi": "Lý do đi trễ tệ nhất là gì?", "options": [], "time_limit_s": 30}


def create_deck(api, owner=None, **changes):
    owner = owner or uid()
    body = {"owner_key": owner, "name": "My special set", "description": "Private prep", "client_request_id": uid(), "questions": [classic(), poll()], **changes}
    response = api.post("/api/decks", json=body)
    assert response.status_code == 200, response.text
    return owner, body, response.json()["deck"]


def create_room(api, **changes):
    response = api.post("/api/rooms", json={"host_name": "Stage Name", "venue_name": "Quiz Bar", **changes})
    assert response.status_code == 200, response.text
    return response.json()


def test_library_private_and_reusable(api):
    owner, body, deck = create_deck(api)
    assert api.get("/api/decks").status_code == 403
    assert api.get("/api/question-bank").status_code == 403
    assert api.get("/api/decks", params={"owner_key": uid()}).json() == {"decks": []}
    listed = api.get("/api/decks", params={"owner_key": owner}).json()["decks"]
    assert len(listed) == 1 and listed[0]["id"] == deck["id"]
    assert "owner_hash" not in listed[0] and "owner_key" not in listed[0]
    assert listed[0]["questions"][0]["notes"]["opener"] == "Private note"
    assert [q["round_type"] for q in listed[0]["questions"]] == ["classic", "poll"]
    response = api.post(f"/api/decks/{deck['id']}", json={**body, "owner_key": uid(), "client_request_id": uid()})
    assert response.status_code == 404


def test_create_and_edit_are_idempotent(api):
    owner, body, deck = create_deck(api)
    repeat = api.post("/api/decks", json=body)
    assert repeat.json()["deck"]["id"] == deck["id"]
    edited = {**body, "name": "Revised set", "questions": [poll(), classic()], "client_request_id": uid()}
    first = api.post(f"/api/decks/{deck['id']}", json=edited)
    second = api.post(f"/api/decks/{deck['id']}", json=edited)
    assert first.json() == second.json()
    assert first.json()["deck"]["questions"][0]["round_type"] == "poll"


def test_custom_deck_order_and_room_snapshot(api):
    owner, body, deck = create_deck(api)
    room = create_room(api, deck_id=deck["id"], owner_key=owner)
    original = api.get(f"/api/rooms/{room['code']}/questions", params={"key": room["host_key"]}).json()["questions"]
    assert [q["round_type"] for q in original] == ["classic", "poll"]
    assert original[0]["id"] != deck["questions"][0]["id"]
    edited = {**body, "client_request_id": uid(), "questions": [poll()]}
    assert api.post(f"/api/decks/{deck['id']}", json=edited).status_code == 200
    after = api.get(f"/api/rooms/{room['code']}/questions", params={"key": room["host_key"]}).json()["questions"]
    assert [q["id"] for q in original] == [q["id"] for q in after]
    rejected = api.post("/api/rooms", json={"deck_id": deck["id"], "owner_key": uid()})
    assert rejected.status_code == 404
    assert api.get(f"/api/rooms/{room['code']}/questions").status_code == 403


def test_save_room_questions_as_new_deck_requires_host(api):
    room = create_room(api)
    body = {"owner_key": uid(), "name": "Tonight's set", "client_request_id": uid()}
    path = f"/api/rooms/{room['code']}/save-deck"
    assert api.post(path, json=body).status_code == 403
    response = api.post(path, params={"key": room["host_key"]}, json=body)
    assert response.status_code == 200, response.text
    assert len(response.json()["deck"]["questions"]) == 3
    again = api.post(path, params={"key": room["host_key"]}, json=body)
    assert again.json()["deck"]["id"] == response.json()["deck"]["id"]


def test_seed_library_and_validation(api):
    bank = api.get("/api/question-bank", params={"owner_key": uid()}).json()["questions"]
    assert len(bank) >= 30
    assert {q["round_type"] for q in bank} == {"classic", "poll"}
    assert len({q["id"] for q in bank}) == len(bank)
    base = {"owner_key": uid(), "name": "Set", "client_request_id": uid(), "questions": [classic()]}
    for change in [{"name": "   "}, {"questions": []}, {"questions": [{**classic(), "options": []}]}, {"questions": [{**classic(), "correct_index": 7}]}]:
        assert api.post("/api/decks", json={**base, **change}).status_code == 422
    _, _, deck = create_deck(api, questions=[{**classic(), "text_vi": "", "options": [{"en": str(x)} for x in range(4)]}])
    assert deck["questions"][0]["text_vi"] == deck["questions"][0]["text_en"]
    assert all(o["en"] == o["vi"] for o in deck["questions"][0]["options"])


def test_poll_deck_opens_existing_private_review_flow(api):
    owner, _, deck = create_deck(api, questions=[poll()])
    room = create_room(api, deck_id=deck["id"], owner_key=owner)
    path = f"/api/rooms/{room['code']}"
    for _ in range(3):
        response = api.post(path + "/host/next", params={"key": room["host_key"]}, json={"client_request_id": uid()})
        assert response.status_code == 200, response.text
    state = api.get(path + "/state", params={"role": "host", "key": room["host_key"]}).json()
    assert state["phase"] == "poll_open"
    assert state["question_total"] == 1
    assert api.post(path + "/host/next", params={"key": room["host_key"]}, json={"client_request_id": uid()}).status_code == 200
    public = api.get(path + "/state", params={"role": "screen"}).json()
    assert public["phase"] == "poll_review"
    assert "host_key" not in str(public) and "Private note" not in str(public)
