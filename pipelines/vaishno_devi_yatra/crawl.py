#!/usr/bin/env python3
"""
Crawl module for Vaishno Devi Yatra Statistics pipeline.
Scrapes the webpage and saves HTML for parsing.
"""
import os
import json
import time
import yaml
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class VaishnoDeviCrawler:
    """Crawler for Vaishno Devi Yatra Statistics page."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.url = self.config['source']['url']
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Scraping settings
        self.timeout = self.config['scraping']['timeout']
        self.max_retries = self.config['scraping']['max_retries']
        self.user_agent = self.config['scraping']['user_agent']

    def _fetch_page(self, retry_count: int = 0) -> Optional[str]:
        """
        Fetch the webpage HTML.
        Returns HTML content or None on failure.
        """
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }

        print(f"Fetching page: {self.url}")

        try:
            response = requests.get(
                self.url,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            response.encoding = self.config['source']['encoding']
            return response.text

        except requests.exceptions.Timeout:
            print(f"Timeout error (attempt {retry_count + 1}/{self.max_retries})")
        except requests.exceptions.ConnectionError:
            print(f"Connection error (attempt {retry_count + 1}/{self.max_retries})")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error: {e} (attempt {retry_count + 1}/{self.max_retries})")
        except Exception as e:
            print(f"Unexpected error: {e}")

        if retry_count < self.max_retries - 1:
            wait_time = 2 ** retry_count
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            return self._fetch_page(retry_count + 1)

        return None

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method.
        Returns summary of crawl results.
        """
        print("=" * 60)
        print("VAISHNO DEVI YATRA STATISTICS EXTRACTION")
        print("=" * 60)

        # Fetch the page
        html_content = self._fetch_page()

        if html_content is None:
            return {
                'success': False,
                'message': 'Failed to fetch webpage'
            }

        # Save raw HTML
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        raw_file = self.raw_dir / f'page_{timestamp}.html'
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Saved raw HTML to: {raw_file}")

        # Save metadata
        metadata_file = self.metadata_dir / f'crawl_metadata_{timestamp}.json'
        with open(metadata_file, 'w') as f:
            json.dump({
                'url': self.url,
                'timestamp': datetime.now().isoformat(),
                'file': str(raw_file),
                'size': len(html_content)
            }, f, indent=2)

        return {
            'success': True,
            'html_file': str(raw_file),
            'metadata_file': str(metadata_file)
        }


if __name__ == "__main__":
    """Main entry point for crawling."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    crawler = VaishnoDeviCrawler(str(config_path))
    results = crawler.crawl()

    if results.get('success'):
        print(f"\n✓ Successfully fetched page: {results['html_file']}")
        exit(0)
    else:
        print(f"\n✗ Crawl failed: {results.get('message', 'Unknown error')}")
        exit(1)
