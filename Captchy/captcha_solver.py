# pip install selenium pytesseract pillow opencv-python numpy torch

import os
import re
import time
import socket
import atexit
import subprocess
import numpy as np
import cv2
import pytesseract
from pathlib import Path
from PIL import Image
import torch
import torch.nn as nn
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException

# ============================================================
# CONFIG
# ============================================================
TOR_BROWSER_BINARY = r"C:\Users\USER\Desktop\Tor Browser\Browser\firefox.exe"
TOR_PROFILE_PATH   = r"C:\Users\USER\Desktop\Tor Browser\Browser\TorBrowser\Data\Browser\profile.default"
TOR_DAEMON_PATH    = r"C:\Users\USER\Desktop\Tor Browser\Browser\TorBrowser\Tor\tor.exe"
GECKODRIVER_PATH   = r"C:\GekkoDriver\geckodriver.exe"

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

TOR_SOCKS_PORT     = 9050
TOR_BOOTSTRAP_WAIT = 20
TARGET_URL = "http://blackxppq2jvqyg4slyg3sbszv7ib2avaaycvhff5qipgdoepqi57xyd.onion/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEBUG_DIR  = str(PROJECT_ROOT / "debug" / "captchy")

USE_CNN    = True
MODEL_PATH = str(Path(__file__).resolve().with_name("captcha_model.pt"))

SVG_SELECTOR      = ".captcha__svg svg"
INPUT_SELECTORS   = ["#captcha-input", "input[name*='captcha']"]
SUBMIT_SELECTORS  = ["button[type='submit']", "//button[text()='Verify']"]
MAX_ATTEMPTS      = 5
GLYPH_SIZE        = 48
# ============================================================

ALPHABET  = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
WHITELIST = ALPHABET


# ---------------- SVG parsing (same as train_captcha.py) ----------------

PATH_RE = re.compile(r'<path\b([^>]*)>', re.S)
D_RE    = re.compile(r'\bd="([^"]+)"')
FILL_RE = re.compile(r'\bfill="([^"]+)"')


def parse_letter_paths(svg_html):
    """Extract letter path 'd' strings (filled, not stroked)."""
    out = []
    for m in PATH_RE.finditer(svg_html):
        attrs = m.group(1)
        d_m = D_RE.search(attrs)
        if not d_m:
            continue
        f_m = FILL_RE.search(attrs)
        fill = f_m.group(1).strip().lower() if f_m else ""
        has_stroke = "stroke=" in attrs.lower()
        if fill in ("", "none") or has_stroke:
            continue
        out.append(d_m.group(1))
    return out


def path_to_points(d_str):
    nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', d_str)]
    if len(nums) < 4:
        return None
    pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    return np.array(pts, dtype=np.float32)


def letterbox(arr, TW, TH):
    h, w = arr.shape[:2]
    s = min(TW / w, TH / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    r = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((TH, TW), dtype=np.uint8)
    dx, dy = (TW - nw) // 2, (TH - nh) // 2
    out[dy:dy + nh, dx:dx + nw] = r
    return out


def glyph_from_svg_paths(d_strings, size=GLYPH_SIZE):
    """Render each letter path to a GLYPH_SIZE crop, sorted left-to-right."""
    paths_with_bbox = []
    for d in d_strings:
        pts = path_to_points(d)
        if pts is None or len(pts) < 3:
            continue
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)
        paths_with_bbox.append((float(x_min), float(y_min), float(x_max), float(y_max), d))

    if not paths_with_bbox:
        return []

    paths_with_bbox.sort(key=lambda t: t[0])

    all_x = [t[0] for t in paths_with_bbox] + [t[2] for t in paths_with_bbox]
    all_y = [t[1] for t in paths_with_bbox] + [t[3] for t in paths_with_bbox]
    canvas_w = int(max(all_x)) + 4
    canvas_h = int(max(all_y)) + 4

    glyphs = []
    for x_min, y_min, x_max, y_max, d in paths_with_bbox:
        glyph_canvas = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
        points = path_to_points(d)
        shifted = points - np.array([x_min, y_min])
        pts_int = shifted.astype(np.int32)
        cv2.polylines(glyph_canvas, [pts_int], False, 255, 2, cv2.LINE_AA)
        glyphs.append(letterbox(glyph_canvas, size, size))
    return glyphs


# ---------------- CNN engine ----------------

