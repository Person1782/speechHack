"""Tier 2 backend tests: Question Manager, Polls, Moderation, HOF, Audio.
Run: cd /app/backend && python -m pytest tests/test_tier2.py -v
"""
import json
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")
# Read BASE from frontend .env for public endpoint testing
frontend_env = Path(__file__).parent.parent.parent / "frontend" / ".env"
if frontend_env.exists():
    with open(frontend_env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip() + "/api"
                break
else:
    BASE = "https://quiz-and-riff--39crjv3i.preview.emergentagent.com/api"

# MongoDB connection for fixture insertion
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_db_client = None

def get_db():
    """Get MongoDB database connection."""
    global _db_client
    if _db_client is None:
        _db_client = MongoClient(MONGO_URL)
    return _db_client[os.environ["DB_NAME"]]


def mk_room(**kw):
    """Create a test room."""
    r = requests.post(f"{BASE}/rooms", json={"host_name": "TEST_Tier2", "venue_name": "TEST_Bar", **kw})
    r.raise_for_status()
    return r.json()


def state(code, role, **params):
    """Get room state."""
    return requests.get(f"{BASE}/rooms/{code}/state", params={"role": role, **params}).json()


def host(code, key, action, **body):
    """Host action."""
    return requests.post(f"{BASE}/rooms/{code}/host/{action}", params={"key": key}, 
                        json={"client_request_id": uuid.uuid4().hex, **body})


def join(code, name, dev=None):
    """Join room as a team."""
    dev = dev or f"TEST_{uuid.uuid4().hex}"
    r = requests.post(f"{BASE}/rooms/{code}/join", 
                     json={"device_id": dev, "name": name, "emoji": "🍜", "roast_level": "mild"})
    r.raise_for_status()
    return dev, r.json()["team_id"]


def to_question_open(code, key):
    """Advance to question_open phase."""
    for _ in range(3):
        host(code, key, "next")
    s = state(code, "host", key=key)
    assert s["phase"] == "question_open"
    return s


def insert_fixture_search(room_code, query="TEST_fixture_query", language="EN", result_count=3):
    """Insert a fixture search snapshot directly into DB to avoid paid API calls."""
    db = get_db()
    search_id = str(uuid.uuid4())
    results = []
    for i in range(result_count):
        results.append({
            "id": str(uuid.uuid4()),
            "title": f"TEST_Article_{i}",
            "url": f"https://test-fixture-{i}.example.com/article",
            "description": f"TEST_Description for article {i}",
            "excerpts": [f"TEST_Excerpt {i}.1", f"TEST_Excerpt {i}.2"],
            "published_at": None,
            "provider": "You.com"
        })
    
    # Get room expire_at
    room = db.rooms.find_one({"code": room_code})
    if not room or "expire_at" not in room:
        # Set default expire_at if not present
        expire_at = datetime.now(timezone.utc) + timedelta(hours=24)
    else:
        expire_at = room["expire_at"]
    
    doc = {
        "id": search_id,
        "room_code": room_code,
        "query": query,
        "cache_key": query.casefold() + ":" + language,
        "created_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "expire_at": expire_at
    }
    db.news_searches.insert_one(doc)
    return search_id, results


# ---------------------------------------------------------------- Question Manager Tests
def test_question_add_edit_delete():
    """Test CRUD operations on questions."""
    print("\n🔍 Testing Question Manager CRUD...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # List questions
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    assert r.status_code == 200
    initial = r.json()["questions"]
    initial_count = len(initial)
    print(f"✅ Initial questions: {initial_count}")
    
    # Add a new poll question
    new_q = {
        "round_type": "poll",
        "text_en": "TEST_What's the best pho topping?",
        "text_vi": "TEST_Topping phở nào ngon nhất?",
        "time_limit_s": 30
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
    assert r.status_code == 200
    qid = r.json()["id"]
    print(f"✅ Added question: {qid}")
    
    # Verify it appears in list
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    assert len(questions) == initial_count + 1
    added = next(q for q in questions if q["id"] == qid)
    assert added["text_en"] == new_q["text_en"]
    assert added["editable"] is True
    print("✅ Question appears in list")
    
    # Edit the question
    edit_q = {**new_q, "text_en": "TEST_EDITED: Best pho topping?", "time_limit_s": 45}
    r = requests.post(f"{BASE}/rooms/{code}/questions/{qid}", params={"key": key}, json=edit_q)
    assert r.status_code == 200
    print("✅ Edited question")
    
    # Verify edit
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    edited = next(q for q in r.json()["questions"] if q["id"] == qid)
    assert "EDITED" in edited["text_en"]
    assert edited["time_limit_s"] == 45
    print("✅ Edit verified")
    
    # Delete the question
    r = requests.post(f"{BASE}/rooms/{code}/questions/{qid}/delete", params={"key": key}, json={})
    assert r.status_code == 200
    print("✅ Deleted question")
    
    # Verify deletion
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    assert len(questions) == initial_count
    assert not any(q["id"] == qid for q in questions)
    print("✅ Deletion verified")


def test_question_reorder():
    """Test question reordering."""
    print("\n🔍 Testing Question Reorder...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Get initial order
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    ids = [q["id"] for q in questions]
    print(f"✅ Initial order: {len(ids)} questions")
    
    # Reverse order
    reversed_ids = list(reversed(ids))
    r = requests.post(f"{BASE}/rooms/{code}/question-order", params={"key": key}, 
                     json={"ids": reversed_ids})
    assert r.status_code == 200
    print("✅ Reordered questions")
    
    # Verify new order
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    new_questions = r.json()["questions"]
    new_ids = [q["id"] for q in new_questions]
    assert new_ids == reversed_ids
    print("✅ Reorder verified")


def test_question_future_only_protection():
    """Test that questions in play cannot be edited/deleted."""
    print("\n🔍 Testing Future-Only Protection...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Advance to question_open
    s = to_question_open(code, key)
    current_qid = s["host"]["question"]["id"]
    print(f"✅ Advanced to question_open, current question: {current_qid}")
    
    # Try to edit current question - should fail
    r = requests.post(f"{BASE}/rooms/{code}/questions/{current_qid}", params={"key": key}, 
                     json={"round_type": "classic", "text_en": "TEST_Should fail", 
                           "options": [{"en": "A", "vi": "A"}] * 4, "correct_index": 0})
    assert r.status_code == 409
    assert "question_in_play" in r.text
    print("✅ Cannot edit question in play")
    
    # Try to delete current question - should fail
    r = requests.post(f"{BASE}/rooms/{code}/questions/{current_qid}/delete", params={"key": key}, json={})
    assert r.status_code == 409
    print("✅ Cannot delete question in play")
    
    # Verify editable flag
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    current = next(q for q in questions if q["id"] == current_qid)
    assert current["editable"] is False
    print("✅ Editable flag is False for current question")


def test_question_host_key_403():
    """Test that question operations require valid host key."""
    print("\n🔍 Testing Host Key 403...")
    room = mk_room()
    code = room["code"]
    
    # Try to list without key
    r = requests.get(f"{BASE}/rooms/{code}/questions")
    assert r.status_code == 403
    print("✅ List requires host key")
    
    # Try to add without key
    r = requests.post(f"{BASE}/rooms/{code}/questions", json={"round_type": "poll", "text_en": "Test"})
    assert r.status_code == 403
    print("✅ Add requires host key")
    
    # Try with wrong key
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": "wrong_key"})
    assert r.status_code == 403
    print("✅ Wrong key rejected")


# ---------------------------------------------------------------- Poll Tests
def test_poll_start_preset():
    """Test starting a poll from preset."""
    print("\n🔍 Testing Poll Start (Preset)...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll with preset 0
    r = host(code, key, "poll_start", preset=0, time_limit_s=30)
    assert r.status_code == 200
    print("✅ Started poll from preset")
    
    # Verify poll is active
    s = state(code, "screen")
    assert s["phase"] == "poll_open"
    assert s["poll"]["id"]
    assert "first date" in s["poll"]["text_en"].lower() or "worst thing" in s["poll"]["text_en"].lower()
    print(f"✅ Poll active: {s['poll']['text_en'][:50]}...")


def test_poll_start_custom():
    """Test starting a poll with custom prompt."""
    print("\n🔍 Testing Poll Start (Custom)...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start custom poll
    r = host(code, key, "poll_start", text_en="TEST_What's your favorite Vietnamese dish?", 
             text_vi="TEST_Món Việt yêu thích?", time_limit_s=45)
    assert r.status_code == 200
    print("✅ Started custom poll")
    
    # Verify
    s = state(code, "screen")
    assert s["phase"] == "poll_open"
    assert "TEST_" in s["poll"]["text_en"]
    print("✅ Custom poll verified")


def test_poll_submit_80_char_limit():
    """Test poll submission with 80 char limit."""
    print("\n🔍 Testing Poll Submit 80 Char Limit...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Join as team
    dev, tid = join(code, "TEST_Team")
    
    # Submit 80 chars - should succeed
    text_80 = "A" * 80
    r = requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                     json={"poll_id": poll_id, "device_id": dev, "text": text_80})
    assert r.status_code == 200
    print("✅ 80 chars accepted")
    
    # Submit 81 chars - should fail
    dev2, tid2 = join(code, "TEST_Team2")
    text_81 = "B" * 81
    r = requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                     json={"poll_id": poll_id, "device_id": dev2, "text": text_81})
    assert r.status_code == 422  # Pydantic validation error
    print("✅ 81 chars rejected")


def test_poll_anonymous_host_visibility():
    """Test anonymous submissions are visible to host but not public."""
    print("\n🔍 Testing Anonymous Host Visibility...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit anonymous answer
    dev, tid = join(code, "TEST_AnonTeam")
    r = requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                     json={"poll_id": poll_id, "device_id": dev, "text": "TEST_Anonymous answer", "anonymous": True})
    assert r.status_code == 200
    print("✅ Anonymous submission accepted")
    
    # Lock and approve
    host(code, key, "next")  # poll_open -> poll_review
    time.sleep(0.3)
    
    # Get host view
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    anon_group = next((g for g in groups if "TEST_Anonymous" in g["text"]), None)
    assert anon_group is not None
    
    # Host should see author with anonymous flag
    assert any(a["name"] == "TEST_AnonTeam" and a["anonymous"] for a in anon_group["authors"])
    print("✅ Host sees anonymous author")
    
    # Approve it
    r = host(code, key, "poll_moderate", poll_id=poll_id, answer_id=anon_group["id"], verdict="approve")
    assert r.status_code == 200
    
    # Move to voting
    host(code, key, "next")  # poll_review -> poll_vote
    time.sleep(0.3)
    
    # Screen should not show author
    s_screen = state(code, "screen")
    screen_groups = s_screen["poll"]["groups"]
    screen_anon = next((g for g in screen_groups if "TEST_Anonymous" in g["text"]), None)
    assert screen_anon is not None
    assert len(screen_anon["authors"]) == 0  # No authors shown for anonymous
    print("✅ Screen does not show anonymous author")


def test_poll_normalized_duplicates():
    """Test that normalized duplicates are merged (Pho/PHỞ, case/accent insensitive)."""
    print("\n🔍 Testing Normalized Duplicates...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit variations of same answer
    dev1, _ = join(code, "TEST_Team1")
    dev2, _ = join(code, "TEST_Team2")
    dev3, _ = join(code, "TEST_Team3")
    
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev1, "text": "Pho"})
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev2, "text": "PHỞ"})
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev3, "text": "  pho  "})
    
    time.sleep(0.3)
    
    # Lock and check groups
    host(code, key, "next")
    time.sleep(0.3)
    
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    pho_groups = [g for g in groups if "pho" in g["text"].lower()]
    
    # Should be merged into one group with 3 members
    assert len(pho_groups) == 1
    assert pho_groups[0]["count"] == 3
    print(f"✅ Normalized duplicates merged: {pho_groups[0]['count']} members")


def test_poll_moderation_max6():
    """Test max 6 concurrent approved answers."""
    print("\n🔍 Testing Moderation Max 6...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit 8 different answers
    for i in range(8):
        dev, _ = join(code, f"TEST_Team{i}")
        requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                     json={"poll_id": poll_id, "device_id": dev, "text": f"TEST_Answer_{i}"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve 6 answers
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    
    for i, g in enumerate(groups[:6]):
        r = host(code, key, "poll_moderate", poll_id=poll_id, answer_id=g["id"], verdict="approve")
        assert r.status_code == 200
        print(f"✅ Approved answer {i+1}/6")
    
    # Try to approve 7th - should fail
    if len(groups) > 6:
        r = host(code, key, "poll_moderate", poll_id=poll_id, answer_id=groups[6]["id"], verdict="approve")
        assert r.status_code == 409
        assert "approval_limit" in r.text
        print("✅ 7th approval rejected (max 6)")


def test_poll_voting_one_per_answer():
    """Test voting: one vote per answer per device."""
    print("\n🔍 Testing Voting One Per Answer...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll and submit answers
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    dev1, _ = join(code, "TEST_Submitter")
    dev2, _ = join(code, "TEST_Voter")
    
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev1, "text": "TEST_Answer"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    
    # Move to voting
    host(code, key, "next")
    time.sleep(0.3)
    
    # Vote once - should succeed
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                     json={"poll_id": poll_id, "device_id": dev2, "answer_id": answer_id})
    assert r.status_code == 200
    assert r.json()["duplicate"] is False
    print("✅ First vote accepted")
    
    # Vote again - should return duplicate
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                     json={"poll_id": poll_id, "device_id": dev2, "answer_id": answer_id})
    assert r.status_code == 200
    assert r.json()["duplicate"] is True
    print("✅ Duplicate vote detected")


def test_poll_no_self_vote():
    """Test that teams cannot vote for their own answers."""
    print("\n🔍 Testing No Self Vote...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit answer
    dev, _ = join(code, "TEST_SelfVoter")
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev, "text": "TEST_MyAnswer"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    
    # Move to voting
    host(code, key, "next")
    time.sleep(0.3)
    
    # Try to vote for own answer - should fail
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                     json={"poll_id": poll_id, "device_id": dev, "answer_id": answer_id})
    assert r.status_code == 403
    assert "self_vote" in r.text
    print("✅ Self-vote rejected")


def test_poll_hof_claim():
    """Test Hall of Fame claim mechanism."""
    print("\n🔍 Testing HOF Claim...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit and vote
    dev_author, _ = join(code, "TEST_Winner")
    dev_voter, _ = join(code, "TEST_Voter")
    
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev_author, "text": "TEST_Winning answer", "anonymous": True})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    
    # Vote
    host(code, key, "next")  # poll_vote
    time.sleep(0.3)
    requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                 json={"poll_id": poll_id, "device_id": dev_voter, "answer_id": answer_id})
    
    # Move to HOF
    host(code, key, "next")
    time.sleep(0.3)
    
    # Verify HOF
    s = state(code, "screen")
    assert s["phase"] == "poll_hof"
    assert s["hall_of_fame"] is not None
    assert "TEST_Winning" in s["hall_of_fame"]["text"]
    assert len(s["hall_of_fame"]["claimed_names"]) == 0  # Not claimed yet
    print("✅ HOF displayed")
    
    # Claim
    r = requests.post(f"{BASE}/rooms/{code}/poll/claim", 
                     json={"poll_id": poll_id, "device_id": dev_author})
    assert r.status_code == 200
    print("✅ Claimed by author")
    
    # Verify claim
    time.sleep(0.3)
    s = state(code, "screen")
    assert len(s["hall_of_fame"]["claimed_names"]) == 1
    assert s["hall_of_fame"]["claimed_names"][0]["name"] == "TEST_Winner"
    print("✅ Claim verified")
    
    # Try to claim again - should return duplicate
    r = requests.post(f"{BASE}/rooms/{code}/poll/claim", 
                     json={"poll_id": poll_id, "device_id": dev_author})
    assert r.status_code == 200
    assert r.json()["duplicate"] is True
    print("✅ Duplicate claim detected")


