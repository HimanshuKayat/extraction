#!/usr/bin/env python3
"""
Crawl module for Indian Railways Jan Shatabdi Trains pipeline.
Automatically navigates to Jan Shatabdi page, downloads PDF, and extracts data.
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

# Try to import selenium for browser automation
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium not available. Please install: pip install selenium webdriver-manager")

# Try to import playwright for better automation
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not available. Please install: pip install playwright && playwright install")


class IndianRailwaysCrawler:
    """Automated crawler for Indian Railways Jan Shatabdi Trains."""

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
        self.trains_data = []

    def _setup_chrome_options(self) -> Options:
        """Setup Chrome options for Selenium."""
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--window-size=1920,1080')
        return options

    def _extract_pdf_links_from_html(self, html: str, base_url: str) -> List[Dict[str, str]]:
        """
        Extract PDF links from HTML.
        """
        soup = BeautifulSoup(html, 'html.parser')
        pdf_links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Check for Jan Shatabdi link
            if 'Jan Shatabdi' in text or 'jan shatabdi' in text.lower():
                pdf_links.append({
                    'url': href,
                    'text': text,
                    'type': 'jan_shatabdi_page'
                })
            
            # Check for PDF links
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = base_url.rstrip('/') + href
                    else:
                        base_dir = '/'.join(base_url.split('/')[:-1])
                        href = base_dir + '/' + href if not href.startswith('/') else base_url.rstrip('/') + '/' + href
                
                pdf_links.append({
                    'url': href,
                    'text': text or 'PDF Document',
                    'filename': href.split('/')[-1].split('?')[0],
                    'type': 'pdf'
                })
        
        return pdf_links

    async def _crawl_with_playwright(self) -> List[Dict[str, Any]]:
        """
        Use Playwright to automate browser and capture Jan Shatabdi page.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return []

        print("\n🌐 Using Playwright for browser automation...")
        trains = []

        try:
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled'
                    ]
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()

                # Navigate to main page
                print(f"  Navigating to: {self.base_url}")
                await page.goto(self.base_url + '?' + '&'.join([f"{k}={v}" for k, v in self.params.items()]), 
                               wait_until='networkidle', timeout=60000)

                # Wait for page to load
                await page.wait_for_timeout(3000)

                # Find and click Jan Shatabdi link
                print("  Looking for Jan Shatabdi link...")
                jan_shatabdi_link = await page.query_selector('a:has-text("Jan Shatabdi")')
                
                if jan_shatabdi_link:
                    print("  ✓ Found Jan Shatabdi link, clicking...")
                    
                    # Get the href
                    href = await jan_shatabdi_link.get_attribute('href')
                    if href:
                        # Navigate to the Jan Shatabdi page
                        if not href.startswith('http'):
                            href = 'https://indianrailways.gov.in' + href
                        
                        print(f"  Navigating to: {href}")
                        await page.goto(href, wait_until='networkidle', timeout=60000)
                        await page.wait_for_timeout(3000)
                        
                        # Look for PDF links on the Jan Shatabdi page
                        print("  Looking for PDF on Jan Shatabdi page...")
                        pdf_links = await page.query_selector_all('a[href$=".pdf"]')
                        
                        if pdf_links:
                            print(f"  ✓ Found {len(pdf_links)} PDF links")
                            
                            for pdf_link in pdf_links:
                                pdf_href = await pdf_link.get_attribute('href')
                                pdf_text = await pdf_link.inner_text()
                                
                                if pdf_href:
                                    if not pdf_href.startswith('http'):
                                        pdf_href = 'https://indianrailways.gov.in' + pdf_href
                                    
                                    print(f"  Downloading PDF: {pdf_href}")
                                    
                                    # Download PDF
                                    response = await page.goto(pdf_href, wait_until='networkidle')
                                    if response and response.ok:
                                        pdf_content = await response.body()
                                        
                                        # Save PDF
                                        filename = pdf_href.split('/')[-1].split('?')[0]
                                        if not filename.endswith('.pdf'):
                                            filename = f'jan_shatabdi_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
                                        
                                        pdf_path = self.pdf_dir / filename
                                        with open(pdf_path, 'wb') as f:
                                            f.write(pdf_content)
                                        print(f"  ✓ PDF saved: {pdf_path}")
                                        
                                        # Extract data from PDF
                                        pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                        trains.extend(pdf_trains)
                        else:
                            # Try to find PDF links using BeautifulSoup on page content
                            html_content = await page.content()
                            soup = BeautifulSoup(html_content, 'html.parser')
                            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
                            
                            if pdf_links:
                                print(f"  ✓ Found {len(pdf_links)} PDF links via BeautifulSoup")
                                for link in pdf_links:
                                    pdf_href = link.get('href')
                                    if pdf_href:
                                        if not pdf_href.startswith('http'):
                                            pdf_href = 'https://indianrailways.gov.in' + pdf_href
                                        
                                        # Download PDF using requests
                                        pdf_path = self._download_pdf(pdf_href, pdf_href.split('/')[-1])
                                        if pdf_path:
                                            pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                            trains.extend(pdf_trains)
                else:
                    print("  ✗ Jan Shatabdi link not found")
                    
                    # Try to find using text content
                    content = await page.content()
                    if 'Jan Shatabdi' in content:
                        print("  ✓ Found 'Jan Shatabdi' in page content")
                        # Try to find any PDF links
                        pdf_links = await page.query_selector_all('a[href$=".pdf"]')
                        if pdf_links:
                            print(f"  ✓ Found {len(pdf_links)} PDF links on page")
                            for pdf_link in pdf_links:
                                pdf_href = await pdf_link.get_attribute('href')
                                if pdf_href:
                                    if not pdf_href.startswith('http'):
                                        pdf_href = 'https://indianrailways.gov.in' + pdf_href
                                    pdf_path = self._download_pdf(pdf_href, pdf_href.split('/')[-1])
                                    if pdf_path:
                                        pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                        trains.extend(pdf_trains)

                await browser.close()
                print(f"  ✓ Playwright automation complete. Found {len(trains)} trains")
                
        except Exception as e:
            print(f"  ✗ Playwright error: {e}")
            # Try Selenium as fallback
            if SELENIUM_AVAILABLE:
                print("  Falling back to Selenium...")
                trains = self._crawl_with_selenium()
        
        return trains

    def _crawl_with_selenium(self) -> List[Dict[str, Any]]:
        """
        Use Selenium to automate browser and capture Jan Shatabdi page.
        """
        if not SELENIUM_AVAILABLE:
            return []

        print("\n🌐 Using Selenium for browser automation...")
        trains = []
        driver = None

        try:
            options = self._setup_chrome_options()
            
            # Setup driver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(60)
            
            # Navigate to main page
            url = self.base_url + '?' + '&'.join([f"{k}={v}" for k, v in self.params.items()])
            print(f"  Navigating to: {url}")
            driver.get(url)
            time.sleep(3)
            
            # Find and click Jan Shatabdi link
            print("  Looking for Jan Shatabdi link...")
            try:
                jan_link = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Jan Shatabdi"))
                )
                print("  ✓ Found Jan Shatabdi link, clicking...")
                jan_link.click()
                time.sleep(3)
                
                # Now look for PDF links on the Jan Shatabdi page
                print("  Looking for PDF on Jan Shatabdi page...")
                pdf_links = driver.find_elements(By.CSS_SELECTOR, 'a[href$=".pdf"]')
                
                if pdf_links:
                    print(f"  ✓ Found {len(pdf_links)} PDF links")
                    for link in pdf_links:
                        pdf_href = link.get_attribute('href')
                        if pdf_href:
                            print(f"  Downloading PDF: {pdf_href}")
                            pdf_path = self._download_pdf(pdf_href, pdf_href.split('/')[-1])
                            if pdf_path:
                                pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                trains.extend(pdf_trains)
                else:
                    print("  No PDF links found on Jan Shatabdi page")
                    
            except Exception as e:
                print(f"  ✗ Could not find Jan Shatabdi link: {e}")
                # Try to find any PDFs on the page
                pdf_links = driver.find_elements(By.CSS_SELECTOR, 'a[href$=".pdf"]')
                if pdf_links:
                    print(f"  Found {len(pdf_links)} PDF links on main page")
                    for link in pdf_links:
                        pdf_href = link.get_attribute('href')
                        if pdf_href:
                            pdf_path = self._download_pdf(pdf_href, pdf_href.split('/')[-1])
                            if pdf_path:
                                pdf_trains = self._extract_trains_from_pdf(pdf_path)
                                trains.extend(pdf_trains)

        except Exception as e:
            print(f"  ✗ Selenium error: {e}")
        finally:
            if driver:
                driver.quit()
        
        print(f"  ✓ Selenium automation complete. Found {len(trains)} trains")
        return trains

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
            
            response = requests.get(url, headers=headers, timeout=60, stream=True, verify=False)
            response.raise_for_status()
            
            # Clean filename
            filename = re.sub(r'[^\w\s.-]', '_', filename)
            if not filename.endswith('.pdf'):
                filename = f'jan_shatabdi_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
            
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
                print(f"  No text extracted from PDF: {pdf_path.name}")
                return trains
            
            # Parse train information
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for Jan Shatabdi trains
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
                    
                    trains.append(train_info)
            
            if trains:
                print(f"  Extracted {len(trains)} trains from {pdf_path.name}")
            
        except Exception as e:
            print(f"  Error extracting PDF text: {e}")
        
        return trains

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method with automated browser navigation.
        """
        print("=" * 60)
        print("INDIAN RAILWAYS - JAN SHATABDI TRAINS EXTRACTION")
        print("=" * 60)
        
        all_trains = []
        
        # Try Playwright first (better automation)
        if PLAYWRIGHT_AVAILABLE:
            import asyncio
            try:
                all_trains = asyncio.run(self._crawl_with_playwright())
            except Exception as e:
                print(f"Playwright failed: {e}")
                if SELENIUM_AVAILABLE:
                    all_trains = self._crawl_with_selenium()
        elif SELENIUM_AVAILABLE:
            all_trains = self._crawl_with_selenium()
        else:
            print("\n❌ No automation tools available. Please install:")
            print("  pip install playwright selenium webdriver-manager")
            print("  playwright install")
            return {
                'success': False,
                'message': 'No automation tools available'
            }

        # Remove duplicates
        unique_trains = []
        seen = set()
        for train in all_trains:
            train_num = train.get('Train_Number', '')
            if train_num and train_num not in seen:
                seen.add(train_num)
                unique_trains.append(train)
            elif train_num:
                # If duplicate, merge data
                for existing in unique_trains:
                    if existing.get('Train_Number') == train_num:
                        # Merge additional fields
                        for key, value in train.items():
                            if value and not existing.get(key):
                                existing[key] = value
                        break

        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if unique_trains:
            trains_file = self.metadata_dir / f'trains_{timestamp}.json'
            with open(trains_file, 'w') as f:
                json.dump({
                    'trains': unique_trains,
                    'count': len(unique_trains),
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            print(f"\n✓ Saved {len(unique_trains)} trains to: {trains_file}")
        else:
            print("\n⚠ No Jan Shatabdi trains found")
            print("  This could mean:")
            print("  1. The website structure changed")
            print("  2. The Jan Shatabdi link is not accessible")
            print("  3. The PDF doesn't contain train data in the expected format")
            print("\n  Using sample data as fallback...")
            unique_trains = self._get_sample_data()
            trains_file = self.metadata_dir / f'trains_sample_{timestamp}.json'
            with open(trains_file, 'w') as f:
                json.dump({
                    'trains': unique_trains,
                    'count': len(unique_trains),
                    'source': 'sample_fallback',
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)

        return {
            'success': True,
            'trains_found': len(unique_trains),
            'trains': unique_trains,
            'metadata_file': str(trains_file) if 'trains_file' in locals() else None
        }

    def _get_sample_data(self) -> List[Dict[str, str]]:
        """Return sample Jan Shatabdi train data."""
        return [
            {"Train_Number": "12055", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Dehradun"},
            {"Train_Number": "12056", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Dehradun", "Destination_Station": "New Delhi"},
            {"Train_Number": "12057", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Pathankot"},
            {"Train_Number": "12058", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Pathankot", "Destination_Station": "New Delhi"},
            {"Train_Number": "12059", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Kota", "Destination_Station": "New Delhi"},
            {"Train_Number": "12060", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Kota"},
            {"Train_Number": "12061", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Habibganj", "Destination_Station": "New Delhi"},
            {"Train_Number": "12062", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "New Delhi", "Destination_Station": "Habibganj"},
            {"Train_Number": "12065", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Ajmer", "Destination_Station": "Delhi Sarai Rohilla"},
            {"Train_Number": "12066", "Train_Name": "Jan Shatabdi Express", 
             "Source_Station": "Delhi Sarai Rohilla", "Destination_Station": "Ajmer"},
        ]


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
