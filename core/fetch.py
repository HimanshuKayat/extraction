from __future__ import annotations

import asyncio
import email
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_TIMEOUT = 30


def normalize_url(url: str) -> str:

    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    url = url.strip()

    markdown_match = re.fullmatch(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        url,
        flags=re.IGNORECASE,
    )

    if markdown_match:
        url = markdown_match.group(2)

    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1]

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"Unsupported URL scheme: {parsed.scheme}"
        )

    if not parsed.netloc:
        raise ValueError(
            f"Invalid URL: {url}"
        )

    return url


def fetch_http(
    url: str,
    save_path: str | Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:

    url = normalize_url(url)

    destination = Path(save_path)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    start = time.monotonic()

    try:

        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; ExtractionAgent/1.0)"
                )
            },
        )

        response.raise_for_status()

        destination.write_bytes(
            response.content
        )

        return {
            "success": True,
            "method": "http",
            "url": url,
            "final_url": response.url,
            "status_code": response.status_code,
            "content_type": response.headers.get(
                "Content-Type"
            ),
            "bytes": len(response.content),
            "path": str(destination),
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "method": "http",
            "url": url,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "recoverable": True,
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }


async def fetch_browser_async(
    url: str,
    save_path: str | Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:

    from playwright.async_api import async_playwright

    url = normalize_url(url)

    destination = Path(save_path)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    start = time.monotonic()

    try:

        async with async_playwright() as playwright:

            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            try:

                page = await browser.new_page()

                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout * 1000,
                )

                if response is None:

                    return {
                        "success": False,
                        "method": "browser",
                        "url": url,
                        "error_type": "NoResponse",
                        "message": (
                            "Browser returned no response."
                        ),
                        "recoverable": True,
                    }

                body = await response.body()

                destination.write_bytes(body)

                return {
                    "success": True,
                    "method": "browser",
                    "url": url,
                    "final_url": page.url,
                    "status_code": response.status,
                    "content_type": response.headers.get(
                        "content-type"
                    ),
                    "bytes": len(body),
                    "path": str(destination),
                    "duration_seconds": round(
                        time.monotonic() - start,
                        4,
                    ),
                }

            finally:

                await browser.close()

    except Exception as exc:

        return {
            "success": False,
            "method": "browser",
            "url": url,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "recoverable": True,
            "duration_seconds": round(
                time.monotonic() - start,
                4,
            ),
        }


def fetch_browser(
    url: str,
    save_path: str | Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:

    return asyncio.run(
        fetch_browser_async(
            url,
            save_path,
            timeout,
        )
    )


def fetch_resource(
    *,
    url: str,
    save_path: str | Path,
    preferred_method: str = "http",
    fallback_method: str | None = "browser",
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:

    methods = [preferred_method]

    if fallback_method:
        methods.append(fallback_method)

    errors = []

    for method in methods:

        if method == "http":

            result = fetch_http(
                url,
                save_path,
                timeout,
            )

        elif method == "browser":

            result = fetch_browser(
                url,
                save_path,
                timeout,
            )

        else:

            result = {
                "success": False,
                "method": method,
                "error_type": "UnsupportedFetchMethod",
                "message": (
                    f"Unsupported fetch method: {method}"
                ),
                "recoverable": False,
            }

        if result.get("success"):
            return result

        errors.append(result)

    return {
        "success": False,
        "error_type": "AllFetchMethodsFailed",
        "attempts": errors,
        "recoverable": True,
    }