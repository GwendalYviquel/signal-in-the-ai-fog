"""Screenshot of the catalog site for the README (assets/catalog.png).

Serves docs/ locally, with its real catalog.json, and captures it in headless Chromium.
Usage: pip install -r requirements-dev.txt && python -m playwright install chromium
       python tools/screenshot_site.py [output.png]
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "catalog.png"
VIEWPORT = {"width": 1280, "height": 860}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def screenshot(out: Path = OUT, color_scheme: str = "light") -> Path:
    handler = functools.partial(_Quiet, directory=str(ROOT / "docs"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT, color_scheme=color_scheme)
            page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/episodes.html")  # the first show's catalog
            page.wait_for_selector("#list > *")
            page.wait_for_load_state("networkidle")
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out))
            browser.close()
    finally:
        httpd.shutdown()
    print(f"Screenshot saved: {out}")
    return out


if __name__ == "__main__":
    screenshot(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