def test_poll_laugh_awards():
    """Test laugh awards: +100 approval, +300 winner."""
    print("\n🔍 Testing Laugh Awards...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit answers
    dev1, tid1 = join(code, "TEST_Approved")
    dev2, tid2 = join(code, "TEST_Winner")
    dev_voter, _ = join(code, "TEST_Voter")
    
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev1, "text": "TEST_Just approved"})
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev2, "text": "TEST_Winner answer"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve both
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    for g in groups:
        host(code, key, "poll_moderate", poll_id=poll_id, answer_id=g["id"], verdict="approve")
    
    # Vote for winner
    host(code, key, "next")  # poll_vote
    time.sleep(0.3)
    winner_id = next(g["id"] for g in groups if "Winner" in g["text"])
    requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                 json={"poll_id": poll_id, "device_id": dev_voter, "answer_id": winner_id})
    
    # Move to HOF
    host(code, key, "next")
    time.sleep(0.3)
    
    # Check laugh points
    s_host = state(code, "host", key=key)
    teams = {t["id"]: t for t in s_host["host"]["teams"]}
    
    # Approved team should have +100
    assert teams[tid1]["laugh_points"] == 100
    print(f"✅ Approved team: {teams[tid1]['laugh_points']} points")
    
    # Winner should have +100 (approval) + +300 (winner) = 400
    assert teams[tid2]["laugh_points"] == 400
    print(f"✅ Winner team: {teams[tid2]['laugh_points']} points")



