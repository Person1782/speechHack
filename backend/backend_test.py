"""Backend API tests for open-ended questions and poll normalization.
Tests the new ResponseTypePicker functionality for both Question Manager and News drafts.
"""
import os
import sys
import uuid
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Read BASE from frontend .env for public endpoint testing
frontend_env = Path(__file__).parent.parent / "frontend" / ".env"
if frontend_env.exists():
    with open(frontend_env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip() + "/api"
                break
else:
    BASE = "https://quiz-and-riff--39crjv3i.preview.emergentagent.com/api"

print(f"Testing against: {BASE}")

# MongoDB connection for fixture insertion
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

from pymongo import MongoClient
_db_client = None

def get_db():
    """Get MongoDB database connection."""
    global _db_client
    if _db_client is None:
        _db_client = MongoClient(MONGO_URL)
    return _db_client[os.environ["DB_NAME"]]


def mk_room(**kw):
    """Create a test room."""
    r = requests.post(f"{BASE}/rooms", json={"host_name": "TEST_OpenEnded", "venue_name": "TEST_Bar", **kw})
    r.raise_for_status()
    return r.json()


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


class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.total = 0
    
    def record(self, test_name, passed, error=None):
        self.total += 1
        if passed:
            self.passed.append(test_name)
            print(f"✅ {test_name}")
        else:
            self.failed.append({"test": test_name, "error": str(error)})
            print(f"❌ {test_name}: {error}")
    
    def summary(self):
        print(f"\n{'='*60}")
        print(f"Test Results: {len(self.passed)}/{self.total} passed")
        print(f"{'='*60}")
        if self.failed:
            print("\n❌ Failed Tests:")
            for fail in self.failed:
                print(f"  - {fail['test']}: {fail['error']}")
        return len(self.failed) == 0


results = TestResults()


def test_create_open_ended_question():
    """Test creating an open-ended question (poll) with only text, no options/correct."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Create open-ended question
        new_q = {
            "round_type": "poll",
            "text_en": "TEST_What's your favorite memory from this year?",
            "text_vi": "TEST_Kỷ niệm yêu thích năm nay?",
            "time_limit_s": 45
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
        assert r.status_code == 200, f"Failed to create: {r.text}"
        qid = r.json()["id"]
        
        # Verify question was created with poll type
        r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
        questions = r.json()["questions"]
        created = next((q for q in questions if q["id"] == qid), None)
        assert created is not None, "Question not found"
        assert created["round_type"] == "poll", f"Expected poll, got {created['round_type']}"
        assert created["options"] == [], f"Expected empty options, got {created['options']}"
        assert created["correct_index"] is None, f"Expected null correct_index, got {created['correct_index']}"
        
        results.record("Create open-ended question", True)
    except Exception as e:
        results.record("Create open-ended question", False, e)


def test_edit_question_to_open_ended():
    """Test editing a classic question to open-ended."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Create classic question first
        classic_q = {
            "round_type": "classic",
            "text_en": "TEST_Classic question",
            "options": [{"en": f"Option {i}", "vi": f"Tùy chọn {i}"} for i in range(4)],
            "correct_index": 0,
            "time_limit_s": 20
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=classic_q)
        assert r.status_code == 200
        qid = r.json()["id"]
        
        # Edit to open-ended
        open_q = {
            "round_type": "poll",
            "text_en": "TEST_Now open-ended",
            "time_limit_s": 30
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions/{qid}", params={"key": key}, json=open_q)
        assert r.status_code == 200, f"Failed to edit: {r.text}"
        
        # Verify it's now poll with no options
        r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
        questions = r.json()["questions"]
        edited = next((q for q in questions if q["id"] == qid), None)
        assert edited["round_type"] == "poll"
        assert edited["options"] == []
        assert edited["correct_index"] is None
        
        results.record("Edit question to open-ended", True)
    except Exception as e:
        results.record("Edit question to open-ended", False, e)


def test_edit_open_ended_to_classic():
    """Test editing an open-ended question back to classic."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Create open-ended first
        open_q = {
            "round_type": "poll",
            "text_en": "TEST_Open question",
            "time_limit_s": 30
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=open_q)
        assert r.status_code == 200
        qid = r.json()["id"]
        
        # Edit to classic
        classic_q = {
            "round_type": "classic",
            "text_en": "TEST_Now classic",
            "options": [{"en": f"Option {i}", "vi": f"Tùy chọn {i}"} for i in range(4)],
            "correct_index": 2,
            "time_limit_s": 20
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions/{qid}", params={"key": key}, json=classic_q)
        assert r.status_code == 200, f"Failed to edit: {r.text}"
        
        # Verify it's now classic with options
        r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
        questions = r.json()["questions"]
        edited = next((q for q in questions if q["id"] == qid), None)
        assert edited["round_type"] == "classic"
        assert len(edited["options"]) == 4
        assert edited["correct_index"] == 2
        
        results.record("Edit open-ended to classic", True)
    except Exception as e:
        results.record("Edit open-ended to classic", False, e)


def test_poll_normalization():
    """Test that poll questions normalize options to [] and correct_index to null."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Try to create poll with options (should be normalized)
        poll_with_options = {
            "round_type": "poll",
            "text_en": "TEST_Poll with options",
            "options": [{"en": "A", "vi": "A"}] * 4,
            "correct_index": 0,
            "time_limit_s": 30
        }
        r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=poll_with_options)
        assert r.status_code == 200
        qid = r.json()["id"]
        
        # Verify normalization
        r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
        questions = r.json()["questions"]
        created = next((q for q in questions if q["id"] == qid), None)
        assert created["options"] == [], "Options should be normalized to []"
        assert created["correct_index"] is None, "correct_index should be normalized to null"
        
        results.record("Poll normalization", True)
    except Exception as e:
        results.record("Poll normalization", False, e)


def test_news_publish_open_ended_with_review():
    """Test publishing open-ended news draft with review=true."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Insert fixture search
        search_id, results_list = insert_fixture_search(room_code=code, result_count=1)
        source = results_list[0]
        
        # Create draft
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                         params={"key": key},
                         json={"source_id": source["id"]})
        assert r.status_code == 200
        draft_id = r.json()["id"]
        
        # Publish as open-ended with review=true
        payload = {
            "round_type": "poll",
            "text_en": "TEST_Open-ended news question",
            "time_limit_s": 45,
            "reviewed": True
        }
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                         params={"key": key},
                         json=payload)
        assert r.status_code == 200, f"Failed to publish: {r.text}"
        qid = r.json()["id"]
        
        # Verify published question
        r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
        questions = r.json()["questions"]
        published = next((q for q in questions if q["id"] == qid), None)
        assert published is not None
        assert published["round_type"] == "poll"
        assert published["options"] == []
        assert published["correct_index"] is None
        
        results.record("News publish open-ended with review", True)
    except Exception as e:
        results.record("News publish open-ended with review", False, e)


def test_news_publish_open_ended_without_review():
    """Test that publishing open-ended news draft without review=true fails."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Insert fixture search
        search_id, results_list = insert_fixture_search(room_code=code, result_count=1)
        source = results_list[0]
        
        # Create draft
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                         params={"key": key},
                         json={"source_id": source["id"]})
        assert r.status_code == 200
        draft_id = r.json()["id"]
        
        # Try to publish without review
        payload = {
            "round_type": "poll",
            "text_en": "TEST_Should fail",
            "time_limit_s": 45,
            "reviewed": False
        }
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                         params={"key": key},
                         json=payload)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        assert "review" in r.text.lower(), "Error should mention review requirement"
        
        results.record("News publish open-ended without review fails", True)
    except Exception as e:
        results.record("News publish open-ended without review fails", False, e)


