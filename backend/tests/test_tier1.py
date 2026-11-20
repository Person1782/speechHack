"""Tier 1 backend tests. Run: cd /app/backend && python -m pytest tests -q
API tests hit the running server (supervisor) at localhost:8001."""
import json
import time
import uuid

import pytest
import requests

from game import (build_round_plan, calc_points, gen_code, rank_teams, recompute_scores, sim_choice, streak_bonus)
from moderation import check_text

BASE = "http://localhost:8001/api"


# ---------------------------------------------------------------- unit
def test_code_letters():
    for _ in range(500):
        c = gen_code()
        assert len(c) == 4 and c.isalpha() and c.isupper() and "I" not in c and "O" not in c


def test_scoring_formula():
    assert calc_points(0, 20000) == 1000
    assert calc_points(20000, 20000) == 500
    assert calc_points(10000, 20000) == 750
    assert calc_points(5000, 20000) == round(1000 * (1 - (5000 / 20000) / 2))
    assert calc_points(99999, 20000) == 500


def test_streak_bonus():
    assert [streak_bonus(s) for s in range(0, 9)] == [0, 0, 100, 200, 300, 400, 500, 500, 500]


def test_recompute_streaks_and_fast_wrong():
    a = lambda c, p=800, ms=3000, fw=False: {"is_correct": c, "points_pending": p, "ms_taken": ms, "fast_wrong": fw}
    by_q = {"q1": {"A": a(True), "B": a(False, 0, 1000, True)},
            "q2": {"A": a(True), "B": a(True)},
            "q3": {"A": a(True)}}
    stats, awarded = recompute_scores(["A", "B"], ["q1", "q2", "q3"], by_q)
    assert awarded["q1"]["A"] == 800 and awarded["q2"]["A"] == 900 and awarded["q3"]["A"] == 1000
    assert stats["A"]["brain_points"] == 2700 and stats["A"]["streak"] == 3
    assert stats["B"]["brain_points"] == 800 and stats["B"]["streak"] == 0 and stats["B"]["fast_wrong_count"] == 1


def test_tiebreak_lower_time_wins():
    teams = [{"id": "x", "brain_points": 1000, "laugh_points": 0, "total_ms": 9000, "number": 1},
             {"id": "y", "brain_points": 1000, "laugh_points": 0, "total_ms": 4000, "number": 2}]
    assert [t["id"] for t in rank_teams(teams)] == ["y", "x"]


def test_round_plan_skips_unbuilt():
    qs = [{"id": str(i), "index": i, "round_type": rt} for i, rt in enumerate(["classic", "poll", "classic", "decoy", "classic"])]
    plan = build_round_plan("demo", qs)
    assert plan and all(q != "1" for r in plan for q in r["question_ids"])


def test_sim_choice_rate():
    import random
    rng = random.Random(1)
    n = sum(sim_choice(2, 4, rng) == 2 for _ in range(2000))
    assert 1000 < n < 1400


def test_moderation():
    assert check_text("Phở Real")[0] == "allow"
    assert check_text("Chợ Lớn Crew")[0] == "allow"
    assert check_text("fuck this")[0] == "block"
    assert check_text("đội đéo biết")[0] == "block"
    assert check_text("call 0903 123 456")[0] == "block"
    assert check_text("me@mail.com")[0] == "block"
    assert check_text("visit www.spam.com")[0] == "flag"
    assert check_text("Team Shit")[0] == "flag"


# ---------------------------------------------------------------- api
def mk_room(**kw):
    r = requests.post(f"{BASE}/rooms", json={"host_name": "Test Comic", "venue_name": "Test Bar", **kw})
    r.raise_for_status()
    return r.json()


def state(code, role, **params):
    return requests.get(f"{BASE}/rooms/{code}/state", params={"role": role, **params}).json()


def host(code, key, action, **body):
    return requests.post(f"{BASE}/rooms/{code}/host/{action}", params={"key": key}, json={"client_request_id": uuid.uuid4().hex, **body})


def join(code, name, dev=None):
    dev = dev or uuid.uuid4().hex
    r = requests.post(f"{BASE}/rooms/{code}/join", json={"device_id": dev, "name": name, "emoji": "🍜", "roast_level": "mild"})
    r.raise_for_status()
    return dev, r.json()["team_id"]


def to_question_open(code, key):
    for _ in range(3):
        host(code, key, "next")  # lobby -> cold_open -> round_intro -> question_open
    s = state(code, "host", key=key)
    assert s["phase"] == "question_open"
    return s


def test_403_without_key():
    room = mk_room()
    code = room["code"]
    assert requests.get(f"{BASE}/rooms/{code}/state", params={"role": "host"}).status_code == 403
    for action in ("next", "reset", "blackout", "load_demo", "freeze", "add_time"):
        assert requests.post(f"{BASE}/rooms/{code}/host/{action}", json={}).status_code == 403
        assert requests.post(f"{BASE}/rooms/{code}/host/{action}", params={"key": "wrong"}, json={}).status_code == 403


def test_unknown_room_404():
    assert requests.get(f"{BASE}/rooms/ZZZZ/public").status_code in (404, 200)
    assert requests.get(f"{BASE}/rooms/QQQ1/state").status_code == 404


