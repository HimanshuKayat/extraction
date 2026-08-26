from __future__ import annotations

from pathlib import Path

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)

from config import SOURCE_URL if False else None
