from __future__ import annotations

from pathlib import Path

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)


# Replace this with the exact URL from Agent_sources.xlsx
SOURCE_URL = "REPLACE_WITH_CATALOG_SOURCE_URL"


async def crawl(
    output_path: str | Path,
) -> dict:

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if SOURCE_URL.startswith(
        "REPLACE_WITH"
    ):
        raise RuntimeError(
            "SOURCE_URL has not been configured. "
            "Use the exact IPO Creation source "
            "from Agent_sources.xlsx."
        )

    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
    )

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=120_000,
        delay_before_return_html=4.0,
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
        "method": "crawl4ai",
        "path": str(output_path),
        "bytes": len(
            result.html.encode("utf-8")
        ),
    }
