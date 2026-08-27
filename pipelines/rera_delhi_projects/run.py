#!/usr/bin/env python3
"""
Main runner for RERA Delhi Projects pipeline.
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
        self.pdf_dir = Path(self.config['paths']['pdf_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.crawler = RERACrawler(config_path)
        self.parser = RERAParser(config_path)
        self.validator = RERAValidator(config_path)

    async def run(self, skip_crawl: bool = False, skip_download: bool = False) -> bool:
        """
        Run the complete pipeline.
        
        Args:
            skip_crawl: Skip crawling and use existing metadata
            skip_download: Skip PDF downloads
            
        Returns:
            bool: True if successful, False otherwise
        """
        print("=" * 70)
        print(f"{self.dataset_name.upper()}")
        print("=" * 70)

        try:
            # Step 1: Crawl (if not skipped)
            if not skip_crawl:
                print("\n[1/5] Crawling RERA Delhi website for project listings...")
                crawl_results = await self.crawler.crawl()
                
                if not crawl_results.get('success'):
                    print("WARNING: Crawling failed, but continuing with existing data if available...")
                    # Don't return False, try to use existing metadata
                
                projects_found = crawl_results.get('projects_found', 0)
                download_summary = crawl_results.get('download_summary', {})
                
                if projects_found > 0:
                    print(f"✓ Found {projects_found} projects")
                    if not skip_download:
                        print(f"✓ Downloaded {download_summary.get('successful_downloads', 0)} PDFs")
                else:
                    print("No new projects found, checking existing metadata...")
            else:
                print("\n[1/5] Skipping crawl (using existing metadata)")

            # Step 2: Parse
            print("\n[2/5] Parsing project metadata...")
            try:
                parsed_data, parsed_file = self.parser.parse()
            except FileNotFoundError:
                print("ERROR: No metadata found. Run without --skip-crawl first.")
                return False
            
            if not parsed_data:
                print("ERROR: No data parsed")
                return False
            
            print(f"✓ Parsed {len(parsed_data)} projects")

            # Step 3: Validate
            print("\n[3/5] Validating project data...")
            validation_results = self.validator.validate(parsed_data)
            
            if validation_results.get('valid_projects', 0) == 0:
                print("WARNING: No valid projects found")
                print(f"  Total projects: {validation_results.get('total_projects', 0)}")
                print(f"  Invalid projects: {validation_results.get('invalid_projects', 0)}")
                # Continue anyway to export what we have
            else:
                valid_count = validation_results.get('valid_projects', 0)
                total_count = validation_results.get('total_projects', 0)
                print(f"✓ {valid_count}/{total_count} projects valid")

            # Step 4: Export CSV
            print("\n[4/5] Exporting to CSV...")
            csv_file = self.parser.export_csv(parsed_data)
            print(f"✓ CSV exported: {csv_file}")

            # Step 5: Generate summary
            print("\n[5/5] Generating summary...")
            summary = self._generate_summary(parsed_data, validation_results)
            summary_file = self._save_summary(summary)
            print(f"✓ Summary saved: {summary_file}")

            # Print final success
            print("\n" + "=" * 70)
            print("SUCCESS")
            print("=" * 70)
            print(f"Dataset: {self.dataset_name}")
            print(f"Total Projects: {summary['total_projects']}")
            print(f"Valid Projects: {summary['valid_projects']}")
            print(f"PDFs Downloaded: {summary['pdf_statistics']['downloaded']}")
            print(f"Total PDF Size: {summary['pdf_statistics']['total_size_mb']:.2f} MB")
            print(f"Output CSV: {csv_file}")
            print("=" * 70)

            return True

        except Exception as e:
            print(f"\nERROR: Pipeline failed - {e}")
            import traceback
            traceback.print_exc()
            return False

    def _generate_summary(self, parsed_data: List[Dict[str, Any]], 
                         validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate pipeline summary."""
        # Count projects by district
        districts = {}
        for project in parsed_data:
            district = project.get('District', 'Unknown')
            districts[district] = districts.get(district, 0) + 1

        # Count download status
        download_status = {}
        for project in parsed_data:
            status = project.get('Download_Status', 'unknown')
            download_status[status] = download_status.get(status, 0) + 1

        # PDF statistics
        pdf_stats = validation_results.get('pdf_stats', {})
        total_pdf_size_mb = pdf_stats.get('total_size_mb', 0)

        summary = {
            'dataset': self.dataset_name,
            'timestamp': datetime.now().isoformat(),
            'total_projects': len(parsed_data),
            'valid_projects': validation_results.get('valid_projects', 0),
            'invalid_projects': validation_results.get('invalid_projects', 0),
            'districts': districts,
            'download_status': download_status,
            'pdf_statistics': {
                'downloaded': pdf_stats.get('downloaded', 0),
                'missing': pdf_stats.get('missing', 0),
                'corrupt': pdf_stats.get('corrupt', 0),
                'total_size_mb': total_pdf_size_mb
            },
            'errors': validation_results.get('errors', [])[:10],  # First 10 errors
            'warnings': validation_results.get('warnings', [])[:10]  # First 10 warnings
        }

        return summary

    def _save_summary(self, summary: Dict[str, Any]) -> Path:
        """Save summary to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.metadata_dir / f'pipeline_summary_{timestamp}.json'
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary_file


async def main():
    """Main entry point."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='RERA Delhi Projects Pipeline')
    parser.add_argument('--skip-crawl', action='store_true', 
                       help='Skip crawling and use existing metadata')
    parser.add_argument('--skip-download', action='store_true',
                       help='Skip PDF downloads')
    args = parser.parse_args()

    # Run pipeline
    pipeline = RERAPipeline(str(config_path))
    success = await pipeline.run(
        skip_crawl=args.skip_crawl,
        skip_download=args.skip_download
    )

    return success


if __name__ == "__main__":
    # For standalone execution
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
