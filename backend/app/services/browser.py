"""Sandbox Chromium controlled through Playwright (its own process + context, never your own browser).

Each step the model gets a screenshot, the URL and tab title, and the interactive elements on screen
(kind, label and centre; no page text). It points on a 0-1000 grid (the coordinate space Qwen-VL
models are trained to point in) and we scale back to pixels.
"""

import asyncio
import base64
import json

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.core.config import settings

# Visible, clickable elements in the viewport, with their centre on a 0-1000 grid.
ELEMENTS_JS = r"""
() => {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, label[for],' +
    '[role=button], [role=link], [role=tab], [role=option], [role=menuitem], [role=checkbox],' +
    '[role=radio], [role=combobox], [role=switch], [role=gridcell], [onclick], [contenteditable=true]';
  const vw = innerWidth, vh = innerHeight;
  const picked = new Set();
  const out = [];
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.right < 0 || r.top > vh || r.left > vw) continue;
    // also checks ancestors: e.g. links in a closed menu overlay whose container has opacity 0
    if (!el.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;
    const x = Math.min(Math.max(r.left + r.width / 2, 1), vw - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 1), vh - 1);
    const hit = document.elementFromPoint(x, y);
    if (hit && !(el === hit || el.contains(hit) || hit.contains(el))) continue;  // covered by something else
    const parent = el.parentElement && el.parentElement.closest(sel);
    if (parent && picked.has(parent)) {  // same click target as an already-listed parent
      const pr = parent.getBoundingClientRect();
      if (r.width * r.height > 0.7 * pr.width * pr.height) continue;
    }
    picked.add(el);
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder ||
                   el.title || el.getAttribute('alt') || el.name || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    out.push({
      tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '', role: el.getAttribute('role') || '',
      label, x: Math.round(x / vw * 1000), y: Math.round(y / vh * 1000),
    });
  }
  return out;
}
"""

_pw = None
_browser: Browser | None = None
_lock = asyncio.Lock()


