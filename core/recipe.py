from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import async_playwright


async def run_recipe_async(
    recipe: dict[str, Any],
) -> dict[str, Any]:

    steps = recipe.get("steps", [])

    if not isinstance(steps, list):
        raise ValueError(
            "recipe.steps must be a list"
        )

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

            observations = []

            for step in steps:

                action = step["action"]

                if action == "goto":

                    await page.goto(
                        step["url"],
                        wait_until=step.get(
                            "wait_until",
                            "domcontentloaded",
                        ),
                        timeout=step.get(
                            "timeout",
                            30000,
                        ),
                    )

                elif action == "click":

                    await page.get_by_text(
                        step["text"],
                        exact=step.get(
                            "exact",
                            False,
                        ),
                    ).click()

                elif action == "click_label":

                    await page.get_by_label(
                        step["label"],
                        exact=step.get(
                            "exact",
                            True,
                        ),
                    ).click()

                elif action == "fill":

                    await page.get_by_label(
                        step["label"],
                        exact=step.get(
                            "exact",
                            True,
                        ),
                    ).fill(
                        step["value"]
                    )

                elif action == "wait":

                    await page.wait_for_timeout(
                        step.get(
                            "milliseconds",
                            1000,
                        )
                    )

                elif action == "wait_for_text":

                    await page.get_by_text(
                        step["text"],
                        exact=step.get(
                            "exact",
                            False,
                        ),
                    ).wait_for()

                elif action == "extract_text":

                    text = await page.locator(
                        step.get(
                            "selector",
                            "body",
                        )
                    ).inner_text()

                    observations.append({
                        "type": "text",
                        "value": text,
                    })

                elif action == "extract_links":

                    links = await page.locator(
                        "a"
                    ).evaluate_all(
                        """
                        elements => elements.map(
                            e => ({
                                text: e.innerText,
                                href: e.href
                            })
                        )
                        """
                    )

                    observations.append({
                        "type": "links",
                        "value": links,
                    })

                else:

                    raise ValueError(
                        f"Unsupported recipe action: {action}"
                    )

            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "observations": observations,
            }

        finally:

            await browser.close()


def run_recipe(
    recipe: dict[str, Any],
) -> dict[str, Any]:

    return asyncio.run(
        run_recipe_async(recipe)
    )