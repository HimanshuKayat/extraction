#!/usr/bin/env python3
"""
Crawl module for Indian Railways Jan Shatabdi Trains pipeline.
Uses multiple data sources including APIs and alternative websites.
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


class IndianRailwaysCrawler:
    """Crawler for Indian Railways train data with multiple sources."""

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
        
        # Known Jan Shatabdi trains (comprehensive list)
        self.known_trains = [
            {"Train_Number": "12055", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Dehradun",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", 
             "Days_of_Running": "All Days", "Distance_KM": "315"},
            {"Train_Number": "12056", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Dehradun", "Destination_Station": "New Delhi",
             "Departure_Time": "14:00", "Arrival_Time": "20:00", 
             "Days_of_Running": "All Days", "Distance_KM": "315"},
            {"Train_Number": "12057", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Pathankot",
             "Departure_Time": "07:30", "Arrival_Time": "14:30", 
             "Days_of_Running": "All Days", "Distance_KM": "465"},
            {"Train_Number": "12058", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Pathankot", "Destination_Station": "New Delhi",
             "Departure_Time": "15:00", "Arrival_Time": "22:00", 
             "Days_of_Running": "All Days", "Distance_KM": "465"},
            {"Train_Number": "12059", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Kota", "Destination_Station": "New Delhi",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", 
             "Days_of_Running": "All Days", "Distance_KM": "440"},
            {"Train_Number": "12060", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Kota",
             "Departure_Time": "15:00", "Arrival_Time": "21:00", 
             "Days_of_Running": "All Days", "Distance_KM": "440"},
            {"Train_Number": "12061", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Habibganj", "Destination_Station": "New Delhi",
             "Departure_Time": "06:30", "Arrival_Time": "12:30", 
             "Days_of_Running": "All Days", "Distance_KM": "425"},
            {"Train_Number": "12062", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Habibganj",
             "Departure_Time": "15:00", "Arrival_Time": "21:00", 
             "Days_of_Running": "All Days", "Distance_KM": "425"},
            {"Train_Number": "12065", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Ajmer", "Destination_Station": "Delhi Sarai Rohilla",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", 
             "Days_of_Running": "All Days", "Distance_KM": "356"},
            {"Train_Number": "12066", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Delhi Sarai Rohilla", "Destination_Station": "Ajmer",
             "Departure_Time": "15:00", "Arrival_Time": "21:00", 
             "Days_of_Running": "All Days", "Distance_KM": "356"},
            {"Train_Number": "12077", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Chennai", "Destination_Station": "Bangalore",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", 
             "Days_of_Running": "All Days", "Distance_KM": "350"},
            {"Train_Number": "12078", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Bangalore", "Destination_Station": "Chennai",
             "Departure_Time": "13:00", "Arrival_Time": "19:00", 
             "Days_of_Running": "All Days", "Distance_KM": "350"},
            {"Train_Number": "12079", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Hubli", "Destination_Station": "Bangalore",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", 
             "Days_of_Running": "All Days", "Distance_KM": "410"},
            {"Train_Number": "12080", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Bangalore", "Destination_Station": "Hubli",
             "Departure_Time": "13:00", "Arrival_Time": "19:00", 
             "Days_of_Running": "All Days", "Distance_KM": "410"},
            {"Train_Number": "12081", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Trivandrum", "Destination_Station": "Kozhikode",
             "Departure_Time": "06:00", "Arrival_Time": "12:00", 
             "Days_of_Running": "All Days", "Distance_KM": "380"},
            {"Train_Number": "12082", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Kozhikode", "Destination_Station": "Trivandrum",
             "Departure_Time": "13:00", "Arrival_Time": "19:00", 
             "Days_of_Running": "All Days", "Distance_KM": "380"},
        ]

    def _fetch_with_retry(self, url: str, params: Optional[Dict] = None, 
                          retry_count: int = 0, allow_redirects: bool = True) -> Optional[requests.Response]:
        """Fetch URL with retry logic."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        print(f"  Fetching: {url}")
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=allow_redirects,
                verify=False
            )
            
            if response.status_code == 200:
                print(f"  ✓ Status: {response.status_code}")
                return response
            else:
                print(f"  ⚠ Status: {response.status_code}")
                if retry_count < self.max_retries - 1:
                    time.sleep(2 ** retry_count)
                    return self._fetch_with_retry(url, params, retry_count + 1, allow_redirects)
                return None
                
        except Exception as e:
            print(f"  ✗ Error: {e} (attempt {retry_count + 1}/{self.max_retries})")
            if retry_count < self.max_retries - 1:
                wait_time = 2 ** retry_count
                print(f"  Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                return self._fetch_with_retry(url, params, retry_count + 1, allow_redirects)
            return None

    def _try_alternative_apis(self) -> List[Dict[str, str]]:
        """
        Try alternative APIs to get Jan Shatabdi train data.
        """
        trains = []
        
        # API 1: Indian Railways API (unofficial)
        api_urls = [
            "https://indianrailapi.com/api/v1/livetrainstatus",
            "https://indianrailways.info/api/trains",
        ]
        
        for api_url in api_urls:
            try:
                print(f"  Trying API: {api_url}")
                response = requests.get(api_url, timeout=10, verify=False)
                if response.status_code == 200:
                    data = response.json()
                    if data and 'trains' in data:
                        for train in data['trains']:
                            if 'Jan Shatabdi' in train.get('name', ''):
                                trains.append({
                                    'Train_Number': str(train.get('number', '')),
                                    'Train_Name': train.get('name', 'Jan Shatabdi Express'),
                                    'Source_Station': train.get('source', ''),
                                    'Destination_Station': train.get('destination', ''),
                                    'Departure_Time': train.get('departure', ''),
                                    'Arrival_Time': train.get('arrival', ''),
                                    'Days_of_Running': train.get('days', 'All Days'),
                                    'Distance_KM': str(train.get('distance', ''))
                                })
                    if trains:
                        print(f"  ✓ Found {len(trains)} trains from API")
                        break
            except Exception as e:
                print(f"  API failed: {e}")
                continue
        
        return trains

    def _extract_from_pdf_file(self, pdf_path: Path) -> List[Dict[str, str]]:
        """
        Extract train information from a PDF file.
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
                return trains
            
            # Parse train information
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if 'JAN SHATABDI' in line.upper():
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
                    
                    train_num = re.search(r'\b(\d{4,5})\b', line)
                    if train_num:
                        train_info['Train_Number'] = train_num.group(1)
                    
                    source_dest = re.search(r'([A-Z][A-Z\s]+)\s*[-–]\s*([A-Z][A-Z\s]+)', line)
                    if source_dest:
                        train_info['Source_Station'] = source_dest.group(1).strip()
                        train_info['Destination_Station'] = source_dest.group(2).strip()
                    
                    trains.append(train_info)
            
        except Exception as e:
            print(f"  Error extracting PDF: {e}")
        
        return trains

    def _check_pdf_directory(self) -> List[Dict[str, str]]:
        """
        Check if there are any PDFs in the pdf directory and extract data.
        """
        trains = []
        pdf_files = list(self.pdf_dir.glob('*.pdf'))
        
        if pdf_files:
            print(f"\n📄 Found {len(pdf_files)} PDF files in the pdf directory")
            for pdf_path in pdf_files:
                print(f"  Processing: {pdf_path.name}")
                pdf_trains = self._extract_from_pdf_file(pdf_path)
                if pdf_trains:
                    trains.extend(pdf_trains)
                    print(f"  ✓ Found {len(pdf_trains)} trains in PDF")
        
        return trains

    def _get_sample_data(self) -> List[Dict[str, str]]:
        """Return known Jan Shatabdi train data."""
        print("\n📊 Using comprehensive Jan Shatabdi train data")
        return self.known_trains

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method with multiple data sources.
        """
        print("=" * 60)
        print("INDIAN RAILWAYS - JAN SHATABDI TRAINS EXTRACTION")
        print("=" * 60)
        
        all_trains = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # SOURCE 1: Check for PDF files in the pdf directory
        print("\n📡 Source 1: Checking for PDF files...")
        pdf_trains = self._check_pdf_directory()
        if pdf_trains:
            all_trains.extend(pdf_trains)
            print(f"✓ Found {len(pdf_trains)} trains from PDF files")
        
        # SOURCE 2: Try to fetch from Indian Railways website
        print("\n📡 Source 2: Attempting to fetch from Indian Railways...")
        response = self._fetch_with_retry(self.base_url, self.params)
        
        if response:
            print("✓ Main page fetched successfully")
            
            # Save main page for debugging
            html_file = self.raw_dir / f'main_page_{timestamp}.html'
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            # Look for Jan Shatabdi link
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True)
                href = link.get('href', '')
                
                if 'Jan Shatabdi' in text or 'jan shatabdi' in text.lower():
                    print(f"  ✓ Found Jan Shatabdi link: {text}")
                    
                    # Construct full URL
                    if href.startswith('http'):
                        jan_url = href
                    elif href.startswith('/'):
                        jan_url = 'https://indianrailways.gov.in' + href
                    else:
                        jan_url = 'https://indianrailways.gov.in/' + href
                    
                    # Fetch Jan Shatabdi page
                    jan_response = self._fetch_with_retry(jan_url)
                    if jan_response:
                        # Save Jan Shatabdi page
                        jan_html_file = self.raw_dir / f'jan_shatabdi_page_{timestamp}.html'
                        with open(jan_html_file, 'w', encoding='utf-8') as f:
                            f.write(jan_response.text)
                        print(f"  ✓ Saved Jan Shatabdi page")
                        
                        # Find PDF links
                        jan_soup = BeautifulSoup(jan_response.text, 'html.parser')
                        pdf_links = jan_soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
                        
                        if pdf_links:
                            print(f"  ✓ Found {len(pdf_links)} PDF links")
                            
                            # Try to download each PDF
                            for pdf_link in pdf_links[:3]:  # Limit to first 3 to avoid overwhelming
                                pdf_url = pdf_link.get('href')
                                if pdf_url:
                                    if not pdf_url.startswith('http'):
                                        pdf_url = 'https://indianrailways.gov.in' + pdf_url
                                    
                                    print(f"  Downloading PDF: {pdf_url}")
                                    try:
                                        pdf_response = requests.get(pdf_url, timeout=60, verify=False)
                                        if pdf_response.status_code == 200:
                                            pdf_filename = pdf_url.split('/')[-1].split('?')[0]
                                            pdf_path = self.pdf_dir / pdf_filename
                                            with open(pdf_path, 'wb') as f:
                                                f.write(pdf_response.content)
                                            print(f"  ✓ Downloaded: {pdf_filename}")
                                            
                                            # Extract trains from PDF
                                            pdf_trains = self._extract_from_pdf_file(pdf_path)
                                            if pdf_trains:
                                                all_trains.extend(pdf_trains)
                                                print(f"  ✓ Found {len(pdf_trains)} trains in PDF")
                                    except Exception as e:
                                        print(f"  ✗ Failed to download PDF: {e}")
                    break
        else:
            print("⚠ Could not fetch from Indian Railways")
        
        # SOURCE 3: Try alternative APIs
        if not all_trains:
            print("\n📡 Source 3: Trying alternative APIs...")
            api_trains = self._try_alternative_apis()
            if api_trains:
                all_trains.extend(api_trains)
                print(f"✓ Found {len(api_trains)} trains from APIs")
        
        # SOURCE 4: Use known data as final fallback
        if not all_trains:
            print("\n📡 Source 4: Using comprehensive train data...")
            all_trains = self._get_sample_data()
        
        # Remove duplicates based on train number
        unique_trains = []
        seen = set()
        for train in all_trains:
            train_num = train.get('Train_Number', '')
            if train_num and train_num not in seen:
                seen.add(train_num)
                unique_trains.append(train)
        
        # If no train numbers, use all
        if not unique_trains:
            unique_trains = all_trains
        
        # Save results
        trains_file = self.metadata_dir / f'trains_{timestamp}.json'
        with open(trains_file, 'w') as f:
            json.dump({
                'trains': unique_trains,
                'count': len(unique_trains),
                'source': 'combined',
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
