import time
import socket
import json
import random
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

TARGET_URL = "http://yqhecvqtdvq6p7duqcgw2qca77spbgakxcoibtx6zpvfshltsbbbhfqd.onion/"
# ============================================================


def start_tor_daemon():
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
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    for _ in range(30):
        if port_open(TOR_SOCKS_PORT):
            print("Tor is ready.")
            return tor_proc
        time.sleep(1)

    raise RuntimeError("Tor did not open port.")


def human_like_drag(driver, source_el, target_el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'})", source_el)
    time.sleep(0.3)

    b = source_el.rect
    t = target_el.rect

    start_x = b["x"] + b["width"] // 2
    start_y = b["y"] + b["height"] // 2
    end_x = t["x"] + t["width"] // 2
    end_y = t["y"] + t["height"] // 2

    steps = random.randint(50, 65)
    ctrl_x = (start_x + end_x) // 2
    ctrl_y = (start_y + end_y) // 2 + 40

    vp_w = driver.execute_script("return window.innerWidth")
    vp_h = driver.execute_script("return window.innerHeight")
    ctrl_x = max(20, min(ctrl_x, vp_w - 20))
    ctrl_y = max(20, min(ctrl_y, vp_h - 20))

    path = []
    for i in range(steps + 1):
        progress = i / steps
        bx = (1 - progress) ** 2 * start_x + 2 * (1 - progress) * progress * ctrl_x + progress ** 2 * end_x
        by = (1 - progress) ** 2 * start_y + 2 * (1 - progress) * progress * ctrl_y + progress ** 2 * end_y
        if i > 0:
            bx += random.uniform(-1.0, 1.0)
            by += random.uniform(-1.0, 1.0)
        bx = max(0, min(bx, vp_w - 1))
        by = max(0, min(by, vp_h - 1))
        path.append({"x": float(bx), "y": float(by)})

    path_json = json.dumps(path)
    hold_time = random.uniform(80, 200)
    base_delay = random.uniform(8, 14)

    result = driver.execute_async_script("""
        const done = arguments[arguments.length - 1];
        const path = JSON.parse(arguments[0]);
        const holdTime = arguments[1];
        const baseDelay = arguments[2];

        function fire(type, x, y, buttons) {
            if (!isFinite(x) || !isFinite(y)) {
                console.error('Bad coords:', type, x, y);
                return;
            }
            const el = document.elementFromPoint(x, y) || document.body;
            const common = {
                bubbles: true, cancelable: true, view: window,
                clientX: x, clientY: y, screenX: x, screenY: y,
                button: 0, buttons: buttons, relatedTarget: null
            };
            el.dispatchEvent(new PointerEvent('pointer' + type.slice(5), Object.assign({
                pointerId: 1, pointerType: 'mouse', isPrimary: true
            }, common)));
            el.dispatchEvent(new MouseEvent(type, common));
        }

        const first = path[0];
        fire('mousedown', first.x, first.y, 1);
        fire('pointerdown', first.x, first.y, 1);

        let delay = holdTime;
        for (let i = 1; i < path.length; i++) {
            const p = path[i];
            const progress = i / path.length;
            let speed = baseDelay + 15 * Math.sin(Math.PI * progress);
            speed += Math.random() * 8;

            (function(idx) {
                setTimeout(function() {
                    fire('mousemove', path[idx].x, path[idx].y, 1);
                    fire('pointermove', path[idx].x, path[idx].y, 1);
                }, delay);
                delay += speed;
            })(i);
        }

        setTimeout(function() {
            const last = path[path.length - 1];
            fire('mouseup', last.x, last.y, 0);
            fire('pointerup', last.x, last.y, 0);
            done('drag complete | released at ' + last.x + ',' + last.y + ' | steps=' + path.length);
        }, delay + 100);
    """, path_json, hold_time, base_delay)

    print(f"  Drag trace: {result}")
    time.sleep(2.5)


def solve_storm_captcha(driver, timeout=30):
    print("Waiting for captcha elements...")
    try:
        bolt = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-bolt='true']"))
        )
        target = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-target='true']"))
        )
    except Exception as e:
        print(f"Captcha elements not found: {e}")
        return False

    print("Performing human-like curved drag via JS pointer events...")
    human_like_drag(driver, bolt, target)

    print("Waiting for verification...")
    time.sleep(4)

    # --- Check 1: visible status/success message ---
    try:
        msg = driver.find_element(
            By.CSS_SELECTOR, ".sc-status, .sc-message, [class*='success'], [class*='passed']"
        )
        if msg.text.strip():
            print(f"  Status message: {msg.text.strip()}")
    except Exception:
        pass

    # --- Check 2: did the captcha disappear? (most reliable) ---
    stage_gone = len(driver.find_elements(By.CSS_SELECTOR, "[data-bolt='true']")) == 0
    map_visible = len(driver.find_elements(
        By.CSS_SELECTOR, "canvas, .map, #map, [class*='map']"
    )) > 0

    if stage_gone or map_visible:
        print("Verification passed (captcha cleared / map loaded).")
        return True

    print("No sign of success after drag attempt.")
    return False


def main():
    print("Opening Storm and attempting the configured challenge flow; no cookies are read or saved.")
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
        print(f"Page title: '{page_title}'")

        for attempt in range(1, 4):
            print(f"\n--- Attempt {attempt}/3 ---")
            if solve_storm_captcha(driver):
                print("\n=== SUCCESS ===")
                break
            print("Retrying in 3 seconds...")
            time.sleep(3)
        else:
            print("\nFailed after 3 attempts. Check element selectors.")
            print("Dumping page source for inspection...")
            with open(r"d:\WolfCaptcha\cloak\storm_page_dump.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Saved to storm_page_dump.html")

        print("\nBrowser stays open. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nClosing browser...")

    finally:
        driver.quit()
        print("Browser closed. Tor daemon remains running.")
        if tor_proc:
            print("To stop Tor manually, run: taskkill /IM tor.exe")


if __name__ == "__main__":
    main()
