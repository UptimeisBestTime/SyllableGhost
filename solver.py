import os
import time
import random
import requests
import whisper
from playwright.sync_api import sync_playwright

# --- Configuration ---
WHISPER_MODEL = "tiny" # Using 'tiny' for the fastest CPU execution in the VM
TARGET_URL = "https://www.google.com/recaptcha/api2/demo"
AUDIO_FILENAME = "payload.mp3"

def random_delay(min_sec=1.0, max_sec=2.5):
    """Simulate human reaction times to avoid instant bot flagging."""
    time.sleep(random.uniform(min_sec, max_sec))

def download_audio(url, filename):
    print("[*] Downloading audio payload...")
    # Spoofing a standard user agent so the download isn't rejected
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    response = requests.get(url, headers=headers)
    with open(filename, "wb") as f:
        f.write(response.content)

def transcribe_audio(filename):
    print(f"[*] Loading Whisper '{WHISPER_MODEL}' model and transcribing...")
    model = whisper.load_model(WHISPER_MODEL)
    # fp16=False is critical here since we are running on a CPU, not an NVIDIA GPU
    result = model.transcribe(filename, fp16=False)
    
    # Clean the output to just the alphanumeric characters we need
    raw_text = result["text"].strip().lower()
    clean_text = "".join(char for char in raw_text if char.isalnum() or char.isspace())
    return clean_text

def main():
    with sync_playwright() as p:
        print("[*] Booting Playwright Stealth Browser...")
        browser = p.chromium.launch(
            headless=False, # We want to watch the magic happen
	    slow_mo=1000, # This adds a 1-second delay to EVERY Playwright action
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print(f"[*] Navigating to {TARGET_URL}")
            page.goto(TARGET_URL)
            random_delay()

            # 1. Target the primary checkbox iframe
            print("[*] Piercing primary iframe and clicking checkbox...")
            checkbox_frame = page.frame_locator("iframe[title*='reCAPTCHA']")
            checkbox_frame.locator(".recaptcha-checkbox").click()
            random_delay(1.5, 3.0)

            # 2. Target the challenge popup iframe
            print("[*] Locating secondary challenge iframe...")
            challenge_frame = page.frame_locator("iframe[title*='recaptcha challenge']")
            
            # Switch to Audio Challenge
            print("[*] Requesting Audio Challenge fallback...")
            audio_button = challenge_frame.locator("button#recaptcha-audio-button")
            audio_button.wait_for(state="visible", timeout=10000)
            audio_button.click()
            random_delay()

            # 3. Extract and Download the Payload
            print("[*] Intercepting audio source URL...")
            audio_element = challenge_frame.locator("audio#audio-source")
            audio_element.wait_for(state="attached", timeout=5000)
            audio_url = audio_element.get_attribute("src")

            if not audio_url:
                raise Exception("Could not locate the audio URL.")

            download_audio(audio_url, AUDIO_FILENAME)

            # 4. Neural Network Transcription
            solved_text = transcribe_audio(AUDIO_FILENAME)
            print(f"\n[!!!] WHISPER EXTRACTED: '{solved_text}'\n")

            # 5. Injection and Verification
            print("[*] Injecting payload into DOM...")
            response_input = challenge_frame.locator("input#audio-response")
            response_input.fill(solved_text)
            random_delay(0.5, 1.5)

            print("[*] Submitting...")
            verify_button = challenge_frame.locator("button#recaptcha-verify-button")
            verify_button.click()

            print("[+] Attack chain complete! Holding browser open for 10 seconds to verify.")
            time.sleep(10)

        except Exception as e:
            print(f"[!] Execution failed: {e}")
        
        finally:
            if os.path.exists(AUDIO_FILENAME):
                os.remove(AUDIO_FILENAME)
            browser.close()

if __name__ == "__main__":
    main()