class GlyphNet(nn.Module):
    def __init__(self, n_cls):
        super().__init__()
        def blk(ci, co):
            return nn.Sequential(
                nn.Conv2d(ci, co, 3, padding=1),
                nn.BatchNorm2d(co), nn.ReLU(),
                nn.Conv2d(co, co, 3, padding=1),
                nn.BatchNorm2d(co), nn.ReLU(),
                nn.MaxPool2d(2), nn.Dropout(0.25))
        self.feat = nn.Sequential(blk(1, 32), blk(32, 64), blk(64, 128))
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 6 * 6, 256),
            nn.ReLU(), nn.Dropout(0.5),
            nn.Linear(256, n_cls))

    def forward(self, x):
        return self.head(self.feat(x))


class CaptchaCNN:
    def __init__(self, path):
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        self.alphabet = ckpt["alphabet"]
        self.model = GlyphNet(len(self.alphabet))
        self.model.load_state_dict(ckpt["state"])
        self.model.eval()
        print(f"CNN loaded  alphabet={self.alphabet}  val_acc={ckpt.get('val_acc', '?')}")

    @torch.no_grad()
    def read_glyphs(self, glyphs):
        """Classify pre-rendered glyph crops (train/inference parity)."""
        if not glyphs:
            return ""
        X = torch.from_numpy(
            np.stack(glyphs).astype(np.float32) / 255.0
        ).unsqueeze(1)
        preds = self.model(X).argmax(1).tolist()
        return "".join(self.alphabet[i] for i in preds)


# ---------------- Tesseract fallback ----------------

def solve_tesseract(clean):
    img = Image.fromarray(clean)
    best, best_conf = "", -1.0
    for psm in (7, 8):
        cfg = f"--psm {psm} -c tessedit_char_whitelist={WHITELIST}"
        data = pytesseract.image_to_data(
            img, config=cfg, output_type=pytesseract.Output.DICT)
        text, confs = [], []
        for word, c in zip(data["text"], data["conf"]):
            word = re.sub(rf"[^{WHITELIST}]", "", word or "")
            if not word:
                continue
            try:
                confs.append(float(c))
            except (TypeError, ValueError):
                confs.append(0.0)
            text.append(word)
        avg = sum(confs) / len(confs) if confs else 0.0
        if avg > best_conf:
            best, best_conf = "".join(text), avg
    return best


# ---------------- Solve via SVG ----------------

def grab_svg(driver):
    el = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, SVG_SELECTOR)))
    return el.get_attribute("outerHTML"), el


