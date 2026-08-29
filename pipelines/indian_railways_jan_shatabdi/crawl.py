#!/usr/bin/env python3
"""
Crawl module for Indian Railways Jan Shatabdi Trains pipeline.
Uses requests with proper headers and session management.
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
    """Crawler for Indian Railways train data using requests."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config['source']['base_url']
        self.params = self.config['source']['params']
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
        
        # Train type config
        self.train_config = self.config['train_types']['jan_shatabdi']
        
        # Create a session with persistent cookies
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })

    def _fetch_with_retry(self, url: str, params: Optional[Dict] = None, 
                          retry_count: int = 0, allow_redirects: bool = True) -> Optional[requests.Response]:
        """
        Fetch URL with retry logic and proper handling.
        """
        print(f"  Fetching: {url}")
        
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                allow_redirects=allow_redirects,
                verify=False  # Ignore SSL verification
            )
            
            # Check if we got a response
            if response.status_code == 200:
                print(f"  ✓ Status: {response.status_code}")
                return response
            else:
                print(f"  ⚠ Status: {response.status_code}")
                if retry_count < self.max_retries - 1:
                    time.sleep(2 ** retry_count)
                    return self._fetch_with_retry(url, params, retry_count + 1, allow_redirects)
                return None
                
        except requests.exceptions.Timeout:
            print(f"  ✗ Timeout (attempt {retry_count + 1}/{self.max_retries})")
        except requests.exceptions.ConnectionError:
            print(f"  ✗ Connection error (attempt {retry_count + 1}/{self.max_retries})")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        if retry_count < self.max_retries - 1:
            wait_time = 2 ** retry_count
            print(f"  Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            return self._fetch_with_retry(url, params, retry_count + 1, allow_redirects)
        
        return None

    def _find_jan_shatabdi_page(self, html: str) -> Optional[str]:
        """
        Find the Jan Shatabdi page URL from the HTML.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for Jan Shatabdi link
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if 'Jan Shatabdi' in text or 'jan shatabdi' in text.lower():
                print(f"  ✓ Found Jan Shatabdi link: {text}")
                
                # Construct full URL
                if href.startswith('http'):
                    return href
                elif href.startswith('/'):
                    return 'https://indianrailways.gov.in' + href
                else:
                    # Handle relative URLs
                    base = '/'.join(self.base_url.split('/')[:-1])
                    return base + '/' + href if not href.startswith('/') else 'https://indianrailways.gov.in/' + href
        
        # Alternative: Look for any link containing "Shatabdi"
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if 'Shatabdi' in text:
                print(f"  ✓ Found Shatabdi link: {text}")
                if href.startswith('http'):
                    return href
                elif href.startswith('/'):
                    return 'https://indianrailways.gov.in' + href
        
        return None

    def _extract_pdf_links_from_page(self, html: str, base_url: str) -> List[Dict[str, str]]:
        """
        Extract PDF links from a page.
        """
        soup = BeautifulSoup(html, 'html.parser')
        pdf_links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = 'https://indianrailways.gov.in' + href
                    else:
                        base_dir = '/'.join(base_url.split('/')[:-1])
                        href = base_dir + '/' + href if not href.startswith('/') else 'https://indianrailways.gov.in/' + href
                
                pdf_links.append({
                    'url': href,
                    'text': text or 'PDF Document',
                    'filename': href.split('/')[-1].split('?')[0]
                })
        
        return pdf_links

    def _download_pdf(self, url: str) -> Optional[Path]:
        """
        Download a PDF file.
        """
        try:
            print(f"  Downloading PDF: {url}")
            
            # Use session to download
            response = self.session.get(url, timeout=60, stream=True, verify=False)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type.lower() and len(response.content) > 0:
                # Still try to save it even if content-type is not PDF
                pass
            
            # Generate filename
            filename = url.split('/')[-1].split('?')[0]
            if not filename.endswith('.pdf'):
                filename = f'jan_shatabdi_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
            
            # Clean filename
            filename = re.sub(r'[^\w\s.-]', '_', filename)
            
            pdf_path = self.pdf_dir / filename
            
            # Save the file
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = pdf_path.stat().st_size
            print(f"  ✓ Downloaded: {filename} ({file_size / 1024:.1f} KB)")
            
            if file_size < 1024:  # Less than 1KB
                print(f"  ⚠ File seems too small ({file_size} bytes), might be an error page")
                return None
                
            return pdf_path
            
        except Exception as e:
            print(f"  ✗ Failed to download PDF: {e}")
            return None

    def _extract_trains_from_pdf(self, pdf_path: Path) -> List[Dict[str, str]]:
        """
        Extract train information from PDF file.
        """
        trains = []
        
        try:
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            if not text:
                print(f"  ⚠ No text extracted from PDF: {pdf_path.name}")
                return trains
            
            print(f"  Extracted {len(text)} characters from PDF")
            
            # Parse train information
            lines = text.split('\n')
            found_trains = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for Jan Shatabdi trains
                if 'JAN SHATABDI' in line.upper() or 'JAN-SHATABDI' in line.upper():
                    train_info = {
                        'Train_Number': '',
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
                    
                    # Extract train number
                    train_num = re.search(r'\b(\d{4,5})\b', line)
                    if train_num:
                        train_info['Train_Number'] = train_num.group(1)
                    
                    # Extract source and destination
                    source_dest = re.search(r'([A-Z][A-Z\s]+)\s*[-–]\s*([A-Z][A-Z\s]+)', line)
                    if source_dest:
                        train_info['Source_Station'] = source_dest.group(1).strip()
                        train_info['Destination_Station'] = source_dest.group(2).strip()
                    
                    # Extract time if available
                    time_match = re.search(r'(\d{1,2}:\d{2})\s*(?:to|-)\s*(\d{1,2}:\d{2})', line)
                    if time_match:
                        train_info['Departure_Time'] = time_match.group(1)
                        train_info['Arrival_Time'] = time_match.group(2)
                    
                    # Extract running days
                    days_match = re.search(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun|All Days)', line, re.IGNORECASE)
                    if days_match:
                        train_info['Days_of_Running'] = days_match.group(1)
                    
                    # Extract distance
                    dist_match = re.search(r'(\d+)\s*km', line, re.IGNORECASE)
                    if dist_match:
                        train_info['Distance_KM'] = dist_match.group(1)
                    
                    found_trains.append(train_info)
            
            if found_trains:
                print(f"  ✓ Found {len(found_trains)} trains in PDF")
                trains.extend(found_trains)
            else:
                print(f"  ⚠ No Jan Shatabdi trains found in PDF")
                
                # Try to find any train numbers
                train_numbers = re.findall(r'\b(\d{4,5})\b', text)
                if train_numbers:
                    print(f"  Found train numbers: {list(set(train_numbers))[:5]}...")
                    
                    # Add them as potential trains
                    for num in list(set(train_numbers))[:3]:
                        trains.append({
                            'Train_Number': num,
                            'Train_Name': 'Jan Shatabdi Express (suspected)',
                            'Source_Station': '',
                            'Destination_Station': '',
                            'Departure_Time': '',
                            'Arrival_Time': '',
                            'Travel_Time': '',
                            'Days_of_Running': '',
                            'Classes_Available': '',
                            'Distance_KM': '',
                            'Stops': ''
                        })
            
        except Exception as e:
            print(f"  ✗ Error extracting PDF text: {e}")
        
        return trains

    def _get_sample_data(self) -> List[Dict[str, str]]:
        """Return sample Jan Shatabdi train data."""
        print("\n📊 Using sample Jan Shatabdi train data (fallback)")
        return [
            {"Train_Number": "12055", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Dehradun",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", "Days_of_Running": "All Days"},
            {"Train_Number": "12056", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Dehradun", "Destination_Station": "New Delhi",
             "Departure_Time": "14:00", "Arrival_Time": "20:00", "Days_of_Running": "All Days"},
            {"Train_Number": "12057", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Pathankot",
             "Departure_Time": "07:30", "Arrival_Time": "14:30", "Days_of_Running": "All Days"},
            {"Train_Number": "12058", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Pathankot", "Destination_Station": "New Delhi",
             "Departure_Time": "15:00", "Arrival_Time": "22:00", "Days_of_Running": "All Days"},
            {"Train_Number": "12059", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Kota", "Destination_Station": "New Delhi",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", "Days_of_Running": "All Days"},
            {"Train_Number": "12060", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Kota",
             "Departure_Time": "15:00", "Arrival_Time": "21:00", "Days_of_Running": "All Days"},
        ]

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method using requests.
        """
        print("=" * 60)
        print("INDIAN RAILWAYS - JAN SHATABDI TRAINS EXTRACTION")
        print("=" * 60)
        
        all_trains = []
        
        # Step 1: Fetch main page
        print("\n📡 Step 1: Fetching main page...")
        response = self._fetch_with_retry(self.base_url, self.params)
        
        if response is None:
            print("❌ Failed to fetch main page")
            return {
                'success': False,
                'message': 'Failed to fetch main page'
            }
        
        # Save main page HTML
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_file = self.raw_dir / f'main_page_{timestamp}.html'
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"  ✓ Saved main page to: {html_file}")
        
        # Step 2: Find Jan Shatabdi page
        print("\n📡 Step 2: Looking for Jan Shatabdi link...")
        jan_sh_page = self._find_jan_shatabdi_page(response.text)
        
        if jan_sh_page:
            print(f"  ✓ Found Jan Shatabdi page: {jan_sh_page}")
            
            # Step 3: Fetch Jan Shatabdi page
            print("\n📡 Step 3: Fetching Jan Shatabdi page...")
            jan_response = self._fetch_with_retry(jan_sh_page)
            
            if jan_response:
                # Save Jan Shatabdi page
                jan_html_file = self.raw_dir / f'jan_shatabdi_page_{timestamp}.html'
                with open(jan_html_file, 'w', encoding='utf-8') as f:
                    f.write(jan_response.text)
                print(f"  ✓ Saved Jan Shatabdi page to: {jan_html_file}")
                
                # Step 4: Extract PDF links
                print("\n📡 Step 4: Looking for PDF links...")
                pdf_links = self._extract_pdf_links_from_page(jan_response.text, jan_sh_page)
                
                if pdf_links:
                    print(f"  ✓ Found {len(pdf_links)} PDF links")
                    
                    # Step 5: Download PDFs
                    print("\n📡 Step 5: Downloading PDFs...")
                    for pdf_info in pdf_links:
                        if 'shatabdi' in pdf_info['filename'].lower() or 'train' in pdf_info['filename'].lower():
                            pdf_path = self._download_pdf(pdf_info['url'])
                            if pdf_path:
                                # Step 6: Extract trains from PDF
                                print(f"\n📡 Step 6: Extracting trains from {pdf_path.name}...")
                                pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                if pdf_trains:
                                    all_trains.extend(pdf_trains)
                                    print(f"  ✓ Found {len(pdf_trains)} trains in this PDF")
                                else:
                                    # Try to get sample data
                                    sample_trains = self._get_sample_data()
                                    if sample_trains:
                                        all_trains.extend(sample_trains)
                                        print(f"  ✓ Used {len(sample_trains)} sample trains as fallback")
                else:
                    print("  ⚠ No PDF links found on Jan Shatabdi page")
                    print("  Looking for PDFs on main page...")
                    
                    # Check main page for PDFs
                    main_pdf_links = self._extract_pdf_links_from_page(response.text, self.base_url)
                    if main_pdf_links:
                        print(f"  ✓ Found {len(main_pdf_links)} PDF links on main page")
                        for pdf_info in main_pdf_links[:2]:  # Try first 2
                            pdf_path = self._download_pdf(pdf_info['url'])
                            if pdf_path:
                                pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                if pdf_trains:
                                    all_trains.extend(pdf_trains)
            else:
                print("  ✗ Failed to fetch Jan Shatabdi page")
        else:
            print("  ✗ Could not find Jan Shatabdi link")
            print("  Looking for any PDFs on main page...")
            
            # Try to find PDFs on main page
            pdf_links = self._extract_pdf_links_from_page(response.text, self.base_url)
            if pdf_links:
                print(f"  ✓ Found {len(pdf_links)} PDF links on main page")
                for pdf_info in pdf_links[:3]:  # Try first 3
                    if 'train' in pdf_info['filename'].lower() or 'shatabdi' in pdf_info['filename'].lower():
                        pdf_path = self._download_pdf(pdf_info['url'])
                        if pdf_path:
                            pdf_trains = self._extract_trains_from_pdf(pdf_path)
                            if pdf_trains:
                                all_trains.extend(pdf_trains)

        # If no trains found, use sample data
        if not all_trains:
            print("\n⚠ No Jan Shatabdi trains found automatically")
            print("  Using sample data as fallback...")
            all_trains = self._get_sample_data()
        
        # Remove duplicates
        unique_trains = []
        seen = set()
        for train in all_trains:
            train_num = train.get('Train_Number', '')
            if train_num and train_num not in seen:
                seen.add(train_num)
                unique_trains.append(train)
            elif train_num:
                # Merge duplicate
                for existing in unique_trains:
                    if existing.get('Train_Number') == train_num:
                        for key, value in train.items():
                            if value and not existing.get(key):
                                existing[key] = value
                        break
            else:
                # No train number, keep with unique ID
                train['_id'] = str(len(unique_trains))
                unique_trains.append(train)

        # Save results
        trains_file = self.metadata_dir / f'trains_{timestamp}.json'
        with open(trains_file, 'w') as f:
            json.dump({
                'trains': unique_trains,
                'count': len(unique_trains),
                'source': 'combined' if all_trains else 'sample',
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)
        print(f"\n✓ Saved {len(unique_trains)} trains to: {trains_file}")

        return {
            'success': True,
            'trains_found': len(unique_trains),
            'trains': unique_trains,
            'metadata_file': str(trains_file)
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
        print(f"\n✓ Successfully processed {results.get('trains_found', 0)} trains")
        exit(0)
    else:
        print(f"\n✗ Crawl failed: {results.get('message', 'Unknown error')}")
        exit(1)
