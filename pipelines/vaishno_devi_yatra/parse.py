#!/usr/bin/env python3
"""
Parse module for Vaishno Devi Yatra Statistics pipeline.
Extracts multiple datasets from HTML tables.
"""
import re
import json
import yaml
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup


class VaishnoDeviParser:
    """Parser for Vaishno Devi Yatra Statistics data."""

    def __init__(self, config_path: str):
        """Initialize parser with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.datasets_config = self.config['dataset']['datasets']

    def _find_latest_html_file(self) -> Optional[Path]:
        """Find the most recent HTML file."""
        html_files = list(self.raw_dir.glob('page_*.html'))
        if not html_files:
            return None
        html_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return html_files[0]

    def _clean_number(self, text: str) -> str:
        """Clean number strings (remove commas, spaces)."""
        if not text:
            return "0"
        # Remove commas and spaces
        cleaned = re.sub(r'[,\s]', '', text.strip())
        return cleaned

    def _parse_annual_table(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse the annual Yatra statistics table.
        """
        annual_data = []
        
        # Find all tables
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
                
            # Check if this is the annual table (look for Year column)
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # Check if this table has year data
            if 'Year' in headers or 'year' in str(headers).lower():
                print("Found annual table")
                
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    
                    if len(cell_texts) >= 3:
                        # Try to parse: S.No., Year, Yatries
                        try:
                            sno = cell_texts[0].strip()
                            year = cell_texts[1].strip()
                            yatries = cell_texts[2].strip()
                            
                            # Only add if year looks like a year (4 digits)
                            if re.match(r'^\d{4}$', year):
                                annual_data.append({
                                    'S.No.': sno,
                                    'Year': year,
                                    'No_of_Yatries_In_Lakhs': self._clean_number(yatries)
                                })
                        except Exception as e:
                            print(f"Error parsing annual row: {e}")
                            continue
                
                if annual_data:
                    break
        
        return annual_data

    def _parse_monthly_1986_onwards(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse the monthly Yatra statistics from 1986 onwards.
        """
        monthly_data = []
        
        # Find all tables
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
                
            # Check if this is the monthly table (look for month columns)
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # Check for month headers
            months = ['January', 'February', 'March', 'April', 'May', 'June', 
                     'July', 'August', 'September', 'October', 'November', 'December']
            
            if any(month in str(headers) for month in months):
                print("Found monthly table (1986 onwards)")
                
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    
                    if len(cell_texts) >= 14:  # Year + 12 months + Total
                        try:
                            year = cell_texts[0].strip()
                            # Only add if year looks like a year (4 digits)
                            if re.match(r'^\d{4}$', year):
                                monthly_entry = {'Year': year}
                                
                                # Add month columns
                                for i, month in enumerate(months):
                                    if i + 1 < len(cell_texts):
                                        monthly_entry[month] = self._clean_number(cell_texts[i + 1])
                                
                                # Add total if available
                                if len(cell_texts) > 13:
                                    monthly_entry['Total'] = self._clean_number(cell_texts[13])
                                
                                monthly_data.append(monthly_entry)
                        except Exception as e:
                            print(f"Error parsing monthly row: {e}")
                            continue
                
                if monthly_data:
                    break
        
        return monthly_data

    def _parse_monthly_2024_2025(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse the monthly Yatra statistics for 2024-2025.
        """
        monthly_data = []
        
        # Look for the specific table with 2024-2025 data
        # The table has "S. No.", "Month", "No. of Yatries"
        
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
                
            # Check headers
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # Look for "Month" and "No. of Yatries" headers
            if 'Month' in str(headers) and 'No. of Yatries' in str(headers):
                print("Found monthly table (2024-2025)")
                
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    
                    if len(cell_texts) >= 3:
                        try:
                            sno = cell_texts[0].strip()
                            month = cell_texts[1].strip()
                            yatries = cell_texts[2].strip()
                            
                            # Clean the month name
                            month = month.replace('"', '').strip()
                            
                            monthly_data.append({
                                'S.No.': sno,
                                'Month': month,
                                'No_of_Yatries': self._clean_number(yatries)
                            })
                        except Exception as e:
                            print(f"Error parsing 2024-2025 row: {e}")
                            continue
                
                if monthly_data:
                    break
        
        return monthly_data

    def parse(self, html_file: Optional[Path] = None) -> Dict[str, Tuple[List[Dict[str, Any]], Path]]:
        """
        Parse the HTML and extract all datasets.
        Returns a dictionary with dataset names as keys and (data, file_path) as values.
        """
        # Find HTML file if not specified
        if html_file is None:
            html_file = self._find_latest_html_file()

        if html_file is None:
            raise FileNotFoundError("No HTML file found")

        print(f"Parsing HTML: {html_file}")

        # Read HTML
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')

        # Parse each dataset
        results = {}
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 1. Annual dataset
        print("\nExtracting Annual Yatra Statistics...")
        annual_data = self._parse_annual_table(soup)
        if annual_data:
            annual_file = self.output_dir / f'annual_yatra_statistics_{timestamp}.json'
            with open(annual_file, 'w') as f:
                json.dump({
                    'dataset': 'annual',
                    'data': annual_data,
                    'count': len(annual_data),
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            results['annual'] = (annual_data, annual_file)
            print(f"  ✓ Found {len(annual_data)} annual records")
        else:
            print("  ✗ No annual data found")

        # 2. Monthly 1986 onwards
        print("\nExtracting Monthly Yatra Statistics (1986 onwards)...")
        monthly_1986_data = self._parse_monthly_1986_onwards(soup)
        if monthly_1986_data:
            monthly_1986_file = self.output_dir / f'monthly_yatra_statistics_1986_onwards_{timestamp}.json'
            with open(monthly_1986_file, 'w') as f:
                json.dump({
                    'dataset': 'monthly_1986_onwards',
                    'data': monthly_1986_data,
                    'count': len(monthly_1986_data),
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            results['monthly_1986_onwards'] = (monthly_1986_data, monthly_1986_file)
            print(f"  ✓ Found {len(monthly_1986_data)} monthly records (1986 onwards)")
        else:
            print("  ✗ No monthly data (1986 onwards) found")

        # 3. Monthly 2024-2025
        print("\nExtracting Monthly Yatra Statistics (2024-2025)...")
        monthly_2024_data = self._parse_monthly_2024_2025(soup)
        if monthly_2024_data:
            monthly_2024_file = self.output_dir / f'monthly_yatra_statistics_2024_2025_{timestamp}.json'
            with open(monthly_2024_file, 'w') as f:
                json.dump({
                    'dataset': 'monthly_2024_2025',
                    'data': monthly_2024_data,
                    'count': len(monthly_2024_data),
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            results['monthly_2024_2025'] = (monthly_2024_data, monthly_2024_file)
            print(f"  ✓ Found {len(monthly_2024_data)} monthly records (2024-2025)")
        else:
            print("  ✗ No monthly data (2024-2025) found")

        return results

    def export_csv(self, parsed_results: Dict[str, Tuple[List[Dict[str, Any]], Path]]) -> Dict[str, Path]:
        """
        Export parsed data to CSV files.
        Returns a dictionary with dataset names as keys and CSV file paths as values.
        """
        csv_files = {}
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for dataset_name, (data, _) in parsed_results.items():
            if not data:
                continue

            # Get column configuration
            dataset_config = self.datasets_config.get(dataset_name)
            if not dataset_config:
                print(f"Warning: No configuration for dataset: {dataset_name}")
                continue

            columns = dataset_config.get('columns', [])
            if not columns:
                print(f"Warning: No columns defined for dataset: {dataset_name}")
                continue

            # Generate CSV filename
            csv_file = self.output_dir / f'{dataset_config["name"]}_{timestamp}.csv'

            # Write CSV
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()

                for row in data:
                    # Only include columns that exist in the row
                    csv_row = {col: row.get(col, '') for col in columns if col in row}
                    writer.writerow(csv_row)

            csv_files[dataset_name] = csv_file
            print(f"  ✓ Exported {len(data)} rows to: {csv_file.name}")

        return csv_files


if __name__ == "__main__":
    """Main entry point for parsing."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    parser = VaishnoDeviParser(str(config_path))

    try:
        parsed_results = parser.parse()
        if parsed_results:
            csv_files = parser.export_csv(parsed_results)
            print(f"\n✓ Successfully parsed and exported {len(csv_files)} datasets")
            for name, path in csv_files.items():
                print(f"  - {name}: {path}")
            exit(0)
        else:
            print("✗ No data parsed")
            exit(1)
    except Exception as e:
        print(f"✗ Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
