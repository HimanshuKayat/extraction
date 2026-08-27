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
                print
