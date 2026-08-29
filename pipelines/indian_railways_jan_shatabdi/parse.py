#!/usr/bin/env python3
"""
Parse module for Indian Railways Jan Shatabdi Trains pipeline.
Extracts train data from HTML tables.
"""
import re
import json
import yaml
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup


class IndianRailwaysParser:
    """Parser for Indian Railways train data."""

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

        self.canonical_columns = self.config['dataset']['canonical_columns']
        self.train_config = self.config['train_types']['jan_shatabdi']
        self.table_selectors = self.config['scraping']['table_selectors']

    def _find_latest_html_files(self) -> List[Path]:
        """Find the most recent HTML files."""
        html_files = list(self.raw_dir.glob('page_*.html'))
        html_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return html_files

    def _clean_text(self, text: str) -> str:
        """Clean text by removing extra spaces and special characters."""
        if not text:
            return ''
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s\-.,()/]', '', text)
        return text.strip()

    def _parse_time(self, time_str: str) -> str:
        """Parse and standardize time format."""
        if not time_str:
            return ''
        
        # Clean the time string
        time_str = self._clean_text(time_str)
        
        # Try common time formats
        time_patterns = [
            (r'(\d{1,2}):(\d{2})\s*(AM|PM)', r'\1:\2 \3'),
            (r'(\d{1,2})\.(\d{2})\s*(AM|PM)', r'\1:\2 \3'),
            (r'(\d{1,2})(\d{2})\s*(AM|PM)', r'\1:\2 \3'),
            (r'(\d{1,2}):(\d{2})', r'\1:\2'),
        ]
        
        for pattern, replacement in time_patterns:
            if re.search(pattern, time_str, re.IGNORECASE):
                time_str = re.sub(pattern, replacement, time_str, re.IGNORECASE)
                break
        
        return time_str

    def _is_jan_shatabdi(self, train_name: str) -> bool:
        """Check if train is a Jan Shatabdi."""
        if not train_name:
            return False
        
        train_name = train_name.upper()
        
        # Check prefixes
        for prefix in self.train_config['prefixes']:
            if prefix in train_name:
                return True
        
        # Check train numbers
        for num in self.train_config['train_numbers']:
            if num in train_name:
                return True
        
        return False

    def _extract_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract train data from HTML tables."""
        trains = []
        
        for selector in self.table_selectors:
            tables = soup.select(selector)
            if not tables:
                continue
            
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue
                
                # Try to find header row
                header_row = rows[0]
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
                # If no headers found, use generic column names
                if not headers or len(headers) < 2:
                    headers = [f'col_{i}' for i in range(len(rows[1].find_all(['td', 'th'])))]
                
                # Process data rows
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [self._clean_text(cell.get_text()) for cell in cells]
                    
                    # Skip empty rows
                    if not any(cell_texts):
                        continue
                    
                    # Create train entry
                    train_data = {}
                    for i, header in enumerate(headers):
                        if i < len(cell_texts) and cell_texts[i]:
                            train_data[header] = cell_texts[i]
                    
                    # Check if this is a Jan Shatabdi train
                    train_name = train_data.get('Train Name', train_data.get('Train', train_data.get('col_1', '')))
                    if self._is_jan_shatabdi(train_name):
                        trains.append(train_data)
        
        return trains

    def _extract_from_text(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract train data from plain text if tables are not found."""
        trains = []
        
        # Look for paragraphs with train information
        paragraphs = soup.find_all(['p', 'div'])
        
        for para in paragraphs:
            text = para.get_text()
            
            # Look for Jan Shatabdi patterns
            if any(prefix in text.upper() for prefix in self.train_config['prefixes']):
                # Try to extract train info from text
                # This is a fallback, will need to be customized based on actual format
                train_data = {
                    'Train_Name': self._clean_text(text.split('\n')[0])[:50],
                    'Source_Station': 'Unknown',
                    'Destination_Station': 'Unknown',
                    'Departure_Time': '',
                    'Arrival_Time': '',
                }
                trains.append(train_data)
        
        return trains

    def _normalize_train_data(self, raw_trains: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize train data to canonical format."""
        normalized = []
        
        for train in raw_trains:
            normalized_train = {}
            
            # Map common column names to canonical names
            col_mapping = {
                'Train No.': 'Train_Number',
                'Train No': 'Train_Number',
                'Number': 'Train_Number',
                'Train Name': 'Train_Name',
                'Train': 'Train_Name',
                'Name': 'Train_Name',
                'Source': 'Source_Station',
                'Source Station': 'Source_Station',
                'From': 'Source_Station',
                'Destination': 'Destination_Station',
                'Dest': 'Destination_Station',
                'To': 'Destination_Station',
                'Departure': 'Departure_Time',
                'Dep': 'Departure_Time',
                'Departure Time': 'Departure_Time',
                'Arrival': 'Arrival_Time',
                'Arr': 'Arrival_Time',
                'Arrival Time': 'Arrival_Time',
                'Running Days': 'Days_of_Running',
                'Days': 'Days_of_Running',
                'Class': 'Classes_Available',
                'Classes': 'Classes_Available',
                'Distance': 'Distance_KM',
                'Stops': 'Stops',
                'Travel Time': 'Travel_Time',
                'Duration': 'Travel_Time',
            }
            
            for key, value in train.items():
                # Find matching canonical column
                matched = False
                for pattern, col in col_mapping.items():
                    if pattern in key:
                        if col in ['Departure_Time', 'Arrival_Time']:
                            normalized_train[col] = self._parse_time(str(value))
                        else:
                            normalized_train[col] = self._clean_text(str(value))
                        matched = True
                        break
                
                if not matched:
                    # Keep as additional field
                    normalized_train[key] = self._clean_text(str(value))
            
            # Ensure all canonical columns exist
            for col in self.canonical_columns:
                if col not in normalized_train:
                    normalized_train[col] = ''
            
            # Add metadata
            normalized_train['Train_Type'] = 'Jan Shatabdi Express'
            
            normalized.append(normalized_train)
        
        return normalized

    def parse(self, html_files: Optional[List[Path]] = None) -> Tuple[List[Dict[str, Any]], Path]:
        """
        Parse the HTML files and extract train data.
        Returns (parsed_data, output_file_path).
        """
        # Find HTML files if not specified
        if html_files is None:
            html_files = self._find_latest_html_files()

        if not html_files:
            raise FileNotFoundError("No HTML files found")

        print(f"Parsing {len(html_files)} HTML files")

        all_trains = []
        
        for html_file in html_files:
            print(f"Processing: {html_file}")
            
            # Read HTML
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try to extract tables
            trains = self._extract_tables(soup)
            
            # If no tables found, try text extraction
            if not trains:
                print("  No tables found, trying text extraction...")
                trains = self._extract_from_text(soup)
            
            if trains:
                print(f"  Found {len(trains)} potential Jan Shatabdi trains")
                all_trains.extend(trains)
            else:
                print("  No Jan Shatabdi trains found")
        
        # Remove duplicates based on train number and name
        unique_trains = []
        seen = set()
        for train in all_trains:
            # Create a unique key
            train_num = train.get('Train_Number', '')
            train_name = train.get('Train_Name', '')
            key = f"{train_num}_{train_name}"
            
            if key not in seen:
                seen.add(key)
                unique_trains.append(train)
        
        # Normalize the data
        normalized_trains = self._normalize_train_data(unique_trains)
        
        print(f"Parsed {len(normalized_trains)} unique Jan Shatabdi trains")

        # Save parsed data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'jan_shatabdi_trains_{timestamp}.json'
        
        with open(output_file, 'w') as f:
            json.dump({
                'dataset': 'jan_shatabdi_trains',
                'count': len(normalized_trains),
                'trains': normalized_trains,
                'timestamp': datetime.now().isoformat(),
                'source_files': [str(f) for f in html_files]
            }, f, indent=2)

        print(f"Saved parsed data to: {output_file}")

        return normalized_trains, output_file

    def export_csv(self, parsed_data: List[Dict[str, Any]], 
                   output_file: Optional[Path] = None) -> Path:
        """
        Export parsed data to CSV.
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.output_dir / f'jan_shatabdi_trains_{timestamp}.csv'

        if not parsed_data:
            print("No data to export")
            return output_file

        # Use canonical columns
        fieldnames = self.canonical_columns

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()

            for row in parsed_data:
                # Only include canonical columns
                csv_row = {col: row.get(col, '') for col in fieldnames}
                writer.writerow(csv_row)

        print(f"Exported {len(parsed_data)} trains to: {output_file}")
        return output_file


if __name__ == "__main__":
    """Main entry point for parsing."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    parser = IndianRailwaysParser(str(config_path))

    try:
        parsed_data, output_file = parser.parse()
        csv_file = parser.export_csv(parsed_data)
        print(f"\n✓ Successfully parsed and exported {len(parsed_data)} trains")
        print(f"CSV saved to: {csv_file}")
        exit(0)
    except Exception as e:
        print(f"✗ Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
