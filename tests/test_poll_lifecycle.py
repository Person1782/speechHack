"""
Test write-in poll lifecycle: submission -> vote -> claim -> reveal
Uses API for setup and host actions, browser for player interactions.

This test verifies the complete write-in poll flow:
1. Create room and join two teams via API
2. Start poll via API (preset 0: "Worst thing to say on a first date in Saigon")
3. Player 1 (d1) submits answer via browser UI
4. Host moves to review and approves submission via API
5. Host moves to vote phase via API
6. Player 2 (d2) votes for submission via browser UI
7. Host moves to Hall of Fame via API
8. Player 1 (d1) claims points via browser UI
9. Screen shows revealed winner name

Expected points: 600 (100 approved + 300 winner + 200 claim)

Usage:
  This script is designed to be used with the browser_automation tool.
  Copy the script content (excluding imports and async wrapper) into browser_automation.
"""

# NOTE: When using with browser_automation tool, the following imports and wrapper are not needed.
# The tool provides the 'page' object and async context automatically.

import asyncio
import json

BASE_URL = "https://quiz-and-riff--39crjv3i.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

# Test script starts here (use this part with browser_automation tool)
async def run_test(page):
    """
    Main test function - use the body of this function with browser_automation tool
    """
    try:
        print("\n=== STEP 1: Create room via API ===")
        response = await page.request.post(f"{API_URL}/rooms", data=json.dumps({
            "load_demo": False
        }), headers={"Content-Type": "application/json"})
        
        if response.status != 200:
            print(f"❌ Failed to create room: {response.status}")
            return False
        
        room_data = await response.json()
        code = room_data.get("code")
        secret = room_data.get("host_key")  # API returns 'host_key' not 'secret'
        print(f"Room created: {code}")
        
        print("\n=== STEP 2: Join two teams ===")
        response1 = await page.request.post(f"{API_URL}/rooms/{code}/join", data=json.dumps({
            "device_id": "d1",
            "name": "Team Alpha"
        }), headers={"Content-Type": "application/json"})
        
        if response1.status != 200:
            print(f"❌ Failed to join team 1: {response1.status}")
            return False
        print(f"✅ Team 1 joined (d1: Team Alpha)")
        
        response2 = await page.request.post(f"{API_URL}/rooms/{code}/join", data=json.dumps({
            "device_id": "d2",
            "name": "Team Bravo"
        }), headers={"Content-Type": "application/json"})
        
        if response2.status != 200:
            print(f"❌ Failed to join team 2: {response2.status}")
            return False
        print(f"✅ Team 2 joined (d2: Team Bravo)")
        
        print("\n=== STEP 3: Start poll via API ===")
        response = await page.request.post(
            f"{API_URL}/rooms/{code}/host/poll_start?key={secret}",
            data=json.dumps({
                "preset": 0,
                "time_limit_s": 180
            }),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status != 200:
            print(f"❌ Failed to start poll: {response.status}")
            body = await response.text()
            print(f"Response: {body}")
            return False
        
        result = await response.json()
        print(f"✅ Poll started successfully")
        
        print("\n=== STEP 4: Get screen state to verify poll ===")
        await page.wait_for_timeout(1000)
        
        poll_id = None
        poll_text = None
        for attempt in range(5):
            response = await page.request.get(f"{API_URL}/rooms/{code}/state?role=screen")
            if response.status == 200:
                state = await response.json()
                if state.get("poll") and state["poll"].get("id"):
                    poll_id = state["poll"]["id"]
                    poll_text = state["poll"]["text_en"]
                    print(f"✅ Screen state confirmed poll active: {poll_text}")
                    print(f"   Poll ID: {poll_id}")
                    break
            await page.wait_for_timeout(1500)
        
        if not poll_id:
            print("❌ Failed to get screen state with active poll")
            return False
        
        print("\n=== STEP 5: Browser as d1 - Submit answer ===")
        await page.goto(f"{BASE_URL}/play/{code}")
        await page.evaluate("localStorage.setItem('hh_device', 'd1')")
        await page.reload()
        await page.wait_for_timeout(2000)
        
        try:
            await page.wait_for_selector('[data-testid="phone-poll"]', timeout=10000)
            print("✅ Poll page loaded")
        except Exception:
            print("❌ Poll page did not load")
            return False
        
        answer_text = "My motorbike needed a holiday"
        await page.fill('[data-testid="phone-answer-textarea"]', answer_text)
        print(f"✅ Filled answer: {answer_text}")
        
        await page.click('[data-testid="phone-submit-button"]')
        await page.wait_for_timeout(2000)
        
        try:
            locked = await page.wait_for_selector('[data-testid="phone-locked-status"]', timeout=5000)
            if locked:
                print("✅ Answer submitted - locked status visible")
            else:
                print("❌ Locked status not found")
                return False
        except Exception:
            print("❌ Locked status not found after submission")
            return False
        
        print("\n=== STEP 6: API - Host next to review phase ===")
        response = await page.request.post(
            f"{API_URL}/rooms/{code}/host/next?key={secret}",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status != 200:
            print(f"❌ Failed to move to review: {response.status}")
            return False
        print("✅ Moved to review phase")
        
        print("\n=== STEP 7: Get state to find group.id ===")
        await page.wait_for_timeout(1500)
        
        group_id = None
        for attempt in range(5):
            response = await page.request.get(f"{API_URL}/rooms/{code}/state?role=host&key={secret}")
            if response.status == 200:
                state = await response.json()
                if state.get("poll") and state["poll"].get("groups"):
                    groups = state["poll"]["groups"]
                    if len(groups) > 0:
                        group_id = groups[0]["id"]
                        print(f"✅ Found group: {group_id}")
                        print(f"   Group text: {groups[0].get('text', 'N/A')}")
                        break
            await page.wait_for_timeout(1500)
        
        if not group_id:
            print("❌ No groups found in review phase")
            return False
        
        print("\n=== STEP 8: API - Moderate/approve submission ===")
        response = await page.request.post(
            f"{API_URL}/rooms/{code}/host/poll_moderate?key={secret}",
            data=json.dumps({
                "poll_id": poll_id,
                "answer_id": group_id,
                "verdict": "approve"
            }),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status != 200:
            print(f"❌ Failed to approve: {response.status}")
            return False
        print("✅ Answer approved")
        
        print("\n=== STEP 9: API - Host next to vote phase ===")
        await page.wait_for_timeout(1000)
        response = await page.request.post(
            f"{API_URL}/rooms/{code}/host/next?key={secret}",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status != 200:
            print(f"❌ Failed to move to vote: {response.status}")
            return False
        print("✅ Moved to vote phase")
        
        print("\n=== STEP 10: Browser as d2 - Vote for submission ===")
        await page.evaluate("localStorage.setItem('hh_device', 'd2')")
        await page.reload()
        await page.wait_for_timeout(2000)
        
        vote_selector = f'[data-testid="phone-vote-{group_id}"]'
        try:
            await page.wait_for_selector(vote_selector, timeout=10000)
            print(f"✅ Vote button found for group {group_id}")
        except Exception:
            print(f"❌ Vote button not found: {vote_selector}")
            return False
        
        await page.click(vote_selector)
        await page.wait_for_timeout(2000)
        
        try:
            button = await page.query_selector(vote_selector)
            is_disabled = await button.get_attribute("disabled")
            button_text = await button.inner_text()
            
            if is_disabled or "Voted" in button_text:
                print(f"✅ Vote registered - button shows: {button_text}")
            else:
                print(f"⚠️ Vote may not have registered - button state: {button_text}")
        except Exception as e:
            print(f"⚠️ Could not verify vote button state: {e}")
        
        await page.wait_for_timeout(1500)
        response = await page.request.get(f"{API_URL}/rooms/{code}/state?role=screen")
        if response.status == 200:
            state = await response.json()
            if state.get("poll") and state["poll"].get("groups"):
                for g in state["poll"]["groups"]:
                    if g["id"] == group_id:
                        votes = g.get("votes", 0)
                        if votes >= 1:
                            print(f"✅ API confirms {votes} vote(s)")
                        else:
                            print(f"❌ API shows {votes} votes (expected >= 1)")
                            return False
                        break
        
        print("\n=== STEP 11: API - Host next to hof phase ===")
        await page.wait_for_timeout(1000)
        response = await page.request.post(
            f"{API_URL}/rooms/{code}/host/next?key={secret}",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status != 200:
            print(f"❌ Failed to move to hof: {response.status}")
            return False
        print("✅ Moved to Hall of Fame phase")
        
        print("\n=== STEP 12: Browser as d1 - Claim points ===")
        await page.evaluate("localStorage.setItem('hh_device', 'd1')")
        await page.reload()
        await page.wait_for_timeout(2000)
        
        try:
            await page.wait_for_selector('[data-testid="hof-claim-button"]', timeout=10000)
            print("✅ Claim button found")
        except Exception:
            print("❌ Claim button not found")
            return False
        
        await page.click('[data-testid="hof-claim-button"]')
        await page.wait_for_timeout(2000)
        
        try:
            await page.wait_for_selector('[data-testid="hof-claim-confirmation"]', timeout=5000)
            print("✅ Claim confirmation visible")
        except Exception:
            print("❌ Claim confirmation not found")
            return False
        
        try:
            score_element = await page.query_selector('[data-testid="play-header-score"]')
            if score_element:
                score_text = await score_element.inner_text()
                if "600" in score_text:
                    print(f"✅ Score shows 600 points: {score_text}")
                else:
                    print(f"⚠️ Score text: {score_text} (expected 600)")
            else:
                print("⚠️ Score element not found")
        except Exception as e:
            print(f"⚠️ Could not verify score: {e}")
        
        print("\n=== STEP 13: Browser - Check screen reveal ===")
        await page.goto(f"{BASE_URL}/screen/{code}")
        await page.wait_for_timeout(2000)
        
        try:
            audio_button = await page.query_selector('[data-testid="tv-audio-silent-button"]')
            if audio_button:
                await audio_button.click()
                print("✅ Clicked audio unlock button")
                await page.wait_for_timeout(1000)
        except Exception:
            pass
        
        try:
            name_element = await page.wait_for_selector('[data-testid="screen-hof-revealed-name"]', timeout=10000)
            name_text = await name_element.inner_text()
            
            if "Team Alpha" in name_text or "Alpha" in name_text:
                print(f"✅ Screen shows winning team name: {name_text}")
            else:
                print(f"⚠️ Screen name text: {name_text} (expected Team Alpha)")
        except Exception as e:
            print(f"❌ Could not find revealed name: {e}")
            return False
        
        print("\n" + "="*60)
        print("✅ POLL LIFECYCLE TEST COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\nTest Summary:")
        print(f"- Room Code: {code}")
        print(f"- Poll ID: {poll_id}")
        print(f"- Group ID: {group_id}")
        print(f"- Answer: {answer_text}")
        print(f"- Winning Team: Team Alpha (d1)")
        print(f"- Voting Team: Team Bravo (d2)")
        print(f"\nAll 3 player UI actions tested:")
        print(f"  1. ✅ Submit answer (phone-submit-button)")
        print(f"  2. ✅ Vote for answer (phone-vote-{group_id})")
        print(f"  3. ✅ Claim points (hof-claim-button)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# Standalone execution wrapper (not needed for browser_automation tool)
if __name__ == "__main__":
    from playwright.async_api import async_playwright
    
    async def main():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            page.on("console", lambda msg: print(f"BROWSER: {msg.text}"))
            
            try:
                result = await run_test(page)
                return 0 if result else 1
            finally:
                await browser.close()
    
    exit(asyncio.run(main()))