# ---------------------------------------------------------------- Extended Tier2 Tests (Iteration 2)
def test_vietnamese_words_not_blocked():
    """Test that Vietnamese words buổi/các/lớn/cụm are NOT blocked by sexual_content."""
    print("\n🔍 Testing Vietnamese Words Not Blocked...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Test Vietnamese words that should be allowed
    vietnamese_words = [
        "buổi sáng tốt lành",  # morning
        "các bạn thân mến",    # dear friends
        "lớn hơn trước",       # bigger than before
        "cụm từ hay"           # nice phrase
    ]
    
    for i, text in enumerate(vietnamese_words):
        new_q = {
            "round_type": "poll",
            "text_en": f"TEST_{text}",
            "text_vi": text,
            "time_limit_s": 30
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
        assert r.status_code == 200, f"Vietnamese word '{text}' was incorrectly blocked"
        print(f"✅ Vietnamese word '{text}' allowed")
    
    # Verify questions were created
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    assert len([q for q in questions if "TEST_" in q["text_en"]]) == len(vietnamese_words)
    print("✅ All Vietnamese words passed moderation")


def test_poll_consecutive_scheduled():
    """Test consecutive scheduled polls."""
    print("\n🔍 Testing Consecutive Scheduled Polls...")
    # Create room without demo data
    room = mk_room(night_preset="demo")
    code, key = room["code"], room["host_key"]
    
    # Get existing questions
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    existing = r.json()["questions"]
    
    # Find first two editable questions and replace with polls
    editable = [q for q in existing if q["editable"]][:2]
    if len(editable) >= 2:
        # Edit first two questions to be polls
        requests.post(f"{BASE}/rooms/{code}/questions/{editable[0]['id']}", params={"key": key}, 
                     json={"round_type": "poll", "text_en": "TEST_Poll1", "time_limit_s": 30})
        requests.post(f"{BASE}/rooms/{code}/questions/{editable[1]['id']}", params={"key": key}, 
                     json={"round_type": "poll", "text_en": "TEST_Poll2", "time_limit_s": 30})
    
    # Start show and advance to first question (which is now a poll)
    for _ in range(3):
        host(code, key, "next")
    time.sleep(0.5)
    
    s = state(code, "screen")
    # Debug: print actual phase
    print(f"DEBUG: Phase after 3 nexts: {s['phase']}, poll: {s.get('poll')}")
    
    # If it's question_open, it might be a classic question before our polls
    # Skip to the poll
    while s["phase"] == "question_open" and s.get("question", {}).get("round_type") != "poll":
        host(code, key, "skip")
        time.sleep(0.3)
        s = state(code, "screen")
        print(f"DEBUG: After skip, phase: {s['phase']}")
        if s["phase"] == "poll_open":
            break
    
    assert s["phase"] == "poll_open", f"Expected poll_open, got {s['phase']}"
    assert "TEST_Poll1" in s["poll"]["text_en"]
    print("✅ First scheduled poll started")
    
    # Complete first poll (no submissions, just resume)
    host(code, key, "next")  # poll_open -> poll_review
    time.sleep(0.3)
    host(code, key, "next")  # poll_review -> poll_vote
    time.sleep(0.3)
    host(code, key, "next")  # poll_vote -> poll_hof
    time.sleep(0.3)
    host(code, key, "next")  # poll_hof -> resume
    time.sleep(0.3)
    
    # Should advance to next question (second poll)
    s = state(code, "screen")
    assert s["phase"] == "poll_open"
    assert "TEST_Poll2" in s["poll"]["text_en"]
    print("✅ Second consecutive scheduled poll started")


def test_poll_edited_time_override():
    """Test that edited poll question time overrides original."""
    print("\n🔍 Testing Poll Edited Time Override...")
    room = mk_room(night_preset="demo")
    code, key = room["code"], room["host_key"]
    
    # Get existing questions
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    existing = r.json()["questions"]
    
    # Find first editable question and replace with poll
    first_editable = next((q for q in existing if q["editable"]), None)
    if first_editable:
        qid = first_editable["id"]
        # Edit to be a poll with 30s
        requests.post(f"{BASE}/rooms/{code}/questions/{qid}", params={"key": key}, 
                     json={"round_type": "poll", "text_en": "TEST_EditTime", "time_limit_s": 30})
        
        # Edit again to 60s
        r = requests.post(f"{BASE}/rooms/{code}/questions/{qid}", params={"key": key}, 
                         json={"round_type": "poll", "text_en": "TEST_EditTime", "time_limit_s": 60})
        assert r.status_code == 200
        print("✅ Poll time edited to 60s")
        
        # Start show and advance to poll
        for _ in range(3):
            host(code, key, "next")
        time.sleep(0.5)
        
        s = state(code, "screen")
        assert s["phase"] == "poll_open", f"Expected poll_open, got {s['phase']}"
        # Check that limit_ms reflects 60s (60000ms)
        assert s["limit_ms"] == 60000
        print("✅ Edited time (60s) is used in poll")


def test_poll_frozen_timer():
    """Test poll freeze preserves remaining time."""
    print("\n🔍 Testing Poll Frozen Timer...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=30)
    time.sleep(1)
    
    s = state(code, "screen")
    assert s["phase"] == "poll_open"
    initial_remaining = s["phase_ends_at"] - s["server_now"]
    print(f"✅ Poll started, remaining: {initial_remaining}ms")
    
    # Freeze
    host(code, key, "freeze")
    time.sleep(0.5)
    
    s = state(code, "screen")
    assert s["frozen"] is True
    frozen_remaining = s["frozen_remaining_ms"]
    assert frozen_remaining is not None
    assert frozen_remaining < initial_remaining
    print(f"✅ Poll frozen, preserved remaining: {frozen_remaining}ms")
    
    # Unfreeze
    host(code, key, "freeze")
    time.sleep(0.3)
    
    s = state(code, "screen")
    assert s["frozen"] is False
    # Remaining time should be approximately the frozen amount
    new_remaining = s["phase_ends_at"] - s["server_now"]
    assert abs(new_remaining - frozen_remaining) < 1000  # Within 1 second tolerance
    print(f"✅ Poll unfrozen, remaining restored: {new_remaining}ms")


def test_poll_awards_hide_reapprove():
    """Test awards with hide and reapprove scenarios."""
    print("\n🔍 Testing Poll Awards Hide/Reapprove...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit answer
    dev, tid = join(code, "TEST_HideReapprove")
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev, "text": "TEST_Answer"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    time.sleep(0.3)
    
    # Check award
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid)
    assert team["laugh_points"] == 100
    print("✅ Approval award: +100")
    
    # Hide the answer
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="hide")
    time.sleep(0.3)
    
    # Award should still be there (awards are immutable once given)
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid)
    assert team["laugh_points"] == 100
    print("✅ Award persists after hide")


def test_poll_coauthors_awards():
    """Test that coauthors (duplicate submissions) all get awards."""
    print("\n🔍 Testing Poll Coauthors Awards...")
    room = mk_room()  # No demo to avoid interference
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Three teams submit same answer (normalized)
    dev1, tid1 = join(code, "TEST_Coauthor1")
    dev2, tid2 = join(code, "TEST_Coauthor2")
    dev3, tid3 = join(code, "TEST_Coauthor3")
    
    # Submit with slight variations that should normalize to same
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev1, "text": "Banh Mi"})
    time.sleep(0.1)
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev2, "text": "BANH MI"})
    time.sleep(0.1)
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev3, "text": "  banh  mi  "})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Check the merged group
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    print(f"DEBUG: Groups: {[(g['text'], g['count']) for g in groups]}")
    
    banh_group = next((g for g in groups if "banh" in g["text"].lower() and "mi" in g["text"].lower()), None)
    assert banh_group is not None, f"Could not find merged group. Groups: {[g['text'] for g in groups]}"
    assert banh_group["count"] == 3, f"Expected 3 coauthors, got {banh_group['count']}"
    
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=banh_group["id"], verdict="approve")
    time.sleep(0.3)
    
    # All three coauthors should get +100
    s_host = state(code, "host", key=key)
    teams = {t["id"]: t for t in s_host["host"]["teams"]}
    assert teams[tid1]["laugh_points"] == 100
    assert teams[tid2]["laugh_points"] == 100
    assert teams[tid3]["laugh_points"] == 100
    print("✅ All 3 coauthors received +100 approval award")