def solve_captcha(driver, engine):
    """Read the captcha from its SVG source — identical pipeline to training."""
    os.makedirs(DEBUG_DIR, exist_ok=True)
    svg_html, el = grab_svg(driver)
    with open(os.path.join(DEBUG_DIR, "captcha.svg"), "w", encoding="utf-8") as f:
        f.write(svg_html)

    d_strings = parse_letter_paths(svg_html)
    glyphs = glyph_from_svg_paths(d_strings)
    print(f"  Letter paths found: {len(d_strings)}  Glyph segments: {len(glyphs)}")

    if engine is not None and glyphs:
        answer = engine.read_glyphs(glyphs)
        if answer and len(answer) >= 3:
            return answer
        print("  CNN returned too few chars -> Tesseract fallback")

    # Fallback: screenshot the SVG element and OCR it
    try:
        png = el.screenshot_as_png
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        clean = cv2.copyMakeBorder(binary, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        Image.fromarray(clean).save(os.path.join(DEBUG_DIR, "captcha_cleaned.png"))
        return solve_tesseract(clean)
    except Exception as e:
        print(f"  Tesseract fallback failed: {e}")
        return ""


# ---------------- Tor daemon ----------------

def start_tor_daemon():
    def port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0

    if port_open(TOR_SOCKS_PORT):
        print(f"Tor already running on port {TOR_SOCKS_PORT}.")
        return None

    print(f"Starting Tor daemon: {TOR_DAEMON_PATH}")
    proc = subprocess.Popen(
        [TOR_DAEMON_PATH, "--SocksPort", str(TOR_SOCKS_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # NOTE: no atexit.terminate() here — we keep Tor alive after success.
    return proc


# ---------------- Selenium browser ----------------

def setup_tor_browser():
    tor_proc = start_tor_daemon()

    options = Options()
    options.binary_location = TOR_BROWSER_BINARY
    options.add_argument("-profile")
    options.add_argument(TOR_PROFILE_PATH)

    options.set_preference("network.proxy.type", 1)
    options.set_preference("network.proxy.socks", "127.0.0.1")
    options.set_preference("network.proxy.socks_port", TOR_SOCKS_PORT)
    options.set_preference("network.proxy.socks_remote_dns", True)
    options.set_preference("network.proxy.socks_version", 5)

    service = Service(GECKODRIVER_PATH)
    driver = webdriver.Firefox(service=service, options=options)
    return driver, tor_proc


# ---------------- Helpers ----------------

def find_first(driver, selectors, timeout=10):
    for sel in selectors:
        try:
            by_method = By.XPATH if sel.startswith("//") else By.CSS_SELECTOR
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_method, sel)))
            return sel, el
        except TimeoutException:
            continue
    raise TimeoutException(f"None matched: {selectors}")


def attempt_once(driver, engine):
    answer = solve_captcha(driver, engine)
    print(f"  Solved: {answer!r}")
    if not answer:
        print("  ERROR: empty answer — skipping submit")
        return False

    _, field = find_first(driver, INPUT_SELECTORS, timeout=5)
    field.clear()
    field.send_keys(answer)

    _, btn = find_first(driver, SUBMIT_SELECTORS, timeout=5)
    btn.click()
    time.sleep(3)
    return True


def solve_with_driver(driver, model_path=None, max_attempts=MAX_ATTEMPTS):
    """Solve the site's SVG text challenge in an already-authorized browser session.

    The scraper calls this with its existing driver so the verification token,
    cookies, and listing requests remain in the same browser session.
    """
    model_path = str(model_path or MODEL_PATH)
    engine = CaptchaCNN(model_path) if os.path.exists(model_path) else None
    if engine is None:
        return False, f"captcha model file not found: {model_path}"

    for attempt in range(1, max_attempts + 1):
        try:
            attempt_once(driver, engine)
        except TimeoutException as exc:
            if attempt == max_attempts:
                return False, f"captcha interaction timed out: {exc}"

        try:
            WebDriverWait(driver, 12).until(
                lambda browser: not browser.find_elements(By.CSS_SELECTOR, ".captcha")
                and bool(browser.find_elements(By.CSS_SELECTOR, ".leaked-page__heading, .target-card"))
            )
            return True, None
        except TimeoutException:
            if attempt == max_attempts:
                break

        # A rejected answer refreshes automatically in the site's UI. If it
        # did not, request a fresh challenge before the next inference.
        try:
            refresh = driver.find_elements(By.XPATH, "//button[normalize-space()='New image']")
            if refresh:
                refresh[0].click()
                WebDriverWait(driver, 10).until(
                    lambda browser: bool(browser.find_elements(By.CSS_SELECTOR, ".captcha__svg svg"))
                )
        except (TimeoutException, WebDriverException):
            pass

    return False, f"verification did not complete after {max_attempts} attempts"


# ---------------- Main ----------------

def main():
    engine = None
    if USE_CNN:
        if os.path.exists(MODEL_PATH):
            engine = CaptchaCNN(MODEL_PATH)
        else:
            print(f"⚠️ Model not found at {MODEL_PATH} — running Tesseract-only")

    driver = tor_proc = None
    solved = False
    try:
        driver, tor_proc = setup_tor_browser()
        print(f"Navigating to {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(6)

        for i in range(1, MAX_ATTEMPTS + 1):
            print(f"\n{'='*50}")
            print(f"  Attempt {i}/{MAX_ATTEMPTS}")
            print(f"{'='*50}")
            try:
                if attempt_once(driver, engine):
                    solved = True
                    print("  ✅ Solved — stopping. Tor window stays open.")
                    break
            except TimeoutException as e:
                print(f"  FAILED: {e}")

            new_btn = driver.find_elements(By.XPATH, "//*[contains(text(),'New image')]")
            if new_btn:
                new_btn[0].click()
                time.sleep(2)

        if not solved:
            print("\n" + "=" * 50)
            print("  All attempts done. Inspect the browser.")
            input("  Press ENTER to close...")
            print("=" * 50)

    finally:
        if solved:
            # Leave the browser AND Tor daemon running so you can use the session.
            print("Browser + Tor left open. Close them manually when done.")
            # Detach geckodriver/Tor from cleanup so they survive script exit.
            driver = None
            tor_proc = None
        else:
            if driver:
                driver.quit()
            if tor_proc:
                print("Stopping Tor daemon...")
                tor_proc.terminate()


if __name__ == "__main__":
    main()
