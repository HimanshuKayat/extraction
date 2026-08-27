#!/usr/bin/env python3
"""
Main runner for Vaishno Devi Yatra Statistics pipeline.
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

from crawl import VaishnoDeviCrawler
from parse import VaishnoDeviParser
from validate import VaishnoDeviValidator


class VaishnoDeviPipeline:
    """Main pipeline orchestrator for Vaishno Devi Yatra Statistics."""

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
        self.crawler = VaishnoDeviCrawler(config_path)
        self.parser = VaishnoDeviParser(config_path)
        self.validator = VaishnoDeviValidator(config_path)

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
                print("\n[1/4] Fetching webpage from Vaishno Devi website...")
                crawl_results = self.crawler.crawl()
                
                if not crawl_results.get('success'):
                    print("ERROR: Crawling failed")
                    print(f"  {crawl_results.get('message', 'Unknown error')}")
                    return False
                
                print(f"✓ Page fetched: {crawl_results['html_file']}")
            else:
                print("\n[1/4] Skipping crawl (using existing HTML)")

            # Step 2: Parse
            print("\n[2/4] Parsing Yatra statistics from HTML...")
            try:
                parsed_results = self.parser.parse()
            except FileNotFoundError:
                print("ERROR: No HTML file found. Run without --skip-crawl first.")
                return False
            
            if not parsed_results:
                print("ERROR: No data parsed")
                return False
            
            print(f"✓ Parsed {len(parsed_results)} datasets")

            # Step 3: Export CSV
            print("\n[3/4] Exporting to CSV...")
            csv_files = self.parser.export_csv(parsed_results)
            print(f"✓ Exported {len(csv_files)} CSV files")

            # Step 4: Validate
            print("\n[4/4] Validating data...")
            validation_results = self.validator.validate()
            
            if validation_results['overall_valid']:
                print("✓ All datasets passed validation")
            else:
                print("⚠ Some datasets have issues")

            # Print summary
            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Datasets Extracted: {len(csv_files)}")
            for name, path in csv_files.items():
                print(f"  - {name}: {path}")
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

    parser = argparse.ArgumentParser(description='Vaishno Devi Yatra Statistics Pipeline')
    parser.add_argument('--skip-crawl', action='store_true', 
                       help='Skip crawling and use existing HTML')
    args = parser.parse_args()

    # Run pipeline
    pipeline = VaishnoDeviPipeline(str(config_path))
    success = pipeline.run(skip_crawl=args.skip_crawl)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
