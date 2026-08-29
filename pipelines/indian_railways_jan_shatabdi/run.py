#!/usr/bin/env python3
"""
Main runner for Indian Railways Jan Shatabdi Trains pipeline.
Orchestrates crawling, parsing, validation, and CSV export.
"""
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from crawl import IndianRailwaysCrawler
from parse import IndianRailwaysParser
from validate import IndianRailwaysValidator


class IndianRailwaysPipeline:
    """Main pipeline orchestrator for Indian Railways Jan Shatabdi Trains."""

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
        self.crawler = IndianRailwaysCrawler(config_path)
        self.parser = IndianRailwaysParser(config_path)
        self.validator = IndianRailwaysValidator(config_path)

    def run(self, skip_crawl: bool = False, use_sample: bool = False) -> bool:
        """
        Run the complete pipeline.
        
        Args:
            skip_crawl: Skip crawling and use existing data
            use_sample: Force use of sample data
            
        Returns:
            bool: True if successful, False otherwise
        """
        print("=" * 70)
        print(f"{self.dataset_name.upper()}")
        print("=" * 70)

        try:
            # Step 1: Crawl (if not skipped)
            if not skip_crawl:
                print("\n[1/4] Fetching train data from Indian Railways...")
                crawl_results = self.crawler.crawl()
                
                if not crawl_results.get('success'):
                    print("ERROR: Crawling failed")
                    print(f"  {crawl_results.get('message', 'Unknown error')}")
                    return False
                
                trains_found = crawl_results.get('trains_found', 0)
                print(f"✓ Found {trains_found} Jan Shatabdi trains")
                
                if trains_found == 0:
                    print("\n⚠ No Jan Shatabdi trains found automatically.")
                    print("The pipeline will try to use sample data if available.")
            else:
                print("\n[1/4] Skipping crawl (using existing data)")

            # Step 2: Parse - This will now use JSON data first
            print("\n[2/4] Parsing Jan Shatabdi train data...")
            try:
                parsed_data, parsed_file = self.parser.parse()
            except Exception as e:
                print(f"ERROR: Parsing failed - {e}")
                return False
            
            if not parsed_data:
                print("WARNING: No Jan Shatabdi trains found in parsed data")
                print("The pipeline will continue with empty dataset.")
                parsed_data = []
            
            print(f"✓ Parsed {len(parsed_data)} Jan Shatabdi trains")

            # Step 3: Validate
            print("\n[3/4] Validating train data...")
            try:
                validation_results = self.validator.validate(parsed_data)
                
                valid_count = validation_results.get('valid_trains', 0)
                total_count = validation_results.get('total_trains', 0)
                
                if valid_count == 0:
                    print("WARNING: No valid trains found")
                    print(f"  Total trains: {total_count}")
                    print(f"  Invalid trains: {validation_results.get('invalid_trains', 0)}")
                else:
                    print(f"✓ {valid_count}/{total_count} trains valid")
            except ValueError as e:
                if "Dataset is empty" in str(e):
                    print("WARNING: Dataset is empty, skipping validation")
                    validation_results = {'valid_trains': 0, 'total_trains': 0}
                else:
                    raise

            # Step 4: Export CSV
            print("\n[4/4] Exporting to CSV...")
            if parsed_data:
                csv_file = self.parser.export_csv(parsed_data)
                print(f"✓ CSV exported: {csv_file}")
            else:
                print("⚠ No data to export to CSV")
                csv_file = None

            # Print summary
            print("\n" + "=" * 70)
            print("SUCCESS" if parsed_data else "COMPLETED WITH WARNINGS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Total Trains: {len(parsed_data)}")
            if csv_file:
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

    parser = argparse.ArgumentParser(description='Indian Railways Jan Shatabdi Trains Pipeline')
    parser.add_argument('--skip-crawl', action='store_true', 
                       help='Skip crawling and use existing data')
    args = parser.parse_args()

    # Run pipeline
    pipeline = IndianRailwaysPipeline(str(config_path))
    success = pipeline.run(skip_crawl=args.skip_crawl)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
