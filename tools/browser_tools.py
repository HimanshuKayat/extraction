from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


_playwright: Playwright | None = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None


async def _ensure_browser() -> Page:
    global _playwright
    global _browser
    global _context
    global _page

    if _page is not None:
        try:
            if not _page.is_closed():
                return _page
        except Exception:
            pass

    _playwright = await async_playwright().start()

    _browser = await _playwright.chromium.launch(
        headless=True,
    )

    _context = await _browser.new_context(
        viewport={
            "width": 1440,
            "height": 900,
        },
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
    )

    _page = await _context.new_page()

    return _page


async def browser_open(
    url: str,
    timeout: int = 30,
) -> dict[str, Any]:

    start = time.monotonic()

    try:

        page = await _ensure_browser()

        timeout_ms = timeout * 1000

        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )

        # Give JavaScript a short opportunity to render.
        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=min(
                    timeout_ms,
                    10_000,
                ),
            )
        except Exception:
            pass

        final_url = page.url

        title = ""

        try:
            title = await page.title()
        except Exception:
            pass

        status_code = (
            response.status
            if response is not None
            else None
        )

        return {
            "success": True,
            "url": final_url,
            "title": title,
            "status_code": status_code,
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "recoverable": True,
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }


async def browser_inspect() -> dict[str, Any]:

    start = time.monotonic()

    try:

        page = await _ensure_browser()

        title = ""

        try:
            title = await page.title()
        except Exception:
            pass

        text = ""

        try:
            text = await page.locator(
                "body"
            ).inner_text(
                timeout=5_000
            )
        except Exception:
            pass

        links: list[dict[str, str]] = []

        try:

            elements = await page.locator(
                "a"
            ).all()

            for element in elements:

                try:

                    href = (
                        await element.get_attribute(
                            "href"
                        )
                    )

                    link_text = (
                        await element.inner_text()
                    )

                    if href:

                        links.append(
                            {
                                "text": (
                                    link_text.strip()
                                ),
                                "href": href,
                            }
                        )

                except Exception:
                    continue

        except Exception:
            pass

        return {
            "success": True,
            "url": page.url,
            "title": title,
            "text": text[:50_000],
            "links": links[:500],
            "link_count": len(links),
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "recoverable": True,
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }


async def browser_close() -> dict[str, Any]:

    global _playwright
    global _browser
    global _context
    global _page

    start = time.monotonic()

    try:

        if _page is not None:

            try:
                await _page.close()
            except Exception:
                pass

        if _context is not None:

            try:
                await _context.close()
            except Exception:
                pass

        if _browser is not None:

            try:
                await _browser.close()
            except Exception:
                pass

        if _playwright is not None:

            try:
                await _playwright.stop()
            except Exception:
                pass

        _page = None
        _context = None
        _browser = None
        _playwright = None

        return {
            "success": True,
            "message": (
                "Browser session closed."
            ),
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }

    except Exception as exc:

        _page = None
        _context = None
        _browser = None
        _playwright = None

        return {
            "success": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "recoverable": True,
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }