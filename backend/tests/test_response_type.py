"""Test ResponseTypePicker backend integration: poll questions with open-ended responses.
Run: cd /app/backend && python tests/test_response_type.py
"""
import os
import requests
import uuid
from pathlib import Path
from dotenv import load_dotenv

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

print(f"Testing against: {BASE}")


def mk_room(**kw):
    """Create a test room."""
    r = requests.post(f"{BASE}/rooms", json={"host_name": "TEST_ResponseType", "venue_name": "TEST_Bar", **kw})
    r.raise_for_status()
    return r.json()


def test_poll_question_no_options_required():
    """Test that poll questions (round_type=poll) don't require options or correct_index."""
    print("\n🔍 Testing poll question without options/correct_index...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Add a poll question without options or correct_index
    new_q = {
        "round_type": "poll",
        "text_en": "TEST_What's the best street food in Saigon?",
        "text_vi": "TEST_Món ăn đường phố ngon nhất ở Sài Gòn?",
        "time_limit_s": 45,
        "options": [],  # Empty options
        "correct_index": None  # No correct answer
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
    assert r.status_code == 200, f"Failed to create poll question: {r.status_code} {r.text}"
    qid = r.json()["id"]
    print(f"✅ Created poll question without options: {qid}")
    
    # Verify it appears in list with empty options
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    added = next(q for q in questions if q["id"] == qid)
    assert added["round_type"] == "poll"
    assert added["options"] == []
    assert added["correct_index"] is None
    print("✅ Poll question has empty options and null correct_index")


def test_classic_question_requires_options():
    """Test that classic questions still require 4 options and correct_index."""
    print("\n🔍 Testing classic question requires options...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Try to add classic question without options - should fail
    new_q = {
        "round_type": "classic",
        "text_en": "TEST_Classic question",
        "options": [],
        "correct_index": None
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
    assert r.status_code in (400, 422), f"Should reject classic without options, got {r.status_code}"
    print("✅ Classic question without options rejected")
    
    # Try with only 3 options - should fail
    new_q = {
        "round_type": "classic",
        "text_en": "TEST_Classic question",
        "options": [{"en": f"Option {i}", "vi": ""} for i in range(3)],
        "correct_index": 0
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
    assert r.status_code in (400, 422), f"Should reject classic with 3 options, got {r.status_code}"
    print("✅ Classic question with 3 options rejected")
    
    # Try without correct_index - should fail
    new_q = {
        "round_type": "classic",
        "text_en": "TEST_Classic question",
        "options": [{"en": f"Option {i}", "vi": ""} for i in range(4)],
        "correct_index": None
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
    assert r.status_code in (400, 422), f"Should reject classic without correct_index, got {r.status_code}"
    print("✅ Classic question without correct_index rejected")
    
    # Valid classic question should succeed
    new_q = {
        "round_type": "classic",
        "text_en": "TEST_Valid classic",
        "options": [{"en": f"Option {i}", "vi": ""} for i in range(4)],
        "correct_index": 0
    }
    r = requests.post(f"{BASE}/rooms/{code}/questions", params={"key": key}, json=new_q)
    assert r.status_code == 200, f"Valid classic should succeed: {r.status_code} {r.text}"
    print("✅ Valid classic question accepted")


def test_news_publish_poll_without_options():
    """Test news draft can be published as poll without options/correct_index if reviewed=true."""
    print("\n🔍 Testing news publish poll without options...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search
    from pymongo import MongoClient
    from datetime import datetime, timezone, timedelta
    
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_client = MongoClient(MONGO_URL)
    db = db_client[os.environ["DB_NAME"]]
    
    search_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    room_doc = db.rooms.find_one({"code": code})
    
    doc = {
        "id": search_id,
        "room_code": code,
        "query": "TEST_poll_publish",
        "cache_key": "test_poll_publish:en",
        "created_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "results": [{
            "id": source_id,
            "title": "TEST_Article",
            "url": "https://test-fixture.example.com/article",
            "description": "TEST_Description",
            "excerpts": ["TEST_Excerpt"],
            "published_at": None,
            "provider": "You.com"
        }],
        "expire_at": room_doc["expire_at"]
    }
    db.news_searches.insert_one(doc)
    print("✅ Inserted fixture search")
    
    # Create draft
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source_id})
    assert r.status_code == 200
    draft_id = r.json()["id"]
    print(f"✅ Created draft: {draft_id}")
    
    # Try to publish as poll without reviewed - should fail
    payload = {
        "text_en": "TEST_Poll question from news",
        "round_type": "poll",
        "options": [],
        "correct_index": None,
        "time_limit_s": 30,
        "reviewed": False
    }
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 400, f"Should reject without reviewed=true, got {r.status_code}"
    print("✅ Publish rejected without reviewed=true")
    
    # Publish as poll with reviewed=true - should succeed
    payload["reviewed"] = True
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code == 200, f"Should accept poll with reviewed=true: {r.status_code} {r.text}"
    qid = r.json()["id"]
    print(f"✅ Published poll question from news: {qid}")
    
    # Verify question in list
    r = requests.get(f"{BASE}/rooms/{code}/questions", params={"key": key})
    questions = r.json()["questions"]
    published = next((q for q in questions if q["id"] == qid), None)
    assert published is not None
    assert published["round_type"] == "poll"
    assert published["options"] == []
    assert published["correct_index"] is None
    print("✅ Published poll has empty options and null correct_index")


def test_news_publish_classic_requires_options():
    """Test news draft published as classic still requires options/correct_index."""
    print("\n🔍 Testing news publish classic requires options...")
    room = mk_room()
    code, key = room["code"], room["host_key"]
    
    # Insert fixture search
    from pymongo import MongoClient
    from datetime import datetime, timezone
    
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_client = MongoClient(MONGO_URL)
    db = db_client[os.environ["DB_NAME"]]
    
    search_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    room_doc = db.rooms.find_one({"code": code})
    
    doc = {
        "id": search_id,
        "room_code": code,
        "query": "TEST_classic_publish",
        "cache_key": "test_classic_publish:en",
        "created_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "results": [{
            "id": source_id,
            "title": "TEST_Article",
            "url": "https://test-fixture.example.com/article",
            "description": "TEST_Description",
            "excerpts": ["TEST_Excerpt"],
            "published_at": None,
            "provider": "You.com"
        }],
        "expire_at": room_doc["expire_at"]
    }
    db.news_searches.insert_one(doc)
    
    # Create draft
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts",
                     params={"key": key},
                     json={"source_id": source_id})
    draft_id = r.json()["id"]
    
    # Try to publish as classic without options - should fail
    payload = {
        "text_en": "TEST_Classic from news",
        "round_type": "classic",
        "options": [],
        "correct_index": None,
        "time_limit_s": 20,
        "reviewed": True
    }
    r = requests.post(f"{BASE}/rooms/{code}/news/drafts/{draft_id}/publish",
                     params={"key": key},
                     json=payload)
    assert r.status_code in (400, 422), f"Should reject classic without options, got {r.status_code}"
    print("✅ Classic publish without options rejected")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 RESPONSE TYPE BACKEND TESTS")
    print("="*60)
    
    try:
        test_poll_question_no_options_required()
        test_classic_question_requires_options()
        test_news_publish_poll_without_options()
        test_news_publish_classic_requires_options()
        
        print("\n" + "="*60)
        print("✅ ALL RESPONSE TYPE BACKEND TESTS PASSED")
        print("="*60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
