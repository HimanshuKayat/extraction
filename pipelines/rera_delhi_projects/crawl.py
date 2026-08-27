#!/usr/bin/env python3
"""
Crawl module for RERA Delhi Projects pipeline.
Extracts project listings and PDF URLs from RERA website.
"""
import os
import json
import asyncio
import yaml
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urljoin, urlparse

# Try to import playwright
try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not available. Please install: pip install playwright && playwright install")

# Fallback to requests if playwright not available
import requests
from bs4 import BeautifulSoup


class RERACrawler:
    """Crawler for RERA Delhi website to extract project information and PDFs."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.base_url = self.config['source']['base_url']
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.pdf_dir = Path(self.config['paths']['pdf_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Browser settings
        self.headless = self.config['browser']['headless']
        self.timeout = self.config['browser']['timeout']
        self.wait_timeout = self.config['browser']['wait_timeout']

        # Download settings
        self.max_retries = self.config['download']['max_retries']
        self.timeout_seconds = self.config['download']['timeout']
        self.concurrent_downloads = self.config['download']['concurrent_downloads']

        # State
        self.projects = []
        self.downloaded_pdfs = set()
        self.failed_downloads = []

    def _extract_pdf_links(self, html: str) -> List[Dict[str, str]]:
        """
        Extract PDF links and project information from HTML.
        """
        soup = BeautifulSoup(html, 'html.parser')
        projects = []

        # Look for tables containing project information
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Extract project details
                    project_info = {}
                    
                    # Find PDF links
                    pdf_links = row.find_all('a', href=re.compile(r'\.pdf$', re.I))
                    for link in pdf_links:
                        pdf_url = urljoin(self.base_url, link.get('href', ''))
                        if pdf_url:
                            project_info['pdf_url'] = pdf_url
                    
                    # Extract text data from cells
                    cell_texts = [cell.get_text(strip=True) for cell in cells if cell.get_text(strip=True)]
                    
                    if cell_texts:
                        # Try to identify fields
                        for i, text in enumerate(cell_texts):
                            if 'Project' in text or i == 0:
                                project_info['project_name'] = text
                            elif 'Promoter' in text or i == 1:
                                project_info['promoter_name'] = text
                            elif 'Registration' in text or i == 2:
                                project_info['registration_number'] = text
                            elif 'District' in text or i == 3:
                                project_info['district'] = text
                            elif 'Date' in text or i == 4:
                                project_info['registration_date'] = text
                    
                    # Only add if we have at least a project name or PDF
                    if project_info.get('project_name') or project_info.get('pdf_url'):
                        projects.append(project_info)

        return projects

    async def _get_playwright_page(self) -> Optional[Page]:
        """
        Initialize Playwright and return a page.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True
        )
        page = await context.new_page()
        return page

    async def crawl_with_playwright(self) -> bool:
        """
        Crawl RERA website using Playwright with PDF detection.
        """
        print(f"Starting Playwright crawl for: {self.base_url}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    accept_downloads=True
                )
                page = await context.new_page()

                # Navigate to page
                print(f"Navigating to {self.base_url}")
                await page.goto(self.base_url, wait_until='networkidle', timeout=self.timeout)

                # Wait for content to load
                await page.wait_for_timeout(3000)

                # Handle any popups or dialogs
                try:
                    # Close any modal/dialog if present
                    close_button = await page.query_selector('button:has-text("Close")')
                    if close_button:
                        await close_button.click()
                        await page.wait_for_timeout(1000)
                except:
                    pass

                # Get the page HTML
                html_content = await page.content()

                # Extract project information
                projects = self._extract_pdf_links(html_content)

                if not projects:
                    # Try to find PDFs using other selectors
                    pdf_links = await page.query_selector_all('a[href$=".pdf"]')
                    for link in pdf_links:
                        href = await link.get_attribute('href')
                        text = await link.inner_text()
                        if href:
                            pdf_url = urljoin(self.base_url, href)
                            projects.append({
                                'pdf_url': pdf_url,
                                'project_name': text or 'Unknown',
                                'promoter_name': '',
                                'registration_number': '',
                                'district': 'Delhi',
                                'registration_date': ''
                            })

                # Save projects
                if projects:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    project_file = self.metadata_dir / f'projects_{timestamp}.json'
                    with open(project_file, 'w') as f:
                        json.dump({
                            'projects': projects,
                            'count': len(projects),
                            'source': self.base_url,
                            'timestamp': datetime.now().isoformat()
                        }, f, indent=2)

                    self.projects = projects
                    print(f"Found {len(projects)} projects with PDF links")
                    return True
                else:
                    print("No projects found")
                    return False

        except Exception as e:
            print(f"Playwright crawl failed: {e}")
            # Try fallback method
            return await self.crawl_with_requests()

    def crawl_with_requests(self) -> bool:
        """
        Fallback: Use requests and BeautifulSoup to crawl the page.
        """
        print(f"Using requests fallback for: {self.base_url}")

        try:
            # Set headers to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            response = requests.get(self.base_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Extract projects from HTML
            projects = self._extract_pdf_links(response.text)

            if projects:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                project_file = self.metadata_dir / f'projects_{timestamp}.json'
                with open(project_file, 'w') as f:
                    json.dump({
                        'projects': projects,
                        'count': len(projects),
                        'source': self.base_url,
                        'timestamp': datetime.now().isoformat()
                    }, f, indent=2)

                self.projects = projects
                print(f"Found {len(projects)} projects with PDF links")
                return True
            else:
                print("No projects found")
                return False

        except Exception as e:
            print(f"Requests crawl failed: {e}")
            return False

    async def download_pdf(self, project: Dict[str, Any], retry_count: int = 0) -> bool:
        """
        Download a single PDF file.
        """
        pdf_url = project.get('pdf_url')
        if not pdf_url:
            return False

        # Generate filename
        reg_num = project.get('registration_number', 'unknown')
        proj_name = project.get('project_name', 'unknown')
        # Sanitize filename
        proj_name = re.sub(r'[^\w\s-]', '', proj_name).strip().replace(' ', '_')
        filename = f"{reg_num}_{proj_name}.pdf" if reg_num != 'unknown' else f"{proj_name}.pdf"
        # Ensure unique filename
        filepath = self.pdf_dir / filename

        # Check if already downloaded
        if filepath.exists() and self.config['download']['resume_downloads']:
            print(f"PDF already exists: {filename}")
            project['pdf_local_path'] = str(filepath)
            project['download_status'] = 'exists'
            return True

        print(f"Downloading: {filename} ({pdf_url})")

        try:
            # Use Playwright for download if available
            if PLAYWRIGHT_AVAILABLE:
                return await self._download_with_playwright(pdf_url, filepath, project)
            else:
                return await self._download_with_requests(pdf_url, filepath, project, retry_count)

        except Exception as e:
            if retry_count < self.max_retries:
                print(f"Retry {retry_count + 1}/{self.max_retries} for {filename}")
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                return await self.download_pdf(project, retry_count + 1)
            else:
                print(f"Failed to download {filename}: {e}")
                project['download_status'] = 'failed'
                project['download_error'] = str(e)
                return False

    async def _download_with_playwright(self, pdf_url: str, filepath: Path, project: Dict[str, Any]) -> bool:
        """
        Download PDF using Playwright.
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(accept_downloads=True)
                page = await context.new_page()

                # Navigate to PDF URL
                async with page.expect_download() as download_info:
                    await page.goto(pdf_url, wait_until='networkidle', timeout=self.timeout)

                download = await download_info.value
                # Save the file
                await download.save_as(str(filepath))

                project['pdf_local_path'] = str(filepath)
                project['download_status'] = 'success'

                # Update metadata
                self._update_metadata(project)

                print(f"Downloaded: {filepath.name}")
                return True

        except Exception as e:
            print(f"Playwright download failed: {e}")
            return False

    async def _download_with_requests(self, pdf_url: str, filepath: Path, 
                                     project: Dict[str, Any], retry_count: int) -> bool:
        """
        Download PDF using requests with streaming.
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': self.base_url
            }

            # Use a session for cookies
            session = requests.Session()
            response = session.get(pdf_url, headers=headers, timeout=self.timeout_seconds, stream=True)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type.lower():
                print(f"Warning: Content-Type is not PDF: {content_type}")

            # Save file in chunks
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.config['download']['chunk_size']):
                    if chunk:
                        f.write(chunk)

            # Verify file size
            file_size = filepath.stat().st_size
            max_size = self.config['validation'].get('max_pdf_size_mb', 50) * 1024 * 1024
            if file_size > max_size:
                print(f"Warning: PDF size exceeds limit: {file_size / (1024*1024):.2f} MB")
            elif file_size < 1024:  # Less than 1KB
                print(f"Warning: PDF seems too small: {file_size} bytes")

            project['pdf_local_path'] = str(filepath)
            project['download_status'] = 'success'

            # Update metadata
            self._update_metadata(project)

            print(f"Downloaded: {filepath.name} ({file_size/1024:.1f} KB)")
            return True

        except Exception as e:
            if retry_count < self.max_retries:
                print(f"Retry {retry_count + 1}/{self.max_retries} for {filepath.name}")
                await asyncio.sleep(2 ** retry_count)
                return await self._download_with_requests(pdf_url, filepath, project, retry_count + 1)
            else:
                project['download_status'] = 'failed'
                project['download_error'] = str(e)
                self.failed_downloads.append(project)
                print(f"Failed to download {filepath.name}: {e}")
                return False

    def _update_metadata(self, project: Dict[str, Any]):
        """
        Update metadata file with download status.
        """
        metadata_file = self.metadata_dir / 'downloads.json'
        
        try:
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            else:
                metadata = {'downloaded': [], 'failed': []}

            # Check if project already in list
            existing = next((p for p in metadata['downloaded'] 
                          if p.get('pdf_url') == project.get('pdf_url')), None)
            if existing:
                existing.update(project)
            else:
                metadata['downloaded'].append(project)

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        except Exception as e:
            print(f"Warning: Could not update metadata: {e}")

    async def download_all_pdfs(self) -> Dict[str, Any]:
        """
        Download all PDFs from discovered projects.
        """
        if not self.projects:
            # Load from metadata
            projects_file = self._find_latest_projects_file()
            if projects_file:
                with open(projects_file, 'r') as f:
                    data = json.load(f)
                    self.projects = data.get('projects', [])

        if not self.projects:
            print("No projects found to download")
            return {'success': 0, 'failed': 0, 'total': 0}

        print(f"Downloading PDFs for {len(self.projects)} projects...")

        # Use semaphore for concurrent downloads
        semaphore = asyncio.Semaphore(self.concurrent_downloads)

        async def download_with_semaphore(project):
            async with semaphore:
                return await self.download_pdf(project)

        tasks = [download_with_semaphore(project) for project in self.projects]
        results = await asyncio.gather(*tasks)

        successful = sum(1 for r in results if r)
        failed = len(results) - successful

        # Save final results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_file = self.metadata_dir / f'download_summary_{timestamp}.json'
        
        summary = {
            'total_projects': len(self.projects),
            'successful_downloads': successful,
            'failed_downloads': failed,
            'projects': self.projects,
            'timestamp': datetime.now().isoformat()
        }

        with open(result_file, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"\nDownload complete: {successful} successful, {failed} failed")
        return summary

    def _find_latest_projects_file(self) -> Optional[Path]:
        """Find the most recent projects JSON file."""
        project_files = list(self.metadata_dir.glob('projects_*.json'))
        if not project_files:
            return None
        project_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return project_files[0]

    async def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method.
        Returns summary of crawl results.
        """
        # First, crawl the website to get project list
        if PLAYWRIGHT_AVAILABLE:
            success = await self.crawl_with_playwright()
        else:
            success = self.crawl_with_requests()

        if not success or not self.projects:
            return {'success': False, 'projects_found': 0, 'message': 'No projects found'}

        # Then download PDFs
        download_summary = await self.download_all_pdfs()

        return {
            'success': True,
            'projects_found': len(self.projects),
            'download_summary': download_summary
        }


async def main():
    """Main entry point for crawling."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    crawler = RERACrawler(str(config_path))
    results = await crawler.crawl()

    if results.get('success'):
        print(f"Crawl completed: {results['projects_found']} projects found")
        download_summary = results.get('download_summary', {})
        print(f"Downloads: {download_summary.get('successful_downloads', 0)} successful")
        return True
    else:
        print(f"Crawl failed: {results.get('message', 'Unknown error')}")
        return False


if __name__ == "__main__":
    asyncio.run(main())