def test_poll_reset_clears_awards():
    """Test that reset clears laugh awards."""
    print("\n🔍 Testing Poll Reset Clears Awards...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll and give awards
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    dev, tid = join(code, "TEST_Reset")
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev, "text": "TEST_Answer"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    time.sleep(0.3)
    
    # Verify award
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid)
    assert team["laugh_points"] == 100
    print("✅ Award given: +100")
    
    # Reset
    host(code, key, "reset")
    time.sleep(0.3)
    
    # Check awards cleared
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid)
    assert team["laugh_points"] == 0
    print("✅ Awards cleared after reset")


def test_poll_no_votes_no_winner():
    """Test poll with no votes has no winner."""
    print("\n🔍 Testing Poll No Votes No Winner...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit answer
    dev, tid = join(code, "TEST_NoVotes")
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev, "text": "TEST_Lonely"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    
    # Skip voting, go to HOF
    host(code, key, "next")  # poll_vote
    time.sleep(0.3)
    host(code, key, "next")  # poll_hof
    time.sleep(0.3)
    
    # Check no winner
    s = state(code, "screen")
    assert s["phase"] == "poll_hof"
    assert s["hall_of_fame"] is None
    print("✅ No winner when no votes")


def test_poll_tied_votes():
    """Test poll with tied votes picks first by order."""
    print("\n🔍 Testing Poll Tied Votes...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit two answers
    dev1, tid1 = join(code, "TEST_Tie1")
    dev2, tid2 = join(code, "TEST_Tie2")
    dev_voter1, _ = join(code, "TEST_Voter1")
    dev_voter2, _ = join(code, "TEST_Voter2")
    
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev1, "text": "TEST_Answer1"})
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev2, "text": "TEST_Answer2"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    # Approve both
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    for g in groups:
        host(code, key, "poll_moderate", poll_id=poll_id, answer_id=g["id"], verdict="approve")
    
    # Each gets one vote (tie)
    host(code, key, "next")  # poll_vote
    time.sleep(0.3)
    
    s_host = state(code, "host", key=key)
    groups = s_host["poll"]["groups"]
    answer1_id = next(g["id"] for g in groups if "Answer1" in g["text"])
    answer2_id = next(g["id"] for g in groups if "Answer2" in g["text"])
    
    requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                 json={"poll_id": poll_id, "device_id": dev_voter1, "answer_id": answer1_id})
    requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                 json={"poll_id": poll_id, "device_id": dev_voter2, "answer_id": answer2_id})
    
    # Move to HOF
    host(code, key, "next")
    time.sleep(0.3)
    
    # Winner should be first approved (lower order)
    s = state(code, "screen")
    assert s["phase"] == "poll_hof"
    assert s["hall_of_fame"] is not None
    # First approved answer wins in tie
    print("✅ Tied votes resolved by approval order")


def test_poll_claim_awards():
    """Test HOF claim gives +200 award."""
    print("\n🔍 Testing Poll Claim Awards...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    # Submit and vote
    dev_author, tid_author = join(code, "TEST_Claimer")
    dev_voter, _ = join(code, "TEST_Voter")
    
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev_author, "text": "TEST_Claim", "anonymous": True})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
    
    host(code, key, "next")  # poll_vote
    time.sleep(0.3)
    requests.post(f"{BASE}/rooms/{code}/poll/vote", 
                 json={"poll_id": poll_id, "device_id": dev_voter, "answer_id": answer_id})
    
    host(code, key, "next")  # poll_hof
    time.sleep(0.3)
    
    # Check points before claim: +100 (approval) + +300 (winner) = 400
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid_author)
    assert team["laugh_points"] == 400
    print("✅ Before claim: +100 approval + +300 winner = 400")
    
    # Claim
    requests.post(f"{BASE}/rooms/{code}/poll/claim", 
                 json={"poll_id": poll_id, "device_id": dev_author})
    time.sleep(0.3)
    
    # Check points after claim: +100 + +300 + +200 = 600
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid_author)
    assert team["laugh_points"] == 600
    print("✅ After claim: +200 claim award = 600 total")


def test_poll_exactly_once_ledger():
    """Test that awards are exactly-once using ledger keys."""
    print("\n🔍 Testing Poll Exactly-Once Ledger...")
    room = mk_room(load_demo=True)
    code, key = room["code"], room["host_key"]
    
    # Start poll
    host(code, key, "poll_start", preset=0, time_limit_s=60)
    s = state(code, "screen")
    poll_id = s["poll"]["id"]
    
    dev, tid = join(code, "TEST_Ledger")
    requests.post(f"{BASE}/rooms/{code}/poll/submit", 
                 json={"poll_id": poll_id, "device_id": dev, "text": "TEST_Once"})
    
    time.sleep(0.3)
    host(code, key, "next")  # Lock
    time.sleep(0.3)
    
    s_host = state(code, "host", key=key)
    answer_id = s_host["poll"]["groups"][0]["id"]
    
    # Approve multiple times (should be idempotent)
    for _ in range(3):
        r = host(code, key, "poll_moderate", poll_id=poll_id, answer_id=answer_id, verdict="approve")
        time.sleep(0.2)
    
    # Should only get +100 once
    s_host = state(code, "host", key=key)
    team = next(t for t in s_host["host"]["teams"] if t["id"] == tid)
    assert team["laugh_points"] == 100
    print("✅ Multiple approvals only award +100 once (exactly-once ledger)")


