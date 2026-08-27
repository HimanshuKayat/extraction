#!/usr/bin/env python3
"""
Crawl module for Daily UPI Transactions pipeline.
Uses Playwright/Crawl4AI to capture NPCI API responses.
"""
import os
import json
import asyncio
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

# Try to import crawl4ai first
try:
    from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    print("Crawl4AI not available, falling back to Playwright")

# Fallback to playwright if crawl4ai is not available
try:
    from playwright.async_api import async_playwright, Page
except ImportError:
    print("Neither Crawl4AI nor Playwright available. Please install one of them.")
    raise


class NPICrawler:
    """Crawler for NPCI website with API response capture."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.source_url = self.config['source']['url']
        self.api_endpoint = self.config['source']['api_endpoint']
        self.api_params = self.config['source']['api_params'].copy()
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # Browser settings
        self.headless = self.config['browser']['headless']
        self.timeout = self.config['browser']['timeout']
        self.wait_timeout = self.config['browser'].get('wait_timeout', 10000)

        # Get year range
        self.year_range = self._determine_year_range()

        # Captured API responses
        self.captured_responses = []

    def _determine_year_range(self) -> str:
        """
        Determine the current NPCI year range.
        Defaults to current financial year if not specified.
        """
        # Check if year_range is specified in config
        if 'year_range' in self.api_params:
            return self.api_params['year_range']

        # Determine financial year (April-March)
        today = datetime.now()
        # NPCI follows April-March financial year
        if today.month >= 4:
            # Current financial year: e.g., 2026-27
            start_year = today.year
        else:
            # Previous financial year started last year
            start_year = today.year - 1

        return f"{start_year}-{str(start_year + 1)[-2:]}"

    def _prepare_api_url(self, params: Optional[Dict] = None) -> str:
        """Prepare API URL with parameters."""
        if params is None:
            params = self.api_params.copy()

        # Ensure year_range is set
        if 'year_range' not in params:
            params['year_range'] = self.year_range

        # Build query string
        query_parts = []
        for key, value in params.items():
            if value is not None:
                query_parts.append(f"{key}={value}")

        return f"{self.api_endpoint}?{'&'.join(query_parts)}"

    async def _capture_response(self, response, endpoint: str):
        """Capture API responses for the specified endpoint."""
        try:
            url = response.url
            if endpoint in url:
                # Check if it's the detail endpoint
                if 'tab/detail' in url:
                    try:
                        # Get response body
                        body = await response.body()
                        content_type = response.headers.get('content-type', '')

                        if 'application/json' in content_type:
                            try:
                                data = json.loads(body)
                                self.captured_responses.append({
                                    'url': url,
                                    'status': response.status,
                                    'headers': dict(response.headers),
                                    'data': data,
                                    'timestamp': datetime.now().isoformat()
                                })
                                print(f"Captured API response: {url}")
                            except json.JSONDecodeError:
                                # Non-JSON response, ignore
                                pass
                # Also capture tab configuration responses
                elif 'tabs' in url:
                    body = await response.body()
                    content_type = response.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        try:
                            data = json.loads(body)
                            # Check if this is the tab config
                            # Parse to find year range options
                            if 'data' in data and 'tabs' in data.get('data', {}):
                                tabs = data['data']['tabs']
                                if tabs:
                                    # Save tab config for metadata
                                    tab_config_file = self.raw_dir / 'tab_config.json'
                                    with open(tab_config_file, 'w') as f:
                                        json.dump(data, f, indent=2)
                                    print("Saved tab configuration")
                        except:
                            pass
        except Exception as e:
            # Silently ignore capture errors
            pass

    async def crawl_with_playwright(self) -> bool:
        """
        Crawl NPCI website using Playwright with API interception.
        Returns True if successful, False otherwise.
        """
        print(f"Starting Playwright crawl for: {self.source_url}")
        print(f"Targeting API: {self.api_endpoint}")
        print(f"Year range: {self.year_range}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )

                # Set up request/response interception
                page = await context.new_page()

                # Capture responses
                page.on('response', lambda response: asyncio.create_task(
                    self._capture_response(response, '/api/product-statistic/tab/detail')
                ))

                # Navigate to page
                print(f"Navigating to {self.source_url}")
                await page.goto(self.source_url, wait_until='networkidle', timeout=self.timeout)

                # Wait for React app to initialize
                await page.wait_for_timeout(3000)

                # Wait for the root element
                try:
                    await page.wait_for_selector('#root', timeout=self.wait_timeout)
                    print("React app loaded")
                except:
                    print("Warning: Could not find #root, but continuing...")

                # Additional wait for API calls to complete
                await page.wait_for_timeout(5000)

                # Try to trigger data loading by scrolling
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)

                # Check if we captured any responses
                detail_responses = [r for r in self.captured_responses
                                  if 'tab/detail' in r['url'] and
                                  'excel_type=daily' in r['url']]

                if detail_responses:
                    print(f"Captured {len(detail_responses)} API responses")
                    # Save the first daily response
                    return await self._save_captured_response(detail_responses[0])
                else:
                    # Try direct API call after page load as fallback
                    print("No API responses captured via interception, trying direct navigation...")
                    return await self._fallback_api_call(page)

        except Exception as e:
            print(f"Playwright crawl failed: {e}")
            return False

    async def _fallback_api_call(self, page: Page) -> bool:
        """
        Fallback: Use the page to make the API call and capture response.
        """
        try:
            # Construct the API URL
            api_url = self._prepare_api_url()

            # Use page to fetch the API (same session/cookies)
            result = await page.evaluate('''
                async (url) => {
                    try {
                        const response = await fetch(url, {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/json'
                            }
                        });
                        return {
                            status: response.status,
                            data: await response.json(),
                            ok: response.ok
                        };
                    } catch (e) {
                        return { error: e.message };
                    }
                }
            ''', api_url)

            if result and result.get('ok') and 'data' in result:
                captured_response = {
                    'url': api_url,
                    'status': result['status'],
                    'data': result['data'],
                    'timestamp': datetime.now().isoformat()
                }
                return await self._save_captured_response(captured_response)
            else:
                print(f"API call failed: {result}")
                return False

        except Exception as e:
            print(f"Fallback API call failed: {e}")
            return False

    async def _save_captured_response(self, response: Dict[str, Any]) -> bool:
        """
        Save captured API response to file.
        """
        try:
            # Create timestamp for filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"api_response_{timestamp}.json"
            filepath = self.raw_dir / filename

            # Save response data
            response_data = {
                'capture_timestamp': response.get('timestamp', datetime.now().isoformat()),
                'url': response.get('url', ''),
                'status': response.get('status', 0),
                'data': response.get('data', {}),
                'year_range': self.year_range,
                'params': self.api_params
            }

            with open(filepath, 'w') as f:
                json.dump(response_data, f, indent=2)

            print(f"Saved API response to: {filepath}")
            return True

        except Exception as e:
            print(f"Failed to save response: {e}")
            return False

    async def crawl(self) -> bool:
        """Main crawl method."""
        # Check if we have crawl4ai available
        if CRAWL4AI_AVAILABLE:
            try:
                return await self.crawl_with_crawl4ai()
            except Exception as e:
                print(f"Crawl4AI failed: {e}, falling back to Playwright...")
                return await self.crawl_with_playwright()
        else:
            return await self.crawl_with_playwright()

    async def crawl_with_crawl4ai(self) -> bool:
        """
        Crawl using Crawl4AI with response capture.
        """
        print(f"Starting Crawl4AI crawl for: {self.source_url}")

        try:
            # Prepare API URL
            api_url = self._prepare_api_url()

            # Configure Crawl4AI
            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                word_count_threshold=1,
                excluded_tags=['nav', 'footer', 'header'],
                exclude_external_links=True,
                markdown_generator=DefaultMarkdownGenerator(
                    content_filter=PruningContentFilter(threshold=0.3)
                ),
                wait_for=self.wait_timeout,
                js_code="""
                    async function waitForApi() {
                        return new Promise((resolve) => {
                            // Wait for React to load
                            setTimeout(() => {
                                resolve(true);
                            }, 3000);
                        });
                    }
                    await waitForApi();
                """
            )

            async with AsyncWebCrawler() as crawler:
                # Crawl the page
                result = await crawler.arun(
                    url=self.source_url,
                    config=config
                )

                # Extract API responses from page data
                # Crawl4AI stores fetched data in result.markdown or result.html
                # We need to capture the network responses differently

                # Since Crawl4AI's response interception is limited,
                # let's use Playwright as the primary method
                print("Crawl4AI may not support full response interception.")
                print("Falling back to Playwright...")
                return await self.crawl_with_playwright()

        except Exception as e:
            print(f"Crawl4AI crawl failed: {e}")
            return False


async def main():
    """Main entry point for crawling."""
    config_path = Path(__file__).parent / 'config.yaml'

    # Verify config exists
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    crawler = NPICrawler(str(config_path))
    result = await crawler.crawl()

    if result:
        print("Crawl completed successfully")
    else:
        print("Crawl failed")

    return result


if __name__ == "__main__":
    # For standalone execution
    asyncio.run(main())
