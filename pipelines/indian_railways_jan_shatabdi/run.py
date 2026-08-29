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

    def run(self, skip_crawl: bool = False) -> bool:
        """
        Run the complete pipeline.
        
        Args:
            skip_crawl: Skip crawling and use existing HTML
            
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
                
                print(f"✓ Fetched {len(crawl_results.get('html_files', []))} pages")
            else:
                print("\n[1/4] Skipping crawl (using existing HTML)")

            # Step 2: Parse
            print("\n[2/4] Parsing Jan Shatabdi train data...")
            try:
                parsed_data, parsed_file = self.parser.parse()
            except FileNotFoundError:
                print("ERROR: No HTML files found. Run without --skip-crawl first.")
                return False
            
            if not parsed_data:
                print("ERROR: No Jan Shatabdi trains found")
                return False
            
            print(f"✓ Parsed {len(parsed_data)} Jan Shatabdi trains")

            # Step 3: Validate
            print("\n[3/4] Validating train data...")
            validation_results = self.validator.validate(parsed_data)
            
            valid_count = validation_results.get('valid_trains', 0)
            total_count = validation_results.get('total_trains', 0)
            
            if valid_count == 0:
                print("WARNING: No valid trains found")
                print(f"  Total trains: {total_count}")
                print(f"  Invalid trains: {validation_results.get('invalid_trains', 0)}")
            else:
                print(f"✓ {valid_count}/{total_count} trains valid")

            # Step 4: Export CSV
            print("\n[4/4] Exporting to CSV...")
            csv_file = self.parser.export_csv(parsed_data)
            print(f"✓ CSV exported: {csv_file}")

            # Print summary
            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Total Trains: {total_count}")
            print(f"Valid Trains: {valid_count}")
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
                       help='Skip crawling and use existing HTML')
    args = parser.parse_args()

    # Run pipeline
    pipeline = IndianRailwaysPipeline(str(config_path))
    success = pipeline.run(skip_crawl=args.skip_crawl)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
