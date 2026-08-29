#!/usr/bin/env python3
"""
Crawl module for RERA Delhi Projects pipeline.
Downloads Excel file from the RERA Delhi website.
"""
import os
import json
import time
import yaml
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import re


class RERACrawler:
    """Crawler for RERA Delhi website to download Excel file."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config['source']['base_url']
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Download settings
        self.max_retries = self.config['download']['max_retries']
        self.timeout = self.config['download']['timeout']
        self.user_agent = self.config['download']['user_agent']
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

    def _fetch_page(self, retry_count: int = 0) -> Optional[str]:
        """
        Fetch the webpage to find the Excel download link.
        """
        print(f"Fetching page: {self.base_url}")

        try:
            response = self.session.get(
                self.base_url,
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
            return self._fetch_page(retry_count + 1)

        return None

    def _find_excel_download_link(self, html: str) -> Optional[str]:
        """
        Find the Excel download link in the HTML.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for Excel/Export buttons
        excel_links = []
        
        # Method 1: Look for links with Excel/Export text
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True).lower()
            href = link.get('href', '')
            
            if 'export' in text or 'excel' in text or 'download' in text:
                if href and ('.xls' in href.lower() or '.xlsx' in href.lower() or 'export' in href.lower()):
                    excel_links.append(href)
                    print(f"  Found export link: {text} -> {href}")
            
            # Also check for onclick or data attributes
            onclick = link.get('onclick', '')
            if 'export' in onclick.lower() or 'excel' in onclick.lower():
                # Try to extract URL from onclick
                url_match = re.search(r"location\.href=['\"]([^'\"]+)['\"]", onclick)
                if url_match:
                    excel_links.append(url_match.group(1))
                    print(f"  Found export in onclick: {onclick}")
        
        # Method 2: Look for buttons with export functionality
        for button in soup.find_all(['button', 'input'], {'type': ['button', 'submit']}):
            text = button.get_text(strip=True).lower()
            onclick = button.get('onclick', '')
            
            if 'export' in text or 'excel' in text or 'download' in text or 'export' in onclick.lower():
                # Try to extract URL from onclick
                if onclick:
                    url_match = re.search(r"location\.href=['\"]([^'\"]+)['\"]", onclick)
                    if url_match:
                        excel_links.append(url_match.group(1))
                        print(f"  Found export button: {text} -> {url_match.group(1)}")
        
        # Method 3: Look for form with export action
        for form in soup.find_all('form'):
            action = form.get('action', '')
            if action and ('export' in action.lower() or 'excel' in action.lower()):
                excel_links.append(action)
                print(f"  Found export form: {action}")
        
        # Construct full URL if relative
        if excel_links:
            excel_url = excel_links[0]
            if not excel_url.startswith('http'):
                if excel_url.startswith('/'):
                    excel_url = 'https://erera.co.in' + excel_url
                else:
                    excel_url = self.base_url.rstrip('/') + '/' + excel_url
            return excel_url
        
        # If no Excel link found, try common export endpoints
        common_export_urls = [
            'https://erera.co.in/reradelhiindex/PublicView/ExportExcel',
            'https://erera.co.in/reradelhiindex/PublicView/ExportToExcel',
            'https://erera.co.in/reradelhiindex/PublicView/DownloadExcel',
            'https://erera.co.in/reradelhiindex/PublicView/ExportData',
        ]
        
        for url in common_export_urls:
            print(f"  Trying common export URL: {url}")
            try:
                response = self.session.head(url, timeout=10)
                if response.status_code == 200:
                    print(f"  ✓ Found working export URL: {url}")
                    return url
            except:
                continue
        
        return None

    def _download_excel(self, download_url: str, retry_count: int = 0) -> Optional[Path]:
        """
        Download the Excel file.
        """
        print(f"Downloading Excel from: {download_url}")

        try:
            # Try with session first
            response = self.session.get(
                download_url,
                timeout=self.timeout,
                stream=True
            )
            
            # If it fails, try without session (some sites work better this way)
            if response.status_code == 403 or response.status_code == 404:
                print("  Trying without session...")
                response = requests.get(
                    download_url,
                    headers={'User-Agent': self.user_agent},
                    timeout=self.timeout,
                    stream=True
                )
            
            response.raise_for_status()
            
            # Determine file extension from content-type or URL
            content_type = response.headers.get('content-type', '')
            if 'xlsx' in content_type or 'excel' in content_type:
                ext = '.xlsx'
            elif 'xls' in content_type:
                ext = '.xls'
            elif 'csv' in content_type:
                ext = '.csv'
            else:
                # Check URL extension
                if '.xlsx' in download_url:
                    ext = '.xlsx'
                elif '.xls' in download_url:
                    ext = '.xls'
                elif '.csv' in download_url:
                    ext = '.csv'
                else:
                    # Default to xlsx
                    ext = '.xlsx'
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'rera_projects_{timestamp}{ext}'
            filepath = self.raw_dir / filename
            
            # Save file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = filepath.stat().st_size
            print(f"✓ Downloaded: {filename} ({file_size / 1024:.1f} KB)")
            
            if file_size < 1024:  # Less than 1KB, might be error page
                print(f"  ⚠ File seems too small ({file_size} bytes), might be an error")
                return None
            
            return filepath

        except Exception as e:
            print(f"Download error: {e}")
            if retry_count < self.max_retries - 1:
                wait_time = 2 ** retry_count
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                return self._download_excel(download_url, retry_count + 1)
            return None

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method.
        Returns summary of crawl results.
        """
        print("=" * 60)
        print("RERA DELHI - EXCEL DATA EXTRACTION")
        print("=" * 60)

        # Step 1: Fetch the main page
        print("\n📡 Step 1: Fetching main page...")
        html = self._fetch_page()

        if html is None:
            return {
                'success': False,
                'message': 'Failed to fetch main page'
            }

        # Save HTML for debugging
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_file = self.raw_dir / f'page_{timestamp}.html'
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ Saved HTML to: {html_file}")

        # Step 2: Find Excel download link
        print("\n📡 Step 2: Looking for Excel download link...")
        download_url = self._find_excel_download_link(html)

        if download_url is None:
            print("⚠ Could not find Excel download link")
            
            # Try common patterns for the download
            print("\n📡 Trying direct download endpoints...")
            common_urls = [
                'https://erera.co.in/reradelhiindex/PublicView/ExportExcel',
                'https://erera.co.in/reradelhiindex/PublicView/ExportToExcel',
                'https://erera.co.in/reradelhiindex/PublicView/DownloadExcel',
                'https://erera.co.in/reradelhiindex/PublicView/ExportData',
            ]
            
            for url in common_urls:
                print(f"  Trying: {url}")
                try:
                    response = self.session.head(url, timeout=10)
                    if response.status_code == 200:
                        download_url = url
                        print(f"  ✓ Found working endpoint: {url}")
                        break
                except:
                    continue
            
            if download_url is None:
                return {
                    'success': False,
                    'message': 'Could not find Excel download link'
                }

        print(f"✓ Found download URL: {download_url}")

        # Step 3: Download Excel file
        print("\n📡 Step 3: Downloading Excel file...")
        excel_path = self._download_excel(download_url)

        if excel_path is None:
            return {
                'success': False,
                'message': 'Failed to download Excel file'
            }

        # Step 4: Save metadata
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'source_url': self.base_url,
            'download_url': download_url,
            'excel_file': str(excel_path),
            'file_size': excel_path.stat().st_size
        }
        
        metadata_file = self.metadata_dir / f'crawl_metadata_{timestamp}.json'
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        return {
            'success': True,
            'excel_file': str(excel_path),
            'metadata_file': str(metadata_file)
        }


if __name__ == "__main__":
    """Main entry point for crawling."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    crawler = RERACrawler(str(config_path))
    results = crawler.crawl()

    if results.get('success'):
        print(f"\n✓ Successfully downloaded Excel file: {results['excel_file']}")
        exit(0)
    else:
        print(f"\n✗ Crawl failed: {results.get('message', 'Unknown error')}")
        exit(1)
