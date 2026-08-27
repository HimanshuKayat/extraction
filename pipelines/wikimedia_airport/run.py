#!/usr/bin/env python3
"""
Main runner for Wikimedia Airport Data pipeline.
Orchestrates crawling, parsing, validation, and CSV export.
"""
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from crawl import WikidataCrawler
from parse import WikimediaAirportParser
from validate import WikimediaAirportValidator


class WikimediaAirportPipeline:
    """Main pipeline orchestrator for Wikimedia Airport Data."""

    def __init__(self, config_path: str):
        """Initialize pipeline with configuration."""
        self.config_path = config_path

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.dataset_name = self.config['dataset']['name']
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.crawler = WikidataCrawler(config_path)
        self.parser = WikimediaAirportParser(config_path)
        self.validator = WikimediaAirportValidator(config_path)

    def run(self, skip_crawl: bool = False) -> bool:
        """
        Run the complete pipeline.
        
        Args:
            skip_crawl: Skip crawling and use existing metadata
            
        Returns:
            bool: True if successful, False otherwise
        """
        print("=" * 70)
        print(f"{self.dataset_name.upper()}")
        print("=" * 70)

        try:
            # Step 1: Crawl (if not skipped)
            if not skip_crawl:
                print("\n[1/4] Fetching airport data from Wikidata...")
                crawl_results = self.crawler.crawl()
                
                if not crawl_results.get('success'):
                    print("ERROR: Crawling failed")
                    print(f"  {crawl_results.get('message', 'Unknown error')}")
                    return False
                
                airports_found = crawl_results.get('airports_found', 0)
                print(f"✓ Found {airports_found} airports in Wikidata")
            else:
                print("\n[1/4] Skipping crawl (using existing metadata)")

            # Step 2: Parse
            print("\n[2/4] Parsing airport data...")
            try:
                parsed_data, parsed_file = self.parser.parse()
            except FileNotFoundError:
                print("ERROR: No data found. Run without --skip-crawl first.")
                return False
            
            if not parsed_data:
                print("ERROR: No data parsed")
                return False
            
            print(f"✓ Parsed {len(parsed_data)} airports")

            # Step 3: Validate
            print("\n[3/4] Validating airport data...")
            validation_results = self.validator.validate(parsed_data)
            
            valid_count = validation_results.get('valid_airports', 0)
            total_count = validation_results.get('total_airports', 0)
            
            if valid_count == 0:
                print("WARNING: No valid airports found")
                print(f"  Total airports: {total_count}")
                print(f"  Invalid airports: {validation_results.get('invalid_airports', 0)}")
            else:
                print(f"✓ {valid_count}/{total_count} airports valid")

            # Step 4: Export CSV
            print("\n[4/4] Exporting to CSV...")
            csv_file = self.parser.export_csv(parsed_data)
            print(f"✓ CSV exported: {csv_file}")

            # Print summary
            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Total Airports: {total_count}")
            print(f"Valid Airports: {valid_count}")
            print(f"Output CSV: {csv_file}")
            print("=" * 70)

            return True

        except Exception as e:
            print(f"\nERROR: Pipeline failed - {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point."""
    import argparse
    
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    parser = argparse.ArgumentParser(description='Wikimedia Airport Data Pipeline')
    parser.add_argument('--skip-crawl', action='store_true', 
                       help='Skip crawling and use existing metadata')
    args = parser.parse_args()

    # Run pipeline
    pipeline = WikimediaAirportPipeline(str(config_path))
    success = pipeline.run(skip_crawl=args.skip_crawl)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