def test_full_classic_flow_and_spoilers():
    room = mk_room()
    code, key = room["code"], room["host_key"]
    devs = [join(code, f"Team {n}") for n in ("Alpha", "Bravo", "Charlie")]
    s = to_question_open(code, key)
    q = s["host"]["question"]
    correct = q["correct_index"]
    # Spoiler check on raw JSON before reveal
    for role, extra in (("screen", {}), ("player", {"device": devs[0][0]})):
        raw = requests.get(f"{BASE}/rooms/{code}/state", params={"role": role, **extra}).text
        for banned in ("correct_index", "punchline", "notes", "setup_line", "host_key", "secret_word\": \"x", "fake_explanations", "hint_joke"):
            if banned == "secret_word\": \"x":
                continue
            assert banned not in raw, (role, banned)
        assert "device_id" not in raw
    # player sees own secret word, never others'
    p0 = state(code, "player", device=devs[0][0])
    assert p0["me"]["secret_word"]
    raw_screen = requests.get(f"{BASE}/rooms/{code}/state", params={"role": "screen"}).text
    assert "secret_word" not in raw_screen
    # answers: team0 correct, team1 wrong, team2 correct; idempotent retry
    crid = uuid.uuid4().hex
    body = {"device_id": devs[0][0], "question_id": q["id"], "option_index": correct, "client_request_id": crid}
    assert requests.post(f"{BASE}/rooms/{code}/answer", json=body).json()["ok"]
    assert requests.post(f"{BASE}/rooms/{code}/answer", json=body).json()["duplicate"]
    # second answer with new crid does not change
    r2 = requests.post(f"{BASE}/rooms/{code}/answer", json={**body, "option_index": (correct + 1) % 4, "client_request_id": uuid.uuid4().hex}).json()
    assert r2["answer"]["option_index"] == correct
    requests.post(f"{BASE}/rooms/{code}/answer", json={"device_id": devs[1][0], "question_id": q["id"], "option_index": (correct + 1) % 4, "client_request_id": uuid.uuid4().hex})
    # refresh mid-question: answer persists
    assert state(code, "player", device=devs[0][0])["my_answer"]["option_index"] == correct
    requests.post(f"{BASE}/rooms/{code}/answer", json={"device_id": devs[2][0], "question_id": q["id"], "option_index": correct, "client_request_id": uuid.uuid4().hex})
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "question_locked"  # all answered -> auto lock
    raw = json.dumps(s)
    assert "counts" not in raw and "correct_index" not in raw and "leaderboard" not in raw
    hs = state(code, "host", key=key)
    assert hs["host"]["distribution"] and sum(d["count"] for d in hs["host"]["distribution"]) == 3
    host(code, key, "next")  # reveal
    s = state(code, "screen")
    assert s["phase"] == "reveal" and s["reveal"]["correct_index"] == correct
    p = state(code, "player", device=devs[0][0])
    assert p["my_result"]["correct"] and 500 <= p["my_result"]["points"] <= 1000
    pw = state(code, "player", device=devs[1][0])
    assert not pw["my_result"]["correct"] and pw["my_result"]["points"] == 0
    # version polling
    v = s["version"]
    assert state(code, "screen", since_version=v)["unchanged"] is True


def test_timer_lock_and_late_join():
    room = mk_room()
    code, key = room["code"], room["host_key"]
    join(code, "Early Birds")
    s = to_question_open(code, key)
    late_dev, _ = join(code, "Latecomers")
    p = state(code, "player", device=late_dev)
    assert p["me"]["eligible"] is False
    r = requests.post(f"{BASE}/rooms/{code}/answer", json={"device_id": late_dev, "question_id": s["question"]["id"], "option_index": 0, "client_request_id": uuid.uuid4().hex})
    assert r.status_code == 409
    # shorten: freeze/unfreeze works and +10s extends
    ends = state(code, "host", key=key)["phase_ends_at"]
    host(code, key, "add_time")
    assert state(code, "host", key=key)["phase_ends_at"] == ends + 10000
    host(code, key, "freeze")
    assert state(code, "screen")["frozen"] is True
    host(code, key, "freeze")
    assert state(code, "screen")["frozen"] is False


def test_flagged_name_placeholder():
    room = mk_room()
    code, key = room["code"], room["host_key"]
    _, tid = join(code, "Shit Happens")
    s = state(code, "screen")
    t = next(t for t in s["teams"] if t["id"] == tid)
    assert t["name"] is None and "Shit" not in json.dumps(s)
    host(code, key, "team", op="approve_name", team_id=tid)
    s = state(code, "screen")
    assert next(t for t in s["teams"] if t["id"] == tid)["name"] == "Shit Happens"
    host(code, key, "team", op="hide", team_id=tid)
    assert all(t["id"] != tid for t in state(code, "screen")["teams"])


def test_demo_and_simulate_crowd():
    room = mk_room()
    code, key = room["code"], room["host_key"]
    host(code, key, "load_demo")
    s = state(code, "screen")
    assert s["team_count"] == 8
    s = to_question_open(code, key)
    deadline = time.time() + 9
    while time.time() < deadline:
        s = state(code, "screen")
        if s["phase"] == "question_locked":
            break
        time.sleep(0.5)
    assert s["phase"] == "question_locked" and s["answered_count"] == 8


def test_blackout_hides_names():
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    host(code, key, "blackout", value=True)
    s = state(code, "screen")
    assert all(t["name"] is None for t in s["teams"]) and s["fun_facts"] == []
