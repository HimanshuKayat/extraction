#!/usr/bin/env python3
"""
Parse module for Wikimedia Airport Data pipeline.
Reads raw Wikidata response and extracts structured data.
"""
import json
import yaml
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class WikimediaAirportParser:
    """Parser for Wikidata airport data."""

    def __init__(self, config_path: str):
        """Initialize parser with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.metadata_dir = Path(self.config['paths']['metadata_dir'])
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.canonical_columns = self.config['dataset']['canonical_columns']

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _find_latest_airport_file(self) -> Optional[Path]:
        """Find the most recent airports JSON file."""
        airport_files = list(self.metadata_dir.glob('airports_*.json'))
        if not airport_files:
            return None
        airport_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return airport_files[0]

    def parse(self, airport_file: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], Path]:
        """
        Parse the airport data.
        Returns (parsed_data, output_file_path).
        """
        # Find file if not specified
        if airport_file is None:
            airport_file = self._find_latest_airport_file()

        if airport_file is None:
            raise FileNotFoundError("No airport data files found")

        print(f"Parsing airport data: {airport_file}")

        # Read data
        with open(airport_file, 'r') as f:
            data = json.load(f)

        # Extract airports
        airports = data.get('airports', [])
        if not airports:
            raise ValueError("No airports found in data")

        print(f"Found {len(airports)} airports to parse")

        # Validate and clean data
        parsed_data = []
        for airport in airports:
            parsed_entry = {
                'Sno.': airport.get('Sno.', len(parsed_data) + 1),
                'Airport': self._clean_text(airport.get('Airport', '')),
                'City': self._clean_text(airport.get('City', '')),
                'Latitude': self._clean_coordinate(airport.get('Latitude')),
                'Longitude': self._clean_coordinate(airport.get('Longitude'))
            }
            parsed_data.append(parsed_entry)

        print(f"Parsed {len(parsed_data)} airports")

        # Save parsed data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'airports_parsed_{timestamp}.json'

        with open(output_file, 'w') as f:
            json.dump({
                'airports': parsed_data,
                'count': len(parsed_data),
                'source': str(airport_file),
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)

        print(f"Saved parsed data to: {output_file}")

        return parsed_data, output_file

    def _clean_text(self, text: str) -> str:
        """Clean text by removing extra spaces."""
        if not text:
            return ''
        return ' '.join(text.strip().split())

    def _clean_coordinate(self, coord: Any) -> Optional[float]:
        """Clean and validate coordinate."""
        if coord is None:
            return None
        try:
            return round(float(coord), 6)
        except (ValueError, TypeError):
            return None

    def export_csv(self, parsed_data: List[Dict[str, Any]], 
                   output_file: Optional[Path] = None) -> Path:
        """
        Export parsed data to CSV.
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.output_dir / f'indian_airports_{timestamp}.csv'

        if not parsed_data:
            print("No data to export")
            return output_file

        # Use canonical columns
        fieldnames = self.canonical_columns

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for row in parsed_data:
                # Filter to only canonical columns
                csv_row = {col: row.get(col, '') for col in fieldnames}
                writer.writerow(csv_row)

        print(f"Exported {len(parsed_data)} airports to: {output_file}")
        return output_file


def main():
    """Main entry point for parsing."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    parser = WikimediaAirportParser(str(config_path))

    try:
        parsed_data, output_file = parser.parse()
        csv_file = parser.export_csv(parsed_data)
        print(f"\n✓ Successfully parsed and exported {len(parsed_data)} airports")
        print(f"CSV saved to: {csv_file}")
        return True
    except Exception as e:
        print(f"✗ Parsing failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
