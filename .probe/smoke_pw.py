import io, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
BASE = r"C:/Users/Administrator/WorkBuddy/抖音"
prof = os.path.join(BASE, ".edge-auto", "smoke")
os.makedirs(prof, exist_ok=True)
with sync_playwright() as p:
    print("chromium exe:", p.chromium.executable_path)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=prof, channel="msedge", headless=False,
        no_viewport=True, args=["--start-maximized", "--no-first-run",
                                "--no-default-browser-check"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://example.com", wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)
    print("title:", page.title())
    print("url:", page.url)
    print("ua:", page.evaluate("navigator.userAgent"))
    print("screens:", page.evaluate("[screen.width, screen.height, devicePixelRatio]"))
    ctx.close()
print("SMOKE OK")