async def get_browser() -> Browser:
    global _pw, _browser
    async with _lock:
        if _browser is None or not _browser.is_connected():
            _pw = _pw or await async_playwright().start()
            _browser = await _pw.chromium.launch(
                headless=settings.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
    return _browser


async def shutdown():
    if _browser:
        await _browser.close()
    if _pw:
        await _pw.stop()


class BrowserSession:
    def __init__(self, context: BrowserContext, page: Page):
        self.context = context
        self.page = page
        self.viewers: set[asyncio.Queue] = set()  # live-view websocket subscribers
        self.last_frame: str | None = None
        self._mouse = (settings.viewport_width / 2, settings.viewport_height / 2)  # last mouse position
        self._cdp = None
        context.on("page", self._on_new_page)

    @classmethod
    async def create(cls) -> "BrowserSession":
        browser = await get_browser()
        context = await browser.new_context(
            viewport={"width": settings.viewport_width, "height": settings.viewport_height},
            locale="en-US",
            timezone_id="Europe/Stockholm",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        session = cls(context, page)
        await session._start_screencast()
        return session

    def _on_new_page(self, page: Page):
        # links that open a new tab: follow them and stream that tab instead
        self.page = page
        asyncio.create_task(self._start_screencast())

    async def close(self):
        await self.context.close()

    # ---- live view (CDP screencast -> websocket) --------------------------

    async def _start_screencast(self):
        if self._cdp:
            try:
                await self._cdp.send("Page.stopScreencast")
                await self._cdp.detach()
            except Exception:
                pass
        cdp = await self.context.new_cdp_session(self.page)
        self._cdp = cdp

        def on_frame(params):
            self._broadcast(params["data"])
            asyncio.create_task(cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": 70, "maxWidth": settings.viewport_width,
             "maxHeight": settings.viewport_height, "everyNthFrame": 1},
        )

    def _broadcast(self, jpeg_b64: str):
        """Send a frame to every live viewer. Latest frame wins: a slow viewer drops its stale
        frame, never the newest one, so the live view always ends on the current page."""
        frame = json.dumps({"img": jpeg_b64, "url": self.page.url})
        self.last_frame = frame
        for q in list(self.viewers):
            if q.full():
                q.get_nowait()
            q.put_nowait(frame)

    async def push_frame(self):
        """Force a fresh frame: the screencast only fires on repaints, which can be missed."""
        try:
            jpeg = await self.page.screenshot(type="jpeg", quality=70)
            self._broadcast(base64.b64encode(jpeg).decode())
        except Exception:
            pass

    # ---- observe -------------------------------------------------------

    async def observe(self, screenshot_path) -> dict:
        page = self.page
        # Wait for the page and its follow-up requests (e.g. the cookie banner's consent script), each
        # capped: some sites never go network-idle (analytics, websockets). Already loaded = no wait.
        for state, timeout in (("load", 8000), ("networkidle", 3000)):
            try:
                await page.wait_for_load_state(state, timeout=timeout)
            except Exception:
                pass
        await asyncio.sleep(0.8)  # let late JS render and banners/menus animate in

        try:
            elements = await page.evaluate(ELEMENTS_JS)
        except Exception:
            elements = []
        try:  # which part of the page is on screen: top/bottom as 0-1 of the page height
            scroll = await page.evaluate(
                "() => { const h = Math.max(document.documentElement.scrollHeight, innerHeight);"
                " return {top: scrollY / h, bottom: Math.min((scrollY + innerHeight) / h, 1), screens: h / innerHeight}; }"
            )
        except Exception:
            scroll = None
        png = await page.screenshot(type="png")
        screenshot_path.write_bytes(png)
        await self.push_frame()  # live view shows exactly what the model is about to decide on
        return {"url": page.url, "title": await page.title(), "elements": elements, "scroll": scroll, "png": png}

    # ---- act -------------------------------------------------------------

    def _px(self, coordinate: list[int] | None) -> tuple[float, float]:
        """Model's relative [x, y] on the 0-1000 grid -> pixels in the live viewport."""
        if not coordinate:
            raise ValueError("coordinate [x, y] (0-1000) is required")
        x, y = coordinate
        return x / 1000 * settings.viewport_width, y / 1000 * settings.viewport_height

    async def navigate(self, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def _glide(self, x: float, y: float, steps: int = 15):
        """Move the real mouse to (x, y) in small eased steps (~0.4s), so hover effects show up in the
        live view, in sync with the cursor the UI animates."""
        x0, y0 = self._mouse
        for i in range(1, steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)  # ease in-out
            await self.page.mouse.move(x0 + (x - x0) * t, y0 + (y - y0) * t)
            await asyncio.sleep(0.025)
        self._mouse = (x, y)

    async def click(self, coordinate: list[int] | None):
        x, y = self._px(coordinate)
        await self._glide(x, y)
        await self.page.mouse.click(x, y)
        await self.page.wait_for_timeout(300)

    async def type(self, coordinate: list[int] | None, text: str):
        if coordinate:  # without one, type into whatever is focused (e.g. the field clicked last step)
            x, y = self._px(coordinate)
            await self._glide(x, y)
            await self.page.mouse.click(x, y)
        await self.page.keyboard.press("ControlOrMeta+A")
        await self.page.keyboard.press("Backspace")
        await self.page.keyboard.type(text, delay=40)

    async def press(self, key: str):
        await self.page.keyboard.press(key)

    async def scroll(self, how: str):
        """`how`: "down" / "up" with an optional number of screens ("down 3", "up 0.5"; default 0.8),
        or "top" / "bottom". Whether it moved, the model sees in the next screenshot."""
        words = how.lower().split() or ["down"]
        if words[0] in ("top", "bottom"):
            direction, screens = ("up" if words[0] == "top" else "down"), 100.0  # past either end of any page
        else:
            direction = "up" if words[0] == "up" else "down"
            try:
                screens = min(max(float(words[1]), 0.1), 100.0) if len(words) > 1 else 0.8
            except ValueError:
                screens = 0.8
        # many small wheel steps instead of one jump, so the live view shows the page gliding
        total = settings.viewport_height * screens * (-1 if direction == "up" else 1)
        for _ in range(16):
            await self.page.mouse.wheel(0, total / 16)
            await asyncio.sleep(0.02)
        await self.page.wait_for_timeout(250)

    async def back(self):
        await self.page.go_back(wait_until="domcontentloaded", timeout=15000)
