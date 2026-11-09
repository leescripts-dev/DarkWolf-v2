import os
import re
import time
import socket
import subprocess
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============================================================
TOR_BROWSER_BINARY = r"C:\Users\USER\Desktop\Tor Browser\Browser\firefox.exe"
TOR_PROFILE_PATH   = r"C:\Users\USER\Desktop\Tor Browser\Browser\TorBrowser\Data\Browser\profile.default"
TOR_DAEMON_PATH    = r"C:\Users\USER\Desktop\Tor Browser\Browser\TorBrowser\Tor\tor.exe"
GECKODRIVER_PATH   = r"C:\GekkoDriver\geckodriver.exe"
TOR_SOCKS_PORT     = 9050

TARGET_URL = "http://i62huw7ve22rpyw6lnq3kmfump2dmsg4xpveec3ere73njwatrz74gad.onion/"
SAVE_DIR   = r"d:\WolfCaptcha\cloak\data"
MAX_CAPS   = 1000
# ============================================================


def start_tor_daemon():
    """Start tor.exe explicitly and wait for SOCKS port."""
    def port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0

    if port_open(TOR_SOCKS_PORT):
        print(f"Tor already running on port {TOR_SOCKS_PORT}.")
        return None

    print(f"Starting Tor daemon: {TOR_DAEMON_PATH}")
    tor_proc = subprocess.Popen(
        [TOR_DAEMON_PATH, "--SocksPort", str(TOR_SOCKS_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(TOR_BOOTSTRAP_WAIT):
        if port_open(TOR_SOCKS_PORT):
            print("Tor is ready.")
            return tor_proc
        time.sleep(1)

    raise RuntimeError("Tor did not open port.")


def solve_math_captcha(question_text):
    """Extract math expression and compute the answer."""
    match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', question_text)
    if match:
        a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
        if op == '+':
            return a + b
        elif op == '-':
            return a - b
        elif op == '*':
            return a * b
        elif op == '/':
            return round(a / b, 2)
    print(f"  ⚠️ Could not parse: {question_text}")
    return None


def main():
    existing = [f for f in os.listdir(SAVE_DIR) if f.endswith(".txt")]
    idx = len(existing) + 1
    print(f"Resuming — {len(existing)} already labeled. Next index: {idx:05d}")

    # Start Tor explicitly
    tor_proc = start_tor_daemon()

    o = webdriver.FirefoxOptions()
    o.binary_location = TOR_BROWSER_BINARY
    o.add_argument("-profile")
    o.add_argument(TOR_PROFILE_PATH)
    o.set_preference("network.proxy.type", 1)
    o.set_preference("network.proxy.socks", "127.0.0.1")
    o.set_preference("network.proxy.socks_port", TOR_SOCKS_PORT)
    o.set_preference("network.proxy.socks_remote_dns", True)
    o.set_preference("network.proxy.socks_version", 5)

    driver = webdriver.Firefox(service=Service(GECKODRIVER_PATH), options=o)
    try:
        print(f"Navigating to {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(8)

        page_title = driver.title.strip()
        print(f"  Page title: '{page_title}'")

        solved = 0
        while solved < MAX_CAPS:
            # 1. Get the math question text
            try:
                question_el = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#captcha-question"))
                )
                question_text = question_el.text
            except Exception as e:
                print(f"  ⚠️ Question element not found ({e}), refreshing...")
                driver.refresh()
                time.sleep(6)
                continue

            print(f"\n  Q: {question_text}")

            # 2. Solve it
            answer = solve_math_captcha(question_text)
            if answer is None:
                print("  Skipping — could not solve.")
                driver.refresh()
                time.sleep(2)
                continue

            print(f"  A: {answer}")

            # 3. Save label
            base = os.path.join(SAVE_DIR, f"{idx:05d}")
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(f"{question_text}\n{answer}")

            # 4. Take a screenshot for reference
            box_el = driver.find_element(By.CSS_SELECTOR, "#captcha-box")
            png = box_el.screenshot_as_png
            with open(base + ".png", "wb") as f:
                f.write(png)

            # 5. Submit via Selenium
            try:
                input_el = driver.find_element(By.CSS_SELECTOR, "#captcha-input")
                input_el.clear()
                input_el.send_keys(str(answer))
                driver.find_element(By.CSS_SELECTOR, "#captcha-button").click()
                time.sleep(2)
                solved += 1
                idx += 1
                print(f"  ✓ Submitted #{idx-1:05d} — answer: {answer}")

                # Check for success message
                try:
                    msg_el = driver.find_element(By.CSS_SELECTOR, "#captcha-message")
                    msg = msg_el.text.strip()
                    if msg:
                        print(f"  Response: {msg}")
                except Exception:
                    pass

                # If the question changed, first solve succeeded — stop and keep browser open
                try:
                    new_question = driver.find_element(By.CSS_SELECTOR, "#captcha-question").text
                    if new_question != question_text:
                        print(f"  Next question loaded: {new_question}")
                        print("\n  === First captcha solved! Browser stays open. ===")
                        print("  Press Ctrl+C to close manually, or wait...")
                        break
                    else:
                        # Same question = submission may have failed, force refresh
                        print("  ⚠️ Question did not change — refreshing...")
                        driver.refresh()
                        time.sleep(3)
                except Exception:
                    print("  ⚠️ Could not verify next question — refreshing...")
                    driver.refresh()
                    time.sleep(3)

            except Exception as e:
                print(f"  ⚠️ Submission failed: {e}")
                driver.refresh()
                time.sleep(3)

            time.sleep(1)

    finally:
        driver.quit()
        print("\nBrowser closed. Tor daemon remains running.")
        if tor_proc:
            print("To stop Tor manually, run: taskkill /IM tor.exe")

    print(f"\nDone. {solved} captcha solved and saved in {SAVE_DIR}")


if __name__ == "__main__":
    main()