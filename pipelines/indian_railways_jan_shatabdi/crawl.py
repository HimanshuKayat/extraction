#!/usr/bin/env python3
"""
Crawl module for Indian Railways Jan Shatabdi Trains pipeline.
Fetches train data from Indian Railways website.
"""
import os
import json
import time
import yaml
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup


class IndianRailwaysCrawler:
    """Crawler for Indian Railways train data."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config['source']['base_url']
        self.params = self.config['source']['params']
        self.fallback_urls = self.config['source']['fallback_urls']
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Scraping settings
        self.timeout = self.config['scraping']['timeout']
        self.max_retries = self.config['scraping']['max_retries']
        self.user_agent = self.config['scraping']['user_agent']
        self.table_selectors = self.config['scraping']['table_selectors']
        
        # Train type config
        self.train_config = self.config['train_types']['jan_shatabdi']

    def _fetch_page(self, url: str, params: Optional[Dict] = None, retry_count: int = 0) -> Optional[str]:
        """
        Fetch webpage content.
        Returns HTML content or None on failure.
        """
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }

        print(f"Fetching: {url}")
        if params:
            print(f"Params: {params}")

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            response.encoding = 'utf-8'
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
            return self._fetch_page(url, params, retry_count + 1)

        return None

    def _fetch_multiple_sources(self) -> List[str]:
        """Try multiple sources to get train data."""
        html_pages = []
        
        # Try main URL
        print("\n📡 Trying main source...")
        html = self._fetch_page(self.base_url, self.params)
        if html:
            html_pages.append(html)
            print("✓ Main source fetched successfully")
        else:
            print("⚠ Main source failed")
        
        # Try fallback URLs
        if not html_pages:
            print("\n📡 Trying fallback sources...")
            for url in self.fallback_urls:
                print(f"  Trying: {url}")
                html = self._fetch_page(url)
                if html:
                    html_pages.append(html)
                    print(f"  ✓ Success from {url}")
                    break
                print(f"  ✗ Failed from {url}")
        
        return html_pages

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method.
        Returns summary of crawl results.
        """
        print("=" * 60)
        print("INDIAN RAILWAYS - JAN SHATABDI TRAINS EXTRACTION")
        print("=" * 60)

        # Fetch pages
        html_pages = self._fetch_multiple_sources()

        if not html_pages:
            return {
                'success': False,
                'message': 'Failed to fetch any data sources'
            }

        # Save raw HTML
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_files = []
        
        for i, html in enumerate(html_pages):
            filename = f'page_{timestamp}_{i+1}.html'
            raw_file = self.raw_dir / filename
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(html)
            saved_files.append(str(raw_file))
            print(f"Saved raw HTML to: {raw_file}")

        # Save metadata
        metadata_file = self.metadata_dir / f'crawl_metadata_{timestamp}.json'
        with open(metadata_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'files': saved_files,
                'train_type': self.train_config['name']
            }, f, indent=2)

        return {
            'success': True,
            'html_files': saved_files,
            'metadata_file': str(metadata_file)
        }


if __name__ == "__main__":
    """Main entry point for crawling."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    crawler = IndianRailwaysCrawler(str(config_path))
    results = crawler.crawl()

    if results.get('success'):
        print(f"\n✓ Successfully fetched {len(results['html_files'])} pages")
        exit(0)
    else:
        print(f"\n✗ Crawl failed: {results.get('message', 'Unknown error')}")
        exit(1)
