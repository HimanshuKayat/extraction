from __future__ import annotations

from pathlib import Path

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)


SOURCE_URL = (
    "https://www.npci.org.in/product/upi/product-statistics"
)


# First try to activate the Daily Statistics section.
#
# This intentionally searches by visible text rather than a fragile
# CSS selector.
CLICK_DAILY_STATISTICS = r"""
(() => {
    const elements = Array.from(
        document.querySelectorAll(
            'button, a, [role="tab"], [role="button"]'
        )
    );

    const target = elements.find(
        element =>
            (element.innerText || element.textContent || "")
                .trim()
                .toLowerCase() === "daily statistics"
    );

    if (!target) {
        return false;
    }

    target.click();

    return true;
})()
"""


def daily_table_present(page) -> bool:
    text = page.inner_text("body")

    required = [
        "Day",
        "Volume (In Mn.)",
        "Value (In Cr.)",
    ]

    return all(
        value in text
        for value in required
    )


async def crawl(
    output_path: str | Path,
) -> dict:

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
    )

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=120_000,
        delay_before_return_html=3.0,
        js_code=CLICK_DAILY_STATISTICS,
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
            "Crawl4AI failed: "
            f"{result.error_message}"
        )

    html = result.html

    if not html:

        raise RuntimeError(
            "Crawl4AI returned empty HTML."
        )

    output_path.write_text(
        html,
        encoding="utf-8",
    )

    return {
        "success": True,
        "path": str(output_path),
        "bytes": len(html.encode("utf-8")),
    }
