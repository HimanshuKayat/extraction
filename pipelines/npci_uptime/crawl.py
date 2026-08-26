from __future__ import annotations

from pathlib import Path

import httpx

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)


SOURCE_URL = (
    "https://www.npci.org.in/product/upi/product-statistics"
)


CLICK_UPTIME = r"""
(() => {
    const elements = Array.from(
        document.querySelectorAll(
            'button, a, [role="tab"], [role="button"]'
        )
    );

    const target = elements.find(element => {
        const text = (
            element.innerText ||
            element.textContent ||
            ""
        ).trim().toLowerCase();

        return text === "uptime";
    });

    if (!target) {
        return false;
    }

    target.click();

    return true;
})();
"""


async def crawl4ai_fetch() -> str:

    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
    )

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=120_000,
        delay_before_return_html=4.0,
        js_code=CLICK_UPTIME,
        remove_overlay_elements=True,
    )

    async with AsyncWebCrawler(
        config=browser_config
    ) as crawler:

        result = await crawler.arun(
            url=SOURCE_URL,
            config=crawler_config,
        )

    if not result.success:
        raise RuntimeError(
            result.error_message
            or "Crawl4AI failed."
        )

    if not result.html:
        raise RuntimeError(
            "Crawl4AI returned empty HTML."
        )

    return result.html


def http_fetch() -> str:

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
    }

    response = httpx.get(
        SOURCE_URL,
        headers=headers,
        timeout=120,
        follow_redirects=True,
    )

    response.raise_for_status()

    html = response.text

    if not html:
        raise RuntimeError(
            "HTTP fallback returned empty content."
        )

    return html


async def crawl(
    output_path: str | Path,
) -> dict:

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "      attempting Crawl4AI..."
    )

    try:

        html = await crawl4ai_fetch()

        method = "crawl4ai"

        print(
            "      Crawl4AI succeeded."
        )

    except Exception as exc:

        print(
            "      Crawl4AI could not obtain "
            "usable page content."
        )

        print(
            f"      reason: {exc}"
        )

        print(
            "      trying official HTTP "
            "fallback..."
        )

        html = http_fetch()

        method = "http"

        print(
            "      HTTP fallback succeeded."
        )

    output_path.write_text(
        html,
        encoding="utf-8",
    )

    return {
        "success": True,
        "method": method,
        "path": str(output_path),
        "bytes": len(
            html.encode("utf-8")
        ),
    }