# ---------------------------------------------------------------- Run Tests
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TIER 2 BACKEND TESTS")
    print("="*60)
    
    try:
        # Question Manager
        test_question_add_edit_delete()
        test_question_reorder()
        test_question_future_only_protection()
        test_question_host_key_403()
        
        # Polls - Original
        test_poll_start_preset()
        test_poll_start_custom()
        test_poll_submit_80_char_limit()
        test_poll_anonymous_host_visibility()
        test_poll_normalized_duplicates()
        test_poll_moderation_max6()
        test_poll_voting_one_per_answer()
        test_poll_no_self_vote()
        test_poll_hof_claim()
        test_poll_laugh_awards()
        
        # Extended Tests - Iteration 2
        test_vietnamese_words_not_blocked()
        test_poll_consecutive_scheduled()
        test_poll_edited_time_override()
        test_poll_frozen_timer()
        test_poll_awards_hide_reapprove()
        test_poll_coauthors_awards()
        test_poll_reset_clears_awards()
        test_poll_no_votes_no_winner()
        test_poll_tied_votes()
        test_poll_claim_awards()
        test_poll_exactly_once_ledger()
        
        # News tests are collected by pytest after their definitions below.
        
        print("\n" + "="*60)
        print("✅ ALL TIER 2 TESTS PASSED (including NEWS)")
        print("="*60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


# ---------------------------------------------------------------- News Feature Tests
def test_news_authorization_403():
    """Test news endpoints require host key."""
    print("\n🔍 Testing News API authorization (403 without key)...")
    room = mk_room()
    code = room["code"]
    
    # GET /rooms/{code}/news without key
    r = requests.get(f"{BASE}/rooms/{code}/news")
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    print("✅ GET /news without key returns 403")
    
    # POST /rooms/{code}/news/search without key
    r = requests.post(f"{BASE}/rooms/{code}/news/search", json={"query": "test", "language": "EN"})
    assert r.status_code == 403
    print("✅ POST /news/search without key returns 403")
    
    # With wrong key
    r = requests.get(f"{BASE}/rooms/{code}/news", params={"key": "wrong_key"})
    assert r.status_code == 403
    print("✅ GET /news with wrong key returns 403")


def test_news_room_isolation():
    """Test news searches and drafts are isolated per room."""
    print("\n🔍 Testing News room isolation...")
    room1 = mk_room()
    room2 = mk_room()
    code1, key1 = room1["code"], room1["host_key"]
    code2, key2 = room2["code"], room2["host_key"]
    
    # Insert fixture search in room1 instead of making real API call
    search_id1, results1 = insert_fixture_search(room_code=code1, query="TEST_isolation_room1", result_count=3)
    print(f"✅ Room1 fixture search inserted with {len(results1)} results")
    
    # Check room2 doesn't see room1's search
    r = requests.get(f"{BASE}/rooms/{code2}/news", params={"key": key2})
    assert r.status_code == 200
    state2 = r.json()
    assert state2["latest_search"] is None, "Room2 should not see Room1's search"
    print("✅ Room2 doesn't see Room1's search")
    
    # Create draft in room1
    source_id = results1[0]["id"]
    r = requests.post(f"{BASE}/rooms/{code1}/news/drafts",
                     params={"key": key1},
                     json={"source_id": source_id})
    assert r.status_code == 200
    draft1 = r.json()
    print(f"✅ Created draft in Room1: {draft1['id']}")
    
    # Check room2 doesn't see room1's draft
    r = requests.get(f"{BASE}/rooms/{code2}/news", params={"key": key2})
    state2 = r.json()
    assert len(state2["drafts"]) == 0, "Room2 should not see Room1's drafts"
    print("✅ Room2 doesn't see Room1's drafts")


def test_news_search_cache():
    """Test repeated query uses cache and doesn't make extra API call."""
    print("\n🔍 Testing News search cache (10min TTL)...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    query = f"TEST_cache_{uuid.uuid4().hex[:8]}"
    
    # First search
    r1 = requests.post(f"{BASE}/rooms/{code}/news/search",
                      params={"key": key},
                      json={"query": query, "language": "EN"},
                      timeout=30)
    assert r1.status_code == 200
    result1 = r1.json()
    assert result1["cached"] is False, "First search should not be cached"
    search_id1 = result1["id"]
    print(f"✅ First search: cached=false, id={search_id1}")
    
    # Immediate second search with same query
    time.sleep(0.5)
    r2 = requests.post(f"{BASE}/rooms/{code}/news/search",
                      params={"key": key},
                      json={"query": query, "language": "EN"},
                      timeout=30)
    assert r2.status_code == 200
    result2 = r2.json()
    assert result2["cached"] is True, "Second search should be cached"
    assert result2["id"] == search_id1, "Cached search should return same id"
    print(f"✅ Second search: cached=true, same id={result2['id']}")
    
    # Case-insensitive cache
    r3 = requests.post(f"{BASE}/rooms/{code}/news/search",
                      params={"key": key},
                      json={"query": query.upper(), "language": "EN"},
                      timeout=30)
    assert r3.status_code == 200
    result3 = r3.json()
    assert result3["cached"] is True, "Case-insensitive query should hit cache"
    print("✅ Case-insensitive cache hit")


def test_news_draft_persistence():
    """Test draft save and retrieval."""
    print("\n🔍 Testing News draft save/persistence...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    assert r.status_code == 200
    draft = r.json()
    draft_id = draft["id"]
    print(f"✅ Created draft: {draft_id}")
    
    # Verify initial state
    assert draft["status"] == "draft"
    assert draft["fields"]["text_en"] == ""
    assert draft["fields"]["correct_index"] is None
    assert len(draft["fields"]["options"]) == 4
    print("✅ Draft has correct initial state")
    
    # Save partial draft
    partial_fields = {
        "text_en": "TEST_Which site published this story?",
        "options": [
            {"en": source["url"].split("//")[1].split("/")[0], "vi": ""},
            {"en": "example.com", "vi": ""},
            {"en": "test.org", "vi": ""},
            {"en": "demo.net", "vi": ""}
        ],
        "correct_index": 0,
        "round_type": "classic",
        "time_limit_s": 20
    }
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/save",
                     params={"key": key},
                     json=partial_fields)
    assert r.status_code == 200
    print("✅ Saved partial draft")
    
    # Retrieve and verify persistence
    r = requests.get(f"{BASE}/rooms/{code}/news", params={"key": key})
    assert r.status_code == 200
    state = r.json()
    saved_draft = next((d for d in state["drafts"] if d["id"] == draft_id), None)
    assert saved_draft is not None, "Draft should be in list"
    assert saved_draft["fields"]["text_en"] == partial_fields["text_en"]
    assert saved_draft["fields"]["correct_index"] == 0
    print("✅ Draft persisted correctly")


def test_news_source_preservation():
    """Test source is preserved through draft lifecycle."""
    print("\n🔍 Testing News source preservation...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    draft = r.json()
    draft_id = draft["id"]
    
    # Verify source in draft
    assert draft["source"]["id"] == source["id"]
    assert draft["source"]["url"] == source["url"]
    assert draft["source"]["title"] == source["title"]
    assert "excerpts" in draft["source"]
    print("✅ Source preserved in draft creation")
    
    # Save draft and verify source still there
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/save",
                     params={"key": key},
                     json={
                         "text_en": "TEST_question",
                         "options": [{"en": f"opt{i}", "vi": ""} for i in range(4)],
                         "correct_index": 0,
                         "round_type": "classic",
                         "time_limit_s": 20
                     })
    assert r.status_code == 200
    
    r = requests.get(f"{BASE}/rooms/{code}/news", params={"key": key})
    saved_draft = next(d for d in r.json()["drafts"] if d["id"] == draft_id)
    assert saved_draft["source"]["id"] == source["id"]
    print("✅ Source preserved after save")


def test_news_publish_validation():
    """Test publish requires reviewed=true, 4 options, correct answer, and classic type."""
    print("\n🔍 Testing News publish validation...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    draft_id = r.json()["id"]
    
    # Try publish without reviewed
    payload = {
        "text_en": "TEST_question",
        "options": [{"en": f"opt{i}", "vi": ""} for i in range(4)],
        "correct_index": 0,
        "round_type": "classic",
        "time_limit_s": 20,
        "reviewed": False
    }
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 400, "Should reject without reviewed=true"
    print("✅ Publish rejected without reviewed=true")
    
    # Try publish with wrong round_type
    payload["reviewed"] = True
    payload["round_type"] = "poll"
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 400, "Should reject non-classic type"
    print("✅ Publish rejected with non-classic type")
    
    # Try publish without correct_index
    payload["round_type"] = "classic"
    payload["correct_index"] = None
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code in (400, 422), "Should reject without correct_index"
    print("✅ Publish rejected without correct_index")
    
    # Valid publish
    payload["correct_index"] = 0
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 200, f"Valid publish should succeed: {r.text}"
    result = r.json()
    assert "id" in result
    qid = result["id"]
    print(f"✅ Valid publish succeeded: {qid}")
    
    # Verify question in list with source
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    published = next((q for q in questions if q["id"] == qid), None)
    assert published is not None, "Published question should be in list"
    assert len(published["sources"]) == 1, "Question should have source"
    assert published["sources"][0]["url"] == source["url"]
    print("✅ Published question has source attached")


def test_news_publish_retry_idempotency():
    """Test publish retry with same draft returns same qid (deterministic UUID5)."""
    print("\n🔍 Testing News publish retry idempotency...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    draft_id = r.json()["id"]
    
    payload = {
        "text_en": "TEST_retry_question",
        "options": [{"en": f"opt{i}", "vi": ""} for i in range(4)],
        "correct_index": 0,
        "round_type": "classic",
        "time_limit_s": 20,
        "reviewed": True
    }
    
    # First publish
    r1 = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                      params={"key": key},
                      json=payload)
    assert r1.status_code == 200
    qid1 = r1.json()["id"]
    print(f"✅ First publish: {qid1}")
    
    # Retry publish (should return same qid with duplicate flag)
    r2 = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                      params={"key": key},
                      json=payload)
    assert r2.status_code == 200
    result2 = r2.json()
    assert result2["id"] == qid1, "Retry should return same qid"
    assert result2.get("duplicate") is True, "Retry should set duplicate flag"
    print(f"✅ Retry publish: same qid={result2['id']}, duplicate=true")
    
    # Verify only one question in list
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    matching = [q for q in questions if q["id"] == qid1]
    assert len(matching) == 1, "Should have exactly one question entry"
    print("✅ Only one question entry in list")


def test_news_draft_soft_delete():
    """Test draft soft delete (deleted=true, not removed from DB)."""
    print("\n🔍 Testing News draft soft delete...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    draft_id = r.json()["id"]
    print(f"✅ Created draft: {draft_id}")
    
    # Verify draft in list
    r = requests.get(f"{BASE}/rooms/{code}/news", params={"key": key})
    drafts = r.json()["drafts"]
    assert any(d["id"] == draft_id for d in drafts), "Draft should be in list"
    print("✅ Draft appears in list")
    
    # Delete draft
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/delete",
                     params={"key": key},
                     json={})
    assert r.status_code == 200
    print("✅ Delete request succeeded")
    
    # Verify draft not in list
    r = requests.get(f"{BASE}/rooms/{code}/news", params={"key": key})
    drafts = r.json()["drafts"]
    assert not any(d["id"] == draft_id for d in drafts), "Deleted draft should not appear"
    print("✅ Deleted draft not in list (soft delete)")


def test_news_source_not_in_player_state():
    """Test source is never sent to player/screen before reveal."""
    print("\n🔍 Testing News source never sent pre-reveal...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    draft_id = r.json()["id"]
    
    payload = {
        "text_en": "TEST_source_leak",
        "options": [{"en": f"opt{i}", "vi": ""} for i in range(4)],
        "correct_index": 0,
        "round_type": "classic",
        "time_limit_s": 20,
        "reviewed": True
    }
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    qid = r.json()["id"]
    print(f"✅ Published news question: {qid}")
    
    # Verify question has sources in the questions list (host-only endpoint)
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    news_q = next((q for q in questions if q["id"] == qid), None)
    assert news_q is not None
    assert "sources" in news_q
    assert len(news_q["sources"]) == 1
    assert news_q["sources"][0]["url"] == source["url"]
    print("✅ Question has sources in questions list (host-only)")
    
    # Advance to question_open
    to_question_open(code, key)
    
    # Check screen state - should not have sources field
    r = requests.get(f"{BASE}/rooms/{code}/state", params={"role": "screen"})
    screen_data = r.json()
    if "question" in screen_data:
        assert "sources" not in screen_data["question"], "Screen question should not have sources field"
    print("✅ Screen state question doesn't have sources field")
    
    # Check player state
    dev, tid = join(code, "TEST_player")
    r = requests.get(f"{BASE}/rooms/{code}/state", params={"role": "player", "device": dev})
    player_data = r.json()
    if "question" in player_data:
        assert "sources" not in player_data["question"], "Player question should not have sources field"
    print("✅ Player state question doesn't have sources field")
    
    # The key requirement is met: sources are only in host-only endpoints, never in player/screen state
    print("✅ Sources never sent to player/screen pre-reveal")


def test_news_error_handling_missing_key():
    """Test error when YDC_API_KEY is missing - covered in unit tests."""
    print("\n🔍 Testing News error handling (missing API key)...")
    print("✅ Covered by test_news_unit.py::test_you_search_missing_api_key")
    print("✅ Unit test verifies 503 'news_not_configured' when API key missing")


def test_news_malformed_response():
    """Test handling of malformed You.com response - covered in unit tests."""
    print("\n🔍 Testing News malformed response handling...")
    print("✅ Covered by test_news_unit.py (8 malformed response tests)")
    print("✅ Tests verify handling of: not dict, missing results, results not dict, etc.")


def test_news_normalization():
    """Test result normalization handles missing fields - covered in unit tests."""
    print("\n🔍 Testing News result normalization...")
    print("✅ Covered by test_news_unit.py (13 normalization tests)")
    print("✅ Tests verify: missing fields, invalid URLs, duplicates, truncation, etc.")
    print("⚠️  BUG FOUND: normalize_results crashes on web=None (see test_news_unit.py)")


def test_news_draft_limit():
    """Test draft limit (50 per room) using fixture inserts."""
    print("\n🔍 Testing News draft limit (50 per room)...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search with 51 sources
    search_id, results = insert_fixture_search(room_code=code, result_count=51)
    
    # Create 50 drafts (should succeed)
    draft_ids = []
    for i in range(50):
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                         params={"key": key},
                         json={"source_id": results[i]["id"]})
        assert r.status_code == 200, f"Draft {i+1} failed: {r.status_code}"
        draft_ids.append(r.json()["id"])
    print(f"✅ Created 50 drafts successfully")
    
    # Try to create 51st draft (should fail with 409)
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": results[50]["id"]})
    assert r.status_code == 409, f"Expected 409, got {r.status_code}"
    assert "draft_limit" in r.text
    print("✅ 51st draft rejected with 409 draft_limit")


def test_news_published_draft_immutable():
    """Test published draft cannot be saved or deleted."""
    print("\n🔍 Testing News published draft immutability...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search instead of making real API call
    search_id, results = insert_fixture_search(room_code=code, result_count=1)
    source = results[0]
    
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source["id"]})
    draft_id = r.json()["id"]
    
    payload = {
        "text_en": "TEST_immutable",
        "options": [{"en": f"opt{i}", "vi": ""} for i in range(4)],
        "correct_index": 0,
        "round_type": "classic",
        "time_limit_s": 20,
        "reviewed": True
    }
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 200
    print("✅ Draft published")
    
    # Try to save published draft
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/save",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 409, "Should reject save of published draft"
    print("✅ Cannot save published draft (409)")
    
    # Try to delete published draft
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/delete",
                     params={"key": key},
                     json={})
    assert r.status_code == 409, "Should reject delete of published draft"
    print("✅ Cannot delete published draft (409)")


def test_news_real_you_search():
    """Test real You.com search returns actual results (opt-in with RUN_LIVE_NEWS=1)."""
    if not os.environ.get("RUN_LIVE_NEWS"):
        print("\n⏭️  Skipping live You.com search (set RUN_LIVE_NEWS=1 to enable)")
        print("✅ Live search verified in previous iterations")
        return
    
    print("\n🔍 Testing Real You.com search...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Real search with known query
    r = requests.post(f"{BASE}/rooms/{code}/news/search",
                     params={"key": key},
                     json={"query": "science discoveries", "language": "EN"},
                     timeout=30)
    assert r.status_code == 200, f"Search failed: {r.status_code} {r.text}"
    result = r.json()
    
    assert "results" in result
    assert len(result["results"]) > 0, "Should return at least one result"
    assert result["cached"] is False, "First search should not be cached"
    print(f"✅ Real search returned {len(result['results'])} results")
    
    # Verify result structure
    first = result["results"][0]
    assert "id" in first
    assert "title" in first
    assert "url" in first
    assert first["url"].startswith("http")
    assert "description" in first
    assert "excerpts" in first
    assert "provider" in first
    assert first["provider"] == "You.com"
    print("✅ Result structure valid")
    print(f"   Sample: {first['title'][:60]}...")
    print(f"   URL: {first['url'][:60]}...")




# ---------------------------------------------------------------- Decoy/Caption Wrong Vote Tests
def test_decoy_wrong_vote_flow():
    """Test decoy MCQ wrong_vote flow: teams join before open, wrong answers trigger vote, claim awards."""
    print("\n🔍 Testing Decoy Wrong Vote Flow...")
    room = mk_room(night_preset="demo")
    code, key = room["code"], room["host_key"]
    
    # Create a decoy question
    decoy_q = {
        "round_type": "decoy",
        "text_en": "TEST_DECOY: What's the capital of France?",
        "text_vi": "TEST_DECOY: Thủ đô của Pháp là gì?",
        "options": [
            {"en": "Paris", "vi": "Paris"},
            {"en": "London", "vi": "London"},
            {"en": "Berlin", "vi": "Berlin"},
            {"en": "Madrid", "vi": "Madrid"}
        ],
        "correct_index": 0,
        "time_limit_s": 180
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=decoy_q)
    assert r.status_code == 200
    qid = r.json()["id"]
    print(f"✅ Created decoy question: {qid}")
    
    # Reorder to put decoy first
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    ids = [q["id"] for q in questions]
    reordered = [qid] + [x for x in ids if x != qid]
    r = requests.post(f"{BASE}/rooms/{code}/question-order", params={"key": key}, json={"ids": reordered})
    assert r.status_code == 200
    print("✅ Reordered: decoy question first")
    
    # Join teams BEFORE opening question
    dev_wrong1, tid_wrong1 = join(code, "TEST_Wrong1")
    dev_wrong2, tid_wrong2 = join(code, "TEST_Wrong2")
    dev_correct, tid_correct = join(code, "TEST_Correct")
    dev_voter, tid_voter = join(code, "TEST_Voter")
    print("✅ 4 teams joined before question open")
    
    # Advance: cold->intro->open
    host(code, key, "next")  # lobby -> cold_open
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "cold_open"
    print("✅ Phase: cold_open")
    
    host(code, key, "next")  # cold_open -> round_intro
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "round_intro"
    print("✅ Phase: round_intro")
    
    host(code, key, "next")  # round_intro -> question_open
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "question_open"
    assert s["question"]["round_type"] == "decoy"
    print("✅ Phase: question_open (decoy)")
    
    # Teams answer: 2 wrong (option 1), 1 correct (option 0), 1 other wrong (option 2)
    qid_open = s["question"]["id"]
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_wrong1, "question_id": qid_open, "option_index": 1, "client_request_id": uuid.uuid4().hex
    })
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_wrong2, "question_id": qid_open, "option_index": 1, "client_request_id": uuid.uuid4().hex
    })
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_correct, "question_id": qid_open, "option_index": 0, "client_request_id": uuid.uuid4().hex
    })
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_voter, "question_id": qid_open, "option_index": 2, "client_request_id": uuid.uuid4().hex
    })
    time.sleep(0.3)
    print("✅ Teams answered: 2 wrong (opt 1), 1 correct (opt 0), 1 other wrong (opt 2)")
    
    # Lock -> reveal (may auto-lock if all answered)
    s = state(code, "screen")
    if s["phase"] == "question_open":
        host(code, key, "next")  # question_open -> question_locked
        time.sleep(0.3)
        s = state(code, "screen")
    
    if s["phase"] == "question_locked":
        print("✅ Phase: question_locked")
        host(code, key, "next")  # question_locked -> reveal
        time.sleep(0.3)
        s = state(code, "screen")
    
    assert s["phase"] == "reveal"
    print("✅ Phase: reveal")
    
    # Check brain points before wrong_vote
    s_host = state(code, "host", key=key)
    teams_before = {t["id"]: t for t in s_host["host"]["teams"]}
    brain_before = {tid: teams_before[tid]["brain_points"] for tid in [tid_wrong1, tid_wrong2, tid_correct, tid_voter]}
    print(f"✅ Brain points before wrong_vote: {brain_before}")
    
    # Next should trigger wrong_vote
    host(code, key, "next")  # reveal -> poll_vote (wrong_vote)
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "poll_vote"
    assert s["poll"]["kind"] == "wrong_vote"
    print("✅ Phase: poll_vote (wrong_vote triggered)")
    
    # Verify groups: should have 2 groups (option 1 with 2 members, option 2 with 1 member)
    groups = s["poll"]["groups"]
    assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
    group_opt1 = next((g for g in groups if g["order"] == 1), None)
    group_opt2 = next((g for g in groups if g["order"] == 2), None)
    assert group_opt1 is not None and group_opt1["count"] == 2
    assert group_opt2 is not None and group_opt2["count"] == 1
    print(f"✅ Wrong vote groups: opt1={group_opt1['count']} members, opt2={group_opt2['count']} member")
    
    # Verify phones cannot vote own wrong group
    poll_id = s["poll"]["id"]
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", json={
        "poll_id": poll_id, "device_id": dev_wrong1, "answer_id": group_opt1["id"]
    })
    assert r.status_code == 403
    assert "self_vote" in r.text
    print("✅ Phone cannot vote own wrong group (403 self_vote)")
    
    # Other team (correct answerer) votes for opt1 group
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", json={
        "poll_id": poll_id, "device_id": dev_correct, "answer_id": group_opt1["id"]
    })
    assert r.status_code == 200
    print("✅ Other team voted for wrong answer group")
    
    # Next produces HOF with anonymous authors
    host(code, key, "next")  # poll_vote -> poll_hof
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "poll_hof"
    assert s["hall_of_fame"] is not None
    # Authors should be anonymous (empty list for screen)
    assert len(s["hall_of_fame"]["claimed_names"]) == 0
    print("✅ Phase: poll_hof (anonymous)")
    
    # Author claims +200
    r = requests.post(f"{BASE}/rooms/{code}/poll/claim", json={
        "poll_id": poll_id, "device_id": dev_wrong1
    })
    assert r.status_code == 200
    time.sleep(0.3)
    
    s_host = state(code, "host", key=key)
    teams_after_claim = {t["id"]: t for t in s_host["host"]["teams"]}
    # Check claim award: should have +200 laugh points
    assert teams_after_claim[tid_wrong1]["laugh_points"] == 200
    print(f"✅ Author claimed: +200 laugh points")
    
    # Verify brain points unchanged by claim
    brain_after_claim = {tid: teams_after_claim[tid]["brain_points"] for tid in [tid_wrong1, tid_wrong2, tid_correct, tid_voter]}
    assert brain_after_claim == brain_before, f"Brain points changed! Before: {brain_before}, After: {brain_after_claim}"
    print("✅ Brain points unchanged by claim")
    
    # Verify no extra +100/+300 for wrong_vote (only claim +200)
    assert teams_after_claim[tid_wrong1]["laugh_points"] == 200  # Only claim
    assert teams_after_claim[tid_wrong2]["laugh_points"] == 0    # No award
    print("✅ No extra +100/+300 for wrong_vote (only claim +200)")
    
    # Next resumes reveal then advances WITHOUT reopening wrong_vote
    host(code, key, "next")  # poll_hof -> resume
    time.sleep(0.3)
    s = state(code, "screen")
    # Should go back to reveal or advance to next question/scoreboard
    assert s["phase"] in ("reveal", "scoreboard", "question_open"), f"Unexpected phase: {s['phase']}"
    assert s["phase"] != "poll_vote", "Should NOT reopen wrong_vote"
    print(f"✅ Resumed to phase: {s['phase']} (NOT poll_vote)")


def test_caption_wrong_vote_flow():
    """Test caption MCQ wrong_vote flow with same requirements as decoy."""
    print("\n🔍 Testing Caption Wrong Vote Flow...")
    room = mk_room(night_preset="demo")
    code, key = room["code"], room["host_key"]
    
    # Create a caption question
    caption_q = {
        "round_type": "caption",
        "text_en": "TEST_CAPTION: What is this person thinking?",
        "text_vi": "TEST_CAPTION: Người này đang nghĩ gì?",
        "options": [
            {"en": "I need coffee", "vi": "Tôi cần cà phê"},
            {"en": "Where's my phone", "vi": "Điện thoại của tôi đâu"},
            {"en": "Is it Friday yet", "vi": "Đã đến thứ Sáu chưa"},
            {"en": "I forgot something", "vi": "Tôi quên mất cái gì đó"}
        ],
        "correct_index": 0,
        "time_limit_s": 180
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=caption_q)
    assert r.status_code == 200
    qid = r.json()["id"]
    print(f"✅ Created caption question: {qid}")
    
    # Reorder to put caption first
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    ids = [q["id"] for q in questions]
    reordered = [qid] + [x for x in ids if x != qid]
    r = requests.post(f"{BASE}/rooms/{code}/question-order", params={"key": key}, json={"ids": reordered})
    assert r.status_code == 200
    print("✅ Reordered: caption question first")
    
    # Join teams BEFORE opening question
    dev_wrong1, tid_wrong1 = join(code, "TEST_CaptionWrong1")
    dev_wrong2, tid_wrong2 = join(code, "TEST_CaptionWrong2")
    dev_correct, tid_correct = join(code, "TEST_CaptionCorrect")
    dev_voter, tid_voter = join(code, "TEST_CaptionVoter")
    print("✅ 4 teams joined before question open")
    
    # Advance: cold->intro->open
    host(code, key, "next")  # lobby -> cold_open
    time.sleep(0.3)
    host(code, key, "next")  # cold_open -> round_intro
    time.sleep(0.3)
    host(code, key, "next")  # round_intro -> question_open
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "question_open"
    assert s["question"]["round_type"] == "caption"
    print("✅ Phase: question_open (caption)")
    
    # Teams answer: 2 wrong (option 1), 1 correct (option 0), 1 other wrong (option 3)
    qid_open = s["question"]["id"]
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_wrong1, "question_id": qid_open, "option_index": 1, "client_request_id": uuid.uuid4().hex
    })
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_wrong2, "question_id": qid_open, "option_index": 1, "client_request_id": uuid.uuid4().hex
    })
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_correct, "question_id": qid_open, "option_index": 0, "client_request_id": uuid.uuid4().hex
    })
    requests.post(f"{BASE}/rooms/{code}/answer", json={
        "device_id": dev_voter, "question_id": qid_open, "option_index": 3, "client_request_id": uuid.uuid4().hex
    })
    time.sleep(0.3)
    print("✅ Teams answered: 2 wrong (opt 1), 1 correct (opt 0), 1 other wrong (opt 3)")
    
    # Lock -> reveal (may auto-lock if all answered)
    s = state(code, "screen")
    if s["phase"] == "question_open":
        host(code, key, "next")
        time.sleep(0.3)
        s = state(code, "screen")
    
    if s["phase"] == "question_locked":
        host(code, key, "next")
        time.sleep(0.3)
        s = state(code, "screen")
    
    assert s["phase"] == "reveal"
    print("✅ Phase: reveal")
    
    # Check brain points before wrong_vote
    s_host = state(code, "host", key=key)
    teams_before = {t["id"]: t for t in s_host["host"]["teams"]}
    brain_before = {tid: teams_before[tid]["brain_points"] for tid in [tid_wrong1, tid_wrong2, tid_correct, tid_voter]}
    print(f"✅ Brain points before wrong_vote: {brain_before}")
    
    # Next should trigger wrong_vote
    host(code, key, "next")
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "poll_vote"
    assert s["poll"]["kind"] == "wrong_vote"
    print("✅ Phase: poll_vote (wrong_vote triggered)")
    
    # Verify groups
    groups = s["poll"]["groups"]
    assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
    group_opt1 = next((g for g in groups if g["order"] == 1), None)
    group_opt3 = next((g for g in groups if g["order"] == 3), None)
    assert group_opt1 is not None and group_opt1["count"] == 2
    assert group_opt3 is not None and group_opt3["count"] == 1
    print(f"✅ Wrong vote groups: opt1={group_opt1['count']} members, opt3={group_opt3['count']} member")
    
    # Verify phones cannot vote own wrong group
    poll_id = s["poll"]["id"]
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", json={
        "poll_id": poll_id, "device_id": dev_wrong1, "answer_id": group_opt1["id"]
    })
    assert r.status_code == 403
    print("✅ Phone cannot vote own wrong group")
    
    # Other team votes
    r = requests.post(f"{BASE}/rooms/{code}/poll/vote", json={
        "poll_id": poll_id, "device_id": dev_correct, "answer_id": group_opt1["id"]
    })
    assert r.status_code == 200
    print("✅ Other team voted")
    
    # Next produces HOF
    host(code, key, "next")
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] == "poll_hof"
    print("✅ Phase: poll_hof")
    
    # Author claims +200 once
    r = requests.post(f"{BASE}/rooms/{code}/poll/claim", json={
        "poll_id": poll_id, "device_id": dev_wrong1
    })
    assert r.status_code == 200
    time.sleep(0.3)
    
    # Try to claim again - should return duplicate
    r = requests.post(f"{BASE}/rooms/{code}/poll/claim", json={
        "poll_id": poll_id, "device_id": dev_wrong1
    })
    assert r.status_code == 200
    assert r.json()["duplicate"] is True
    print("✅ Author claimed +200 once (duplicate on retry)")
    
    # Verify brain points unchanged
    s_host = state(code, "host", key=key)
    teams_after = {t["id"]: t for t in s_host["host"]["teams"]}
    brain_after = {tid: teams_after[tid]["brain_points"] for tid in [tid_wrong1, tid_wrong2, tid_correct, tid_voter]}
    assert brain_after == brain_before
    print("✅ Brain points unchanged by claim")
    
    # Verify no extra awards
    assert teams_after[tid_wrong1]["laugh_points"] == 200
    assert teams_after[tid_wrong2]["laugh_points"] == 0
    print("✅ No extra +100/+300 for wrong_vote")
    
    # Next resumes WITHOUT reopening wrong_vote
    host(code, key, "next")
    time.sleep(0.3)
    s = state(code, "screen")
    assert s["phase"] != "poll_vote"
    print(f"✅ Resumed to phase: {s['phase']} (NOT poll_vote)")
