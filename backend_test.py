"""
Comprehensive backend API tests for Heckle & Hint Tier 1
Tests against the public endpoint
"""
import requests
import time
import uuid
import json
import sys

BASE_URL = "https://quiz-and-riff--39crjv3i.preview.emergentagent.com/api"

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.total = 0

    def add_pass(self, test_name):
        self.total += 1
        self.passed.append(test_name)
        print(f"✅ PASS: {test_name}")

    def add_fail(self, test_name, reason):
        self.total += 1
        self.failed.append({"test": test_name, "reason": reason})
        print(f"❌ FAIL: {test_name} - {reason}")

    def summary(self):
        print("\n" + "="*60)
        print(f"BACKEND TEST SUMMARY: {len(self.passed)}/{self.total} passed")
        print("="*60)
        if self.failed:
            print("\nFailed tests:")
            for f in self.failed:
                print(f"  - {f['test']}: {f['reason']}")
        return len(self.failed) == 0

results = TestResults()

def create_room(load_demo=False):
    """Helper to create a test room"""
    try:
        r = requests.post(f"{BASE_URL}/rooms", json={
            "host_name": "TEST_Comic",
            "venue_name": "TEST_Bar",
            "night_preset": "demo",
            "load_demo": load_demo
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data["code"], data["host_key"]
    except Exception as e:
        print(f"Failed to create room: {e}")
        return None, None

def get_state(code, role, key=None, device=None, since_version=None):
    """Helper to get room state"""
    params = {"role": role}
    if key:
        params["key"] = key
    if device:
        params["device"] = device
    if since_version is not None:
        params["since_version"] = since_version
    try:
        r = requests.get(f"{BASE_URL}/rooms/{code}/state", params=params, timeout=10)
        return r
    except Exception as e:
        print(f"Failed to get state: {e}")
        return None

def host_action(code, key, action, body=None):
    """Helper for host actions"""
    if body is None:
        body = {}
    body["client_request_id"] = uuid.uuid4().hex
    try:
        r = requests.post(f"{BASE_URL}/rooms/{code}/host/{action}",
                         params={"key": key}, json=body, timeout=10)
        return r
    except Exception as e:
        print(f"Failed host action {action}: {e}")
        return None

def join_team(code, name, device_id=None):
    """Helper to join a team"""
    if device_id is None:
        device_id = f"TEST_{uuid.uuid4().hex[:8]}"
    try:
        r = requests.post(f"{BASE_URL}/rooms/{code}/join", json={
            "device_id": device_id,
            "name": name,
            "emoji": "🍜",
            "roast_level": "mild"
        }, timeout=10)
        r.raise_for_status()
        return device_id, r.json()["team_id"]
    except Exception as e:
        print(f"Failed to join team: {e}")
        return None, None

# TEST 1: Create room returns 4-letter code without I/O
print("\n" + "="*60)
print("TEST 1: POST /api/rooms creates room with valid code")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        if len(code) == 4 and code.isalpha() and code.isupper():
            if "I" not in code and "O" not in code:
                results.add_pass("Room creation with valid code (no I/O)")
            else:
                results.add_fail("Room creation", f"Code contains I or O: {code}")
        else:
            results.add_fail("Room creation", f"Invalid code format: {code}")
    else:
        results.add_fail("Room creation", "Failed to create room")
except Exception as e:
    results.add_fail("Room creation", str(e))

# TEST 2: 403 without host key
print("\n" + "="*60)
print("TEST 2: Host actions without key return 403")
print("="*60)
try:
    code, key = create_room()
    if code:
        # Test GET state without key
        r = get_state(code, "host")
        if r and r.status_code == 403:
            results.add_pass("GET state role=host without key returns 403")
        else:
            results.add_fail("GET state 403", f"Got status {r.status_code if r else 'None'}")

        # Test POST actions without key
        for action in ["next", "reset", "blackout", "load_demo", "freeze"]:
            r = requests.post(f"{BASE_URL}/rooms/{code}/host/{action}", json={}, timeout=10)
            if r.status_code == 403:
                results.add_pass(f"POST {action} without key returns 403")
            else:
                results.add_fail(f"POST {action} 403", f"Got status {r.status_code}")

        # Test with wrong key
        r = requests.post(f"{BASE_URL}/rooms/{code}/host/next",
                         params={"key": "wrong_key"}, json={}, timeout=10)
        if r.status_code == 403:
            results.add_pass("POST with wrong key returns 403")
        else:
            results.add_fail("POST wrong key 403", f"Got status {r.status_code}")
except Exception as e:
    results.add_fail("403 tests", str(e))

# TEST 3: Role filtering - screen and player never see spoilers
print("\n" + "="*60)
print("TEST 3: Role filtering (no spoilers for screen/player)")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        # Join a team
        dev, tid = join_team(code, "TEST_Team_Alpha")

        # Advance to question_open
        for _ in range(3):  # lobby -> cold_open -> round_intro -> question_open
            host_action(code, key, "next")
        time.sleep(0.5)

        # Check screen role
        r = get_state(code, "screen")
        if r and r.status_code == 200:
            raw_text = r.text
            banned = ["correct_index", "punchline", "notes", "setup_line", "host_key", "fake_explanations", "hint_joke", "device_id"]
            found_spoilers = [b for b in banned if b in raw_text]
            if not found_spoilers:
                results.add_pass("Screen role: no spoilers before reveal")
            else:
                results.add_fail("Screen role spoilers", f"Found: {found_spoilers}")

        # Check player role
        r = get_state(code, "player", device=dev)
        if r and r.status_code == 200:
            raw_text = r.text
            data = r.json()
            # Player should see their own secret_word
            if data.get("me") and data["me"].get("secret_word"):
                results.add_pass("Player sees own secret_word")
            else:
                results.add_fail("Player secret_word", "Missing secret_word")

            # But not spoilers
            banned = ["correct_index", "punchline", "notes", "setup_line", "host_key", "fake_explanations", "hint_joke"]
            found_spoilers = [b for b in banned if b in raw_text]
            if not found_spoilers:
                results.add_pass("Player role: no spoilers before reveal")
            else:
                results.add_fail("Player role spoilers", f"Found: {found_spoilers}")
except Exception as e:
    results.add_fail("Role filtering", str(e))

# TEST 4: since_version returns unchanged:true
print("\n" + "="*60)
print("TEST 4: since_version polling")
print("="*60)
try:
    code, key = create_room()
    if code:
        r = get_state(code, "screen")
        if r and r.status_code == 200:
            version = r.json()["version"]
            r2 = get_state(code, "screen", since_version=version)
            if r2 and r2.status_code == 200:
                data = r2.json()
                if data.get("unchanged") is True:
                    results.add_pass("since_version returns unchanged:true")
                else:
                    results.add_fail("since_version", f"Got: {data}")
except Exception as e:
    results.add_fail("since_version", str(e))

# TEST 5: Classic flow with 3 teams
print("\n" + "="*60)
print("TEST 5: Classic flow with 3 teams")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        # Join 3 teams
        teams = []
        for name in ["TEST_Alpha", "TEST_Bravo", "TEST_Charlie"]:
            dev, tid = join_team(code, name)
            if dev and tid:
                teams.append((dev, tid))

        if len(teams) == 3:
            results.add_pass("3 teams joined successfully")

            # Advance to question_open
            for _ in range(3):
                host_action(code, key, "next")
            time.sleep(0.5)

            r = get_state(code, "host", key=key)
            if r and r.status_code == 200:
                state = r.json()
                if state["phase"] == "question_open":
                    results.add_pass("Advanced to question_open phase")

                    q = state["host"]["question"]
                    correct_idx = q["correct_index"]
                    qid = q["id"]

                    # Submit answers: team0 correct, team1 wrong, team2 correct
                    answers = [
                        (teams[0][0], correct_idx),
                        (teams[1][0], (correct_idx + 1) % 4),
                        (teams[2][0], correct_idx)
                    ]

                    for dev, opt in answers:
                        r = requests.post(f"{BASE_URL}/rooms/{code}/answer", json={
                            "device_id": dev,
                            "question_id": qid,
                            "option_index": opt,
                            "client_request_id": uuid.uuid4().hex
                        }, timeout=10)
                        if r.status_code == 200:
                            pass
                        else:
                            print(f"Answer failed: {r.status_code}")

                    time.sleep(0.5)

                    # Check auto-lock
                    r = get_state(code, "screen")
                    if r and r.status_code == 200:
                        state = r.json()
                        if state["phase"] == "question_locked":
                            results.add_pass("Auto-lock after all teams answered")

                            # Verify no spoilers in locked phase
                            raw = r.text
                            if "correct_index" not in raw and "counts" not in raw:
                                results.add_pass("No spoilers in question_locked phase")
                            else:
                                results.add_fail("Locked phase spoilers", "Found correct_index or counts")
                        else:
                            results.add_fail("Auto-lock", f"Phase is {state['phase']}")

                    # Host reveals
                    host_action(code, key, "next")
                    time.sleep(0.5)

                    r = get_state(code, "screen")
                    if r and r.status_code == 200:
                        state = r.json()
                        if state["phase"] == "reveal":
                            results.add_pass("Reveal phase reached")
                            if state["reveal"]["correct_index"] == correct_idx:
                                results.add_pass("Correct answer shown in reveal")
                        else:
                            results.add_fail("Reveal phase", f"Phase is {state['phase']}")

                    # Check player results
                    r = get_state(code, "player", device=teams[0][0])
                    if r and r.status_code == 200:
                        state = r.json()
                        if state.get("my_result"):
                            if state["my_result"]["correct"]:
                                results.add_pass("Player 0 (correct) sees correct result")
                                if 500 <= state["my_result"]["points"] <= 1000:
                                    results.add_pass("Player 0 points in valid range")
                            else:
                                results.add_fail("Player 0 result", "Should be correct")

                    r = get_state(code, "player", device=teams[1][0])
                    if r and r.status_code == 200:
                        state = r.json()
                        if state.get("my_result"):
                            if not state["my_result"]["correct"] and state["my_result"]["points"] == 0:
                                results.add_pass("Player 1 (wrong) sees wrong result with 0 points")
                            else:
                                results.add_fail("Player 1 result", f"Should be wrong with 0 points, got {state['my_result']}")
                else:
                    results.add_fail("Phase advance", f"Phase is {state['phase']}")
        else:
            results.add_fail("Team joining", f"Only {len(teams)} teams joined")
except Exception as e:
    results.add_fail("Classic flow", str(e))

# TEST 6: Idempotency
print("\n" + "="*60)
print("TEST 6: Idempotent answer submission")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        dev, tid = join_team(code, "TEST_Idempotent")

        # Advance to question_open
        for _ in range(3):
            host_action(code, key, "next")
        time.sleep(0.5)

        r = get_state(code, "host", key=key)
        if r and r.status_code == 200:
            q = r.json()["host"]["question"]
            qid = q["id"]
            crid = uuid.uuid4().hex

            # Submit same answer twice with same client_request_id
            body = {
                "device_id": dev,
                "question_id": qid,
                "option_index": 0,
                "client_request_id": crid
            }

            r1 = requests.post(f"{BASE_URL}/rooms/{code}/answer", json=body, timeout=10)
            r2 = requests.post(f"{BASE_URL}/rooms/{code}/answer", json=body, timeout=10)

            if r1.status_code == 200 and r2.status_code == 200:
                data1 = r1.json()
                data2 = r2.json()
                if data1.get("ok") and not data1.get("duplicate"):
                    if data2.get("duplicate"):
                        results.add_pass("Second answer with same crid returns duplicate")
                    else:
                        results.add_fail("Idempotency", "Second answer should be duplicate")
                else:
                    results.add_fail("Idempotency", "First answer failed")
except Exception as e:
    results.add_fail("Idempotency", str(e))

# TEST 7: Late join returns 409
print("\n" + "="*60)
print("TEST 7: Late join (after question opens) returns 409")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        # Join early team
        join_team(code, "TEST_Early")

        # Advance to question_open
        for _ in range(3):
            host_action(code, key, "next")
        time.sleep(0.5)

        # Join late team
        late_dev, late_tid = join_team(code, "TEST_Late")

        r = get_state(code, "player", device=late_dev)
        if r and r.status_code == 200:
            state = r.json()
            if state.get("me") and state["me"].get("eligible") is False:
                results.add_pass("Late joiner marked as ineligible")

                # Try to answer
                r = get_state(code, "host", key=key)
                if r and r.status_code == 200:
                    q = r.json()["host"]["question"]
                    r = requests.post(f"{BASE_URL}/rooms/{code}/answer", json={
                        "device_id": late_dev,
                        "question_id": q["id"],
                        "option_index": 0,
                        "client_request_id": uuid.uuid4().hex
                    }, timeout=10)
                    if r.status_code == 409:
                        results.add_pass("Late joiner answer returns 409")
                    else:
                        results.add_fail("Late join 409", f"Got status {r.status_code}")
            else:
                results.add_fail("Late join eligible", "Should be ineligible")
except Exception as e:
    results.add_fail("Late join", str(e))

# TEST 8: Flagged team name
print("\n" + "="*60)
print("TEST 8: Flagged team name shows as null until approved")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        dev, tid = join_team(code, "Shit Happens")
        time.sleep(0.3)

        r = get_state(code, "screen")
        if r and r.status_code == 200:
            state = r.json()
            team = next((t for t in state["teams"] if t["id"] == tid), None)
            if team:
                if team["name"] is None:
                    results.add_pass("Flagged team name shows as null on screen")

                    # Check raw JSON doesn't contain the word
                    if "Shit" not in r.text:
                        results.add_pass("Flagged word not in screen JSON")
                    else:
                        results.add_fail("Flagged word leak", "Found 'Shit' in screen JSON")

                    # Approve name
                    host_action(code, key, "team", {"op": "approve_name", "team_id": tid})
                    time.sleep(0.3)

                    r = get_state(code, "screen")
                    if r and r.status_code == 200:
                        state = r.json()
                        team = next((t for t in state["teams"] if t["id"] == tid), None)
                        if team and team["name"] == "Shit Happens":
                            results.add_pass("Approved team name now visible")
                        else:
                            results.add_fail("Approve name", f"Name is {team['name'] if team else 'missing'}")
                else:
                    results.add_fail("Flagged name", f"Name should be null, got {team['name']}")
except Exception as e:
    results.add_fail("Flagged team name", str(e))

# TEST 9: Demo data loads 8 teams
print("\n" + "="*60)
print("TEST 9: Load demo data creates 8 teams")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        # Load demo
        host_action(code, key, "load_demo")
        time.sleep(2.5)  # Wait for demo teams to appear

        r = get_state(code, "screen")
        if r and r.status_code == 200:
            state = r.json()
            if state["team_count"] == 8:
                results.add_pass("Demo data loaded 8 teams within 2.5s")
            else:
                results.add_fail("Demo data", f"Got {state['team_count']} teams, expected 8")
except Exception as e:
    results.add_fail("Demo data", str(e))

# TEST 10: Blackout hides team names
print("\n" + "="*60)
print("TEST 10: Blackout mode hides team names and fun facts")
print("="*60)
try:
    code, key = create_room(load_demo=True)
    if code and key:
        time.sleep(2)  # Wait for demo teams

        # Enable blackout
        host_action(code, key, "blackout", {"value": True})
        time.sleep(0.3)

        r = get_state(code, "screen")
        if r and r.status_code == 200:
            state = r.json()
            teams = state.get("teams", [])
            if teams:
                all_null = all(t["name"] is None for t in teams)
                if all_null:
                    results.add_pass("Blackout: all team names are null")
                else:
                    results.add_fail("Blackout names", "Some names not null")

                if state.get("fun_facts") == []:
                    results.add_pass("Blackout: fun_facts empty")
                else:
                    results.add_fail("Blackout fun_facts", f"Got {state.get('fun_facts')}")
except Exception as e:
    results.add_fail("Blackout", str(e))

# TEST 11: Timer and freeze
print("\n" + "="*60)
print("TEST 11: Timer +10s and freeze/unfreeze")
print("="*60)
try:
    code, key = create_room()
    if code and key:
        join_team(code, "TEST_Timer")

        # Advance to question_open
        for _ in range(3):
            host_action(code, key, "next")
        time.sleep(0.5)

        r = get_state(code, "host", key=key)
        if r and r.status_code == 200:
            ends1 = r.json()["phase_ends_at"]

            # Add 10s
            host_action(code, key, "add_time")
            time.sleep(0.3)

            r = get_state(code, "host", key=key)
            if r and r.status_code == 200:
                ends2 = r.json()["phase_ends_at"]
                if ends2 == ends1 + 10000:
                    results.add_pass("add_time extends phase_ends_at by 10000ms")
                else:
                    results.add_fail("add_time", f"Expected {ends1 + 10000}, got {ends2}")

            # Freeze
            host_action(code, key, "freeze")
            time.sleep(0.3)

            r = get_state(code, "screen")
            if r and r.status_code == 200:
                if r.json().get("frozen") is True:
                    results.add_pass("Freeze sets frozen=true")
                else:
                    results.add_fail("Freeze", "frozen not true")

            # Unfreeze
            host_action(code, key, "freeze")
            time.sleep(0.3)

            r = get_state(code, "screen")
            if r and r.status_code == 200:
                if r.json().get("frozen") is False:
                    results.add_pass("Unfreeze sets frozen=false")
                else:
                    results.add_fail("Unfreeze", "frozen not false")
except Exception as e:
    results.add_fail("Timer/freeze", str(e))

# Print summary
print("\n")
success = results.summary()
sys.exit(0 if success else 1)
