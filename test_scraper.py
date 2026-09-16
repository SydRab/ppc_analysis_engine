import asyncio
import json
import pandas as pd
from playwright.async_api import async_playwright

TEST_URL = "https://datastudio.google.com/embed/u/0/reporting/622ebab9-9ee2-45b6-9831-bbf53e3395f9/page/uruCE?params=%7B%22df12%22:%22include%25EE%2580%25800%25EE%2580%2580IN%25EE%2580%2580Pest%2520Control%22%7D"

async def test_api_interception(page):
    """TEST 1: Intercept underlying POST requests for raw data payloads"""
    print("\n--- TEST 1: API Request Interception ---")
    captured_payloads = []

    async def handle_response(response):
        # Listen for internal reporting endpoints
        if "getComponentData" in response.url or "batchedData" in response.url or "reporting" in response.url:
            try:
                text = await response.text()
                if len(text) > 100:
                    captured_payloads.append((response.url, text[:300]))
            except Exception:
                pass

    page.on("response", handle_response)
    await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(6)

    if captured_payloads:
        print(f"[✓] SUCCESS: Caught {len(captured_payloads)} network calls.")
        for url, snippet in captured_payloads[:3]:
            print(f"    -> Endpoint: {url[:60]}...\n       Snippet: {snippet[:120]}...\n")
        return True
    else:
        print("[X] FAILED: No relevant backend data traffic intercepted.")
        return False

async def test_pointer_events(page):
    """TEST 2: Dispatch Synthetic Pointer Events (JS)"""
    print("\n--- TEST 2: Native Pointer Event Dispatch ---")
    try:
        button_attached = await page.evaluate("""() => {
            const targets = document.querySelectorAll('canvas, svg, .component-container, ggr-geo-chart');
            for (let el of targets) {
                const rect = el.getBoundingClientRect();
                const opts = { bubbles: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
                el.dispatchEvent(new PointerEvent('pointerover', opts));
                el.dispatchEvent(new PointerEvent('pointermove', opts));
            }
            return document.querySelector("button[aria-label='More options'], [aria-label='More options']") !== null;
        }""")
        await asyncio.sleep(2)
        
        btn = page.locator("button[aria-label='More options'], [aria-label='More options']").first
        if button_attached or await btn.count() > 0:
            print("[✓] SUCCESS: Pointer events revealed 3-dots action button!")
            return True
        print("[X] FAILED: Pointer events did not trigger DOM update.")
        return False
    except Exception as e:
        print(f"[X] FAILED: {type(e).__name__} - {e}")
        return False

async def test_keyboard_tabbing(page):
    """TEST 3: Keyboard Tab Focus Navigation (Accessibility Tree)"""
    print("\n--- TEST 3: Keyboard Focus Navigation (Tab Iteration) ---")
    try:
        await page.focus("body")
        for tab_count in range(1, 12):
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.2)
            
            btn = page.locator("button[aria-label='More options'], [aria-label='More options']").first
            if await btn.count() > 0 and await btn.is_visible():
                print(f"[✓] SUCCESS: Action button revealed after {tab_count} Tab keypresses!")
                return True
        print("[X] FAILED: Tab focus cycling did not expose the menu button.")
        return False
    except Exception as e:
        print(f"[X] FAILED: {type(e).__name__} - {e}")
        return False

async def test_cdp_mouse(page, context):
    """TEST 4: Chrome DevTools Protocol (CDP) Hardware Mouse Injection"""
    print("\n--- TEST 4: CDP Hardware Mouse Injection ---")
    try:
        cdp = await context.new_cdp_session(page)
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 720, "y": 350})
        await asyncio.sleep(2)

        btn = page.locator("button[aria-label='More options'], [aria-label='More options']").first
        if await btn.count() > 0:
            print("[✓] SUCCESS: CDP Mouse Move attached the action button!")
            return True
        print("[X] FAILED: CDP Input injection did not trigger hover state.")
        return False
    except Exception as e:
        print(f"[X] FAILED: {type(e).__name__} - {e}")
        return False

async def test_visual_viewport_inspection(page):
    """TEST 5: Screenshot & Layout Audit"""
    print("\n--- TEST 5: Visual Viewport Audit ---")
    try:
        await page.screenshot(path="debug_viewport.png", full_page=True)
        print("[✓] SUCCESS: Saved screen state to 'debug_viewport.png'.")
        return True
    except Exception as e:
        print(f"[X] FAILED: Could not save screenshot: {e}")
        return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("=== RUNNING FAST DIAGNOSTIC SUITE ===")

        results = {}
        results["1. Network Interception"] = await test_api_interception(page)
        results["2. Synthetic Pointer Events"] = await test_pointer_events(page)
        results["3. Keyboard Tab Navigation"] = await test_keyboard_tabbing(page)
        results["4. CDP Hardware Mouse Inject"] = await test_cdp_mouse(page, context)
        results["5. Screenshot Audit"] = await test_visual_viewport_inspection(page)

        await browser.close()

        print("\n" + "="*45)
        print("         DIAGNOSTIC RESULTS SUMMARY         ")
        print("="*45)
        for name, status in results.items():
            out = "PASSED" if status else "FAILED"
            print(f"{name:<32}: {out}")
        print("="*45)

if __name__ == "__main__":
    asyncio.run(main())