def test_news_publish_classic_with_review():
    """Test publishing classic news draft still works with review=true."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Insert fixture search
        search_id, results_list = insert_fixture_search(room_code=code, result_count=1)
        source = results_list[0]
        
        # Create draft
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                         params={"key": key},
                         json={"source_id": source["id"]})
        assert r.status_code == 200
        draft_id = r.json()["id"]
        
        # Publish as classic with review=true
        payload = {
            "round_type": "classic",
            "text_en": "TEST_Classic news question",
            "options": [{"en": f"Option {i}", "vi": ""} for i in range(4)],
            "correct_index": 0,
            "time_limit_s": 20,
            "reviewed": True
        }
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                         params={"key": key},
                         json=payload)
        assert r.status_code == 200, f"Failed to publish: {r.text}"
        qid = r.json()["id"]
        
        # Verify published question
        r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
        questions = r.json()["questions"]
        published = next((q for q in questions if q["id"] == qid), None)
        assert published is not None
        assert published["round_type"] == "classic"
        assert len(published["options"]) == 4
        assert published["correct_index"] == 0
        
        results.record("News publish classic with review", True)
    except Exception as e:
        results.record("News publish classic with review", False, e)


def test_news_publish_decoy_rejected():
    """Test that publishing news draft as decoy/caption is rejected."""
    try:
        room = mk_room()
        code, key = room["code"], room["host_key"]
        
        # Insert fixture search
        search_id, results_list = insert_fixture_search(room_code=code, result_count=1)
        source = results_list[0]
        
        # Create draft
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                         params={"key": key},
                         json={"source_id": source["id"]})
        assert r.status_code == 200
        draft_id = r.json()["id"]
        
        # Try to publish as decoy
        payload = {
            "round_type": "decoy",
            "text_en": "TEST_Decoy",
            "options": [{"en": f"Option {i}", "vi": ""} for i in range(4)],
            "correct_index": 0,
            "time_limit_s": 20,
            "reviewed": True
        }
        r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                         params={"key": key},
                         json=payload)
        assert r.status_code == 400, f"Expected 400 for decoy, got {r.status_code}"
        
        results.record("News publish decoy rejected", True)
    except Exception as e:
        results.record("News publish decoy rejected", False, e)


def main():
    print("\n" + "="*60)
    print("🧪 BACKEND TESTS: Open-Ended Questions & Poll Normalization")
    print("="*60 + "\n")
    
    # Run all tests
    test_create_open_ended_question()
    test_edit_question_to_open_ended()
    test_edit_open_ended_to_classic()
    test_poll_normalization()
    test_news_publish_open_ended_with_review()
    test_news_publish_open_ended_without_review()
    test_news_publish_classic_with_review()
    test_news_publish_decoy_rejected()
    
    # Print summary
    success = results.summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
