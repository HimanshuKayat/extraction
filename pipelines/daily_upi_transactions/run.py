#!/usr/bin/env python3
"""
Main runner for Daily UPI Transactions pipeline.
Orchestrates crawling, parsing, validation, and CSV export.
"""
import os
import sys
import json
import csv
import yaml
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from crawl import NPICrawler
from parse import NPIParser
from validate import NPIValidator


class DailyUPIPipeline:
    """Main pipeline orchestrator for Daily UPI Transactions."""

    def __init__(self, config_path: str):
        """Initialize pipeline with configuration."""
        self.config_path = config_path

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.dataset_name = self.config['dataset']['name']
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.crawler = NPICrawler(config_path)
        self.parser = NPIParser(config_path)
        self.validator = NPIValidator(config_path)

    async def run(self) -> bool:
        """
        Run the complete pipeline.
        Returns True if successful, False otherwise.
        """
        print("=" * 70)
        print(f"{self.dataset_name.upper()}")
        print("=" * 70)

        try:
            # Step 1: Crawl
            print("\n[1/4] Crawling NPCI with browser/API capture...")
            crawl_success = await self.crawler.crawl()
            if not crawl_success:
                print("ERROR: Crawling failed")
                return False
            print("✓ Crawl completed")

            # Step 2: Parse
            print("\n[2/4] Extracting Daily UPI data...")
            parsed_data, parsed_file = self.parser.parse()
            if not parsed_data:
                print("ERROR: No data parsed")
                return False
            print(f"✓ Parsed {len(parsed_data)} rows")

            # Step 3: Validate
            print("\n[3/4] Validating...")
            validation_results = self.validator.validate(parsed_data)
            if not validation_results['valid']:
                print("ERROR: Validation failed")
                return False
            print("✓ Validation passed")

            # Step 4: Write CSV
            print("\n[4/4] Writing CSV...")
            csv_file = self.output_dir / f"{self.dataset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.config['dataset']['canonical_columns'])
                writer.writeheader()
                for row in parsed_data:
                    writer.writerow(row)
            
            print(f"✓ CSV written: {csv_file}")

            # Print final success
            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Rows: {len(parsed_data)}")
            print(f"Output: {csv_file}")
            print("=" * 70)

            return True

        except Exception as e:
            print(f"\nERROR: Pipeline failed - {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main entry point."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    pipeline = DailyUPIPipeline(str(config_path))
    success = await pipeline.run()
    return success


if __name__ == "__main__":
    # For standalone execution
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
