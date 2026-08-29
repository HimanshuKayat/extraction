#!/usr/bin/env python3
"""
Crawl module for Indian Railways Jan Shatabdi Trains pipeline.
Fetches train data from Indian Railways website including PDFs.
"""
import os
import json
import time
import yaml
import requests
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup
import PyPDF2
import io


class IndianRailwaysCrawler:
    """Crawler for Indian Railways train data including PDF extraction."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config['source']['base_url']
        self.params = self.config['source']['params']
        self.fallback_urls = self.config['source']['fallback_urls']
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])
        self.pdf_dir = self.raw_dir / 'pdfs'

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

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

    def _extract_pdf_links(self, html: str, base_url: str) -> List[Dict[str, str]]:
        """
        Extract PDF links from HTML.
        """
        soup = BeautifulSoup(html, 'html.parser')
        pdf_links = []
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Check if it's a PDF link
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                # Handle relative URLs
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = base_url.rstrip('/') + href
                    else:
                        # Handle relative paths
                        base_dir = '/'.join(base_url.split('/')[:-1])
                        href = base_dir + '/' + href if not href.startswith('/') else base_url.rstrip('/') + '/' + href
                
                pdf_links.append({
                    'url': href,
                    'text': text or 'PDF Document',
                    'filename': href.split('/')[-1].split('?')[0]
                })
        
        return pdf_links

    def _download_pdf(self, url: str, filename: str) -> Optional[Path]:
        """
        Download a PDF file.
        """
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Connection': 'keep-alive'
            }
            
            print(f"  Downloading PDF: {filename}")
            response = requests.get(url, headers=headers, timeout=self.timeout, stream=True)
            response.raise_for_status()
            
            # Save PDF
            pdf_path = self.pdf_dir / filename
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print(f"  ✓ Downloaded: {filename} ({pdf_path.stat().st_size / 1024:.1f} KB)")
            return pdf_path
            
        except Exception as e:
            print(f"  ✗ Failed to download {filename}: {e}")
            return None

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """
        Extract text from a PDF file.
        """
        try:
            text = ""
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except Exception as e:
            print(f"  Error extracting PDF text: {e}")
            return ""

    def _extract_trains_from_pdf(self, pdf_text: str) -> List[Dict[str, str]]:
        """
        Extract train information from PDF text.
        """
        trains = []
        
        # Look for Jan Shatabdi trains in the PDF text
        lines = pdf_text.split('\n')
        
        # Patterns for train information
        train_patterns = [
            r'(\d{4,5})\s+(JAN\s+SHATABDI[^\d]*?)(?=\d{4,5}|$)',
            r'(\d{4,5})\s+(JAN-SHATABDI[^\d]*?)(?=\d{4,5}|$)',
            r'(\d{4,5})\s+(JAN\s+SHATBDI[^\d]*?)(?=\d{4,5}|$)',
        ]
        
        # Try to find train numbers and names
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line contains Jan Shatabdi
            if 'JAN SHATABDI' in line.upper() or 'JAN-SHATABDI' in line.upper():
                # Try to extract train number
                train_num = re.search(r'\b(\d{4,5})\b', line)
                
                train_info = {
                    'Train_Number': train_num.group(1) if train_num else '',
                    'Train_Name': 'Jan Shatabdi Express',
                    'Source_Station': '',
                    'Destination_Station': '',
                    'Departure_Time': '',
                    'Arrival_Time': '',
                    'Travel_Time': '',
                    'Days_of_Running': '',
                    'Classes_Available': '',
                    'Distance_KM': '',
                    'Stops': ''
                }
                
                # Try to extract source and destination
                source_dest_pattern = r'([A-Z][A-Z\s]+)\s*-\s*([A-Z][A-Z\s]+)'
                match = re.search(source_dest_pattern, line)
                if match:
                    train_info['Source_Station'] = match.group(1).strip()
                    train_info['Destination_Station'] = match.group(2).strip()
                
                trains.append(train_info)
        
        return trains

    def _fetch_multiple_sources(self) -> List[Tuple[str, str]]:
        """
        Try multiple sources to get train data.
        Returns list of (source_type, content) tuples.
        """
        results = []
        
        # Try main URL
        print("\n📡 Trying main source...")
        html = self._fetch_page(self.base_url, self.params)
        if html:
            results.append(('html', html))
            print("✓ Main source fetched successfully")
            
            # Extract PDF links from main page
            pdf_links = self._extract_pdf_links(html, self.base_url)
            if pdf_links:
                print(f"  Found {len(pdf_links)} PDF links")
                
                # Download PDFs that might contain train schedules
                for pdf_link in pdf_links:
                    if 'shatabdi' in pdf_link['filename'].lower() or 'train' in pdf_link['filename'].lower():
                        pdf_path = self._download_pdf(pdf_link['url'], pdf_link['filename'])
                        if pdf_path:
                            pdf_text = self._extract_text_from_pdf(pdf_path)
                            if pdf_text:
                                results.append(('pdf', pdf_text, pdf_path))
        else:
            print("⚠ Main source failed")
        
        # Try fallback URLs
        if not results:
            print("\n📡 Trying fallback sources...")
            for url in self.fallback_urls:
                print(f"  Trying: {url}")
                html = self._fetch_page(url)
                if html:
                    results.append(('html', html))
                    print(f"  ✓ Success from {url}")
                    break
                print(f"  ✗ Failed from {url}")
        
        return results

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method.
        Returns summary of crawl results.
        """
        print("=" * 60)
        print("INDIAN RAILWAYS - JAN SHATABDI TRAINS EXTRACTION")
        print("=" * 60)

        # Fetch pages
        results = self._fetch_multiple_sources()

        if not results:
            return {
                'success': False,
                'message': 'Failed to fetch any data sources'
            }

        # Save raw data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_files = []
        all_trains = []
        
        for result in results:
            result_type = result[0]
            
            if result_type == 'html':
                html_content = result[1]
                filename = f'page_{timestamp}_{len(saved_files)+1}.html'
                raw_file = self.raw_dir / filename
                with open(raw_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                saved_files.append(str(raw_file))
                print(f"Saved raw HTML to: {raw_file}")
                
            elif result_type == 'pdf':
                pdf_text = result[1]
                pdf_path = result[2] if len(result) > 2 else None
                if pdf_path:
                    saved_files.append(str(pdf_path))
                    print(f"Saved PDF to: {pdf_path}")
                    
                    # Extract trains from PDF
                    trains = self._extract_trains_from_pdf(pdf_text)
                    if trains:
                        all_trains.extend(trains)
                        print(f"  Found {len(trains)} trains in PDF")

        # Save train data if found
        if all_trains:
            trains_file = self.metadata_dir / f'trains_{timestamp}.json'
            with open(trains_file, 'w') as f:
                json.dump({
                    'trains': all_trains,
                    'count': len(all_trains),
                    'source': 'PDF extraction',
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            print(f"Saved train data to: {trains_file}")

        # Save metadata
        metadata_file = self.metadata_dir / f'crawl_metadata_{timestamp}.json'
        with open(metadata_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'files': saved_files,
                'train_type': self.train_config['name'],
                'trains_found': len(all_trains)
            }, f, indent=2)

        return {
            'success': True,
            'files': saved_files,
            'metadata_file': str(metadata_file),
            'trains_found': len(all_trains),
            'trains': all_trains
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
        print(f"\n✓ Successfully fetched {len(results.get('files', []))} files")
        print(f"  Found {results.get('trains_found', 0)} Jan Shatabdi trains")
        exit(0)
    else:
        print(f"\n✗ Crawl failed: {results.get('message', 'Unknown error')}")
        exit(1)
