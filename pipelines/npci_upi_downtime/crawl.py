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


CLICK_DOWNTIME = r"""
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
        )
        .trim()
        .toLowerCase();

        return (
            text.includes("downtime") ||
            text.includes("incidents")
        );
    });

    if (!target) {
        return false;
    }

    target.click();

    return true;
})();
"""


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
        delay_before_return_html=4.0,
        js_code=CLICK_DOWNTIME,
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

    if not result.html:
        raise RuntimeError(
            "Crawl4AI returned empty HTML."
        )

    output_path.write_text(
        result.html,
        encoding="utf-8",
    )

    return {
        "success": True,
        "path": str(output_path),
        "bytes": len(
            result.html.encode("utf-8")
        ),
    }
