import warnings
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

TOR = "socks5h://127.0.0.1:9050"
P = {"http": TOR, "https": TOR}
sites = [
    ("Akira", "https://akiral2iz6a7qgd3ayp3l6yub7xx2uep76idk3u2kollpj5z3z636bad.onion/"),
    ("LeakedData", "https://business-data-leaks.com/"),
    ("ZaWoo", "https://fyenuhkq3pfhnbpidj5jm2fl2lryxip4byhg6eozynrnlomu4szf2nyd.onion/"),
]
for name, url in sites:
    try:
        r = requests.get(
            url,
            proxies=P,
            timeout=50,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        print(name, "status", r.status_code, "ctype", r.headers.get("content-type"), "bytes", len(r.content))
        (Path(__file__).resolve().parent / "html" / f"{name.lower()}.html").write_text(
            r.text[:250000], encoding="utf-8", errors="replace"
        )
    except Exception as e:
        print(name, "FAIL", e)
