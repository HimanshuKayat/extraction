#!/usr/bin/env python3
"""
Main runner for RERA Delhi Projects pipeline.
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

from crawl import RERACrawler
from parse import RERAParser
from validate import RERAValidator


class RERAPipeline:
    """Main pipeline orchestrator for RERA Delhi Projects."""

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
        self.crawler = RERACrawler(config_path)
        self.parser = RERAParser(config_path)
        self.validator = RERAValidator(config_path)

    def run(self, skip_crawl: bool = False) -> bool:
        """
        Run the complete pipeline.
        
        Args:
            skip_crawl: Skip crawling and use existing Excel file
            
        Returns:
            bool: True if successful, False otherwise
        """
        print("=" * 70)
        print(f"{self.dataset_name.upper()}")
        print("=" * 70)

        try:
            # Step 1: Crawl (if not skipped)
            if not skip_crawl:
                print("\n[1/4] Downloading Excel file from RERA Delhi...")
                crawl_results = self.crawler.crawl()
                
                if not crawl_results.get('success'):
                    print("ERROR: Crawling failed")
                    print(f"  {crawl_results.get('message', 'Unknown error')}")
                    return False
                
                print(f"✓ Excel file downloaded: {crawl_results['excel_file']}")
            else:
                print("\n[1/4] Skipping crawl (using existing Excel file)")

            # Step 2: Parse
            print("\n[2/4] Parsing Excel data...")
            try:
                parsed_data, parsed_file = self.parser.parse()
            except FileNotFoundError:
                print("ERROR: No Excel file found. Run without --skip-crawl first.")
                return False
            
            if not parsed_data:
                print("ERROR: No data parsed")
                return False
            
            print(f"✓ Parsed {len(parsed_data)} records")

            # Step 3: Validate
            print("\n[3/4] Validating data...")
            validation_results = self.validator.validate(parsed_data)
            
            valid_count = validation_results.get('valid_records', 0)
            total_count = validation_results.get('total_records', 0)
            
            if valid_count == 0:
                print("WARNING: No valid records found")
                print(f"  Total records: {total_count}")
                print(f"  Invalid records: {validation_results.get('invalid_records', 0)}")
            else:
                print(f"✓ {valid_count}/{total_count} records valid")

            # Step 4: Export CSV
            print("\n[4/4] Exporting to CSV...")
            csv_file = self.parser.export_csv(parsed_data)
            print(f"✓ CSV exported: {csv_file}")

            # Print summary
            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Total Records: {total_count}")
            print(f"Valid Records: {valid_count}")
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

    parser = argparse.ArgumentParser(description='RERA Delhi Projects Pipeline')
    parser.add_argument('--skip-crawl', action='store_true', 
                       help='Skip crawling and use existing Excel file')
    args = parser.parse_args()

    # Run pipeline
    pipeline = RERAPipeline(str(config_path))
    success = pipeline.run(skip_crawl=args.skip_crawl)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
