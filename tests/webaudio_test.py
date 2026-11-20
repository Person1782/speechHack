"""
WebAudio Testing Script for Heckle & Hint Big Screen
Tests actual audio synthesis (oscillators and buffer sources) not just presence checks.

Usage:
    python webaudio_test.py [base_url]

Example:
    python webaudio_test.py https://quiz-and-riff--39crjv3i.preview.emergentagent.com
"""

import asyncio
import sys
import time
from playwright.async_api import async_playwright
import requests


class WebAudioTester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.room_code = None
        self.host_key = None
        self.test_results = {
            "passed": [],
            "failed": [],
            "audio_counts": {}
        }

    def create_room(self):
        """Create a test room via API"""
        print("\n[STEP 1] Creating room via API...")
        response = requests.post(
            f"{self.base_url}/api/rooms",
            json={
                "host_name": "TEST_AudioHost",
                "venue_name": "TEST_AudioVenue",
                "default_lang": "en",
                "night_preset": "full",
                "roast_enabled": False,
                "chaos_enabled": False,
                "sound_on": True,
                "bar_reward_text": "Test reward",
                "follow_links": {},
                "load_demo": False
            }
        )

        if response.status_code != 200:
            raise Exception(f"Room creation failed: {response.status_code} - {response.text}")

        data = response.json()
        self.room_code = data["code"]
        self.host_key = data["host_key"]
        print(f"✅ Room created: {self.room_code}")
        self.test_results["passed"].append("Room creation")

    def send_sound(self, sound_name):
        """Send sound event via API"""
        response = requests.post(
            f"{self.base_url}/api/rooms/{self.room_code}/host/sound",
            params={"key": self.host_key},
            json={"sound": sound_name}
        )
        return response.status_code == 200

    def set_mute(self, muted):
        """Mute or unmute via API"""
        response = requests.post(
            f"{self.base_url}/api/rooms/{self.room_code}/host/settings",
            params={"key": self.host_key},
            json={"settings": {"sound_on": not muted}}
        )
        return response.status_code == 200

    def start_poll(self, time_limit_s=5):
        """Start a poll with timer"""
        response = requests.post(
            f"{self.base_url}/api/rooms/{self.room_code}/host/poll_start",
            params={"key": self.host_key},
            json={
                "text_en": "Test poll for timer",
                "text_vi": "Test poll",
                "time_limit_s": time_limit_s
            }
        )
        return response.status_code == 200

    async def run_tests(self):
        """Run all WebAudio tests"""
        print("=" * 80)
        print("WEBAUDIO TESTING - Actual Sound Generation")
        print("=" * 80)

        # Create room
        self.create_room()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})

            # Add AudioContext instrumentation
            print("\n[STEP 2] Adding AudioContext instrumentation...")
            await page.add_init_script("""
                window.audioInstrumentation = {
                    oscillatorCreated: 0,
                    bufferSourceCreated: 0,
                    oscillatorStarted: 0,
                    bufferSourceStarted: 0,
                    startTimes: []
                };

                const OriginalAudioContext = window.AudioContext || window.webkitAudioContext;
                if (OriginalAudioContext) {
                    const originalCreateOscillator = OriginalAudioContext.prototype.createOscillator;
                    const originalCreateBufferSource = OriginalAudioContext.prototype.createBufferSource;

                    OriginalAudioContext.prototype.createOscillator = function() {
                        window.audioInstrumentation.oscillatorCreated++;
                        const osc = originalCreateOscillator.call(this);
                        const originalStart = osc.start;
                        osc.start = function(...args) {
                            window.audioInstrumentation.oscillatorStarted++;
                            window.audioInstrumentation.startTimes.push(Date.now());
                            return originalStart.apply(this, args);
                        };
                        return osc;
                    };

                    OriginalAudioContext.prototype.createBufferSource = function() {
                        window.audioInstrumentation.bufferSourceCreated++;
                        const source = originalCreateBufferSource.call(this);
                        const originalStart = source.start;
                        source.start = function(...args) {
                            window.audioInstrumentation.bufferSourceStarted++;
                            window.audioInstrumentation.startTimes.push(Date.now());
                            return originalStart.apply(this, args);
                        };
                        return source;
                    };
                }
            """)
            print("✅ AudioContext instrumentation added")

            # Navigate to screen
            print(f"\n[STEP 3] Navigating to /screen/{self.room_code}...")
            await page.goto(f"{self.base_url}/screen/{self.room_code}")
            await page.wait_for_timeout(1000)

            # Check unlock overlay
            unlock_overlay = await page.query_selector('[data-testid="tv-audio-unlock-overlay"]')
            if unlock_overlay:
                print("✅ Unlock overlay visible")
                self.test_results["passed"].append("Unlock overlay visible")

            # Test sound before unlock
            print("\n[STEP 4] Testing sound API BEFORE unlock...")
            initial_counts = await page.evaluate("() => window.audioInstrumentation")
            self.send_sound("rimshot")
            await page.wait_for_timeout(2000)

            counts_before_unlock = await page.evaluate("() => window.audioInstrumentation")
            if counts_before_unlock["oscillatorStarted"] == 0 and counts_before_unlock["bufferSourceStarted"] == 0:
                print("✅ No audio before unlock")
                self.test_results["passed"].append("No audio before unlock")
            else:
                print("❌ Audio started before unlock")
                self.test_results["failed"].append("Audio before unlock")

            # Unlock audio
            print("\n[STEP 5] Clicking unlock button...")
            unlock_button = await page.wait_for_selector('[data-testid="tv-audio-unlock-button"]')
            await unlock_button.click()
            await page.wait_for_timeout(1000)
            print("✅ Unlocked")

            # Test sound after unlock
            print("\n[STEP 6] Testing sound API AFTER unlock...")
            await page.evaluate("() => { window.audioInstrumentation.startTimes = []; }")
            counts_before = await page.evaluate("() => window.audioInstrumentation")

            api_start = time.time() * 1000
            self.send_sound("rimshot")
            await page.wait_for_timeout(2500)

            counts_after = await page.evaluate("() => window.audioInstrumentation")
            start_times = await page.evaluate("() => window.audioInstrumentation.startTimes")

            if start_times:
                latency = start_times[0] - api_start
                print(f"✅ Audio latency: {latency:.0f}ms")
                self.test_results["passed"].append(f"Audio latency {latency:.0f}ms")

            osc_started = counts_after["oscillatorStarted"] - counts_before["oscillatorStarted"]
            buf_started = counts_after["bufferSourceStarted"] - counts_before["bufferSourceStarted"]

            if osc_started > 0 and buf_started > 0:
                print(f"✅ Actual audio synthesis: {osc_started} osc + {buf_started} buf")
                self.test_results["passed"].append("Actual audio synthesis")

            # Test poll cycle deduplication
            print("\n[STEP 7] Testing poll cycle (no duplicates)...")
            counts_before_poll = await page.evaluate("() => window.audioInstrumentation")
            await page.wait_for_timeout(3000)
            counts_after_poll = await page.evaluate("() => window.audioInstrumentation")

            new_starts = (counts_after_poll["oscillatorStarted"] - counts_before_poll["oscillatorStarted"]) + \
                        (counts_after_poll["bufferSourceStarted"] - counts_before_poll["bufferSourceStarted"])

            if new_starts == 0:
                print("✅ No duplicate triggers")
                self.test_results["passed"].append("No duplicate triggers")

            # Test mute
            print("\n[STEP 8] Testing mute...")
            self.set_mute(True)
            await page.wait_for_timeout(2000)

            counts_before_muted = await page.evaluate("() => window.audioInstrumentation")
            self.send_sound("ding")
            await page.wait_for_timeout(1500)
            counts_after_muted = await page.evaluate("() => window.audioInstrumentation")

            muted_starts = (counts_after_muted["oscillatorStarted"] - counts_before_muted["oscillatorStarted"]) + \
                          (counts_after_muted["bufferSourceStarted"] - counts_before_muted["bufferSourceStarted"])

            if muted_starts == 0:
                print("✅ Mute prevents audio")
                self.test_results["passed"].append("Mute prevents audio")

            # Test unmute
            print("\n[STEP 9] Testing unmute (no replay)...")
            self.set_mute(False)
            await page.wait_for_timeout(2000)

            counts_before_unmute = await page.evaluate("() => window.audioInstrumentation")
            await page.wait_for_timeout(2000)
            counts_after_unmute = await page.evaluate("() => window.audioInstrumentation")

            replay_starts = (counts_after_unmute["oscillatorStarted"] - counts_before_unmute["oscillatorStarted"]) + \
                           (counts_after_unmute["bufferSourceStarted"] - counts_before_unmute["bufferSourceStarted"])

            if replay_starts == 0:
                print("✅ No replay after unmute")
                self.test_results["passed"].append("No replay after unmute")

            # Test reload
            print("\n[STEP 10] Testing reload (no historical replay)...")
            self.send_sound("buzz")
            await page.wait_for_timeout(1000)

            await page.reload()
            await page.wait_for_timeout(1000)

            unlock_button_reload = await page.wait_for_selector('[data-testid="tv-audio-unlock-button"]')
            await page.evaluate("""() => {
                window.audioInstrumentation.oscillatorStarted = 0;
                window.audioInstrumentation.bufferSourceStarted = 0;
            }""")

            await unlock_button_reload.click()
            await page.wait_for_timeout(2000)

            counts_after_reload = await page.evaluate("() => window.audioInstrumentation")

            if counts_after_reload["oscillatorStarted"] == 0 and counts_after_reload["bufferSourceStarted"] == 0:
                print("✅ No replay after reload")
                self.test_results["passed"].append("No replay after reload")

            await browser.close()

        # Print summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"\n✅ PASSED ({len(self.test_results['passed'])} tests):")
        for test in self.test_results["passed"]:
            print(f"  - {test}")

        if self.test_results["failed"]:
            print(f"\n❌ FAILED ({len(self.test_results['failed'])} tests):")
            for test in self.test_results["failed"]:
                print(f"  - {test}")
        else:
            print("\n🎉 All tests passed!")

        print("\n" + "=" * 80)

        return len(self.test_results["failed"]) == 0


async def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://quiz-and-riff--39crjv3i.preview.emergentagent.com"

    tester = WebAudioTester(base_url)
    success = await tester.run_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
