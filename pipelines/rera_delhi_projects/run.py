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

    async def run(self, skip_crawl: bool = False, skip_download: bool = False, 
                  manual_html: Optional[str] = None) -> bool:
        """
        Run the complete pipeline.
        
        Args:
            skip_crawl: Skip crawling and use existing metadata
            skip_download: Skip PDF downloads
            manual_html: Path to manually downloaded HTML file
            
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
                
                # If manual HTML is provided, use it
                if manual_html and Path(manual_html).exists():
                    print(f"Using manually provided HTML: {manual_html}")
                    with open(manual_html, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    from crawl import RERACrawler
                    crawler = RERACrawler(str(self.config_path))
                    projects = crawler._extract_pdf_links(html_content)
                    if projects:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        project_file = self.metadata_dir / f'projects_{timestamp}.json'
                        with open(project_file, 'w') as f:
                            json.dump({
                                'projects': projects,
                                'count': len(projects),
                                'source': manual_html,
                                'timestamp': datetime.now().isoformat()
                            }, f, indent=2)
                        self.crawler.projects = projects
                        print(f"✓ Extracted {len(projects)} projects from manual HTML")
                    else:
                        print("No projects found in manual HTML")
                else:
                    # Try automated crawling
                    crawl_results = await self.crawler.crawl()
                    
                    if not crawl_results.get('success'):
                        print("WARNING: Automated crawling failed")
                        print("  The site might be blocking automated requests or be unreachable.")
                        print("  You can manually download the HTML and use the --manual-html option.")
                        
                        # Check if we have existing metadata
                        projects_file = self.crawler._find_latest_projects_file()
                        if projects_file:
                            print(f"  Using existing metadata from: {projects_file}")
                            with open(projects_file, 'r') as f:
                                data = json.load(f)
                                self.crawler.projects = data.get('projects', [])
                            if self.crawler.projects:
                                print(f"  Loaded {len(self.crawler.projects)} projects from metadata")
                                crawl_results['success'] = True
                    
                    projects_found = crawl_results.get('projects_found', 0)
                    download_summary = crawl_results.get('download_summary', {})
                    
                    if projects_found > 0:
                        print(f"✓ Found {projects_found} projects")
                        if not skip_download:
                            print(f"✓ Downloaded {download_summary.get('successful_downloads', 0)} PDFs")
            else:
                print("\n[1/5] Skipping crawl (using existing metadata)")

            # Step 2: Parse
            print("\n[2/5] Parsing project metadata...")
            try:
                parsed_data, parsed_file = self.parser.parse()
            except FileNotFoundError:
                print("ERROR: No metadata found. Options:")
                print("  1. Run without --skip-crawl to try crawling again")
                print("  2. Manually download the HTML and use --manual-html <file>")
                print("  3. Create a sample metadata file with --create-sample")
                return False
            
            if not parsed_data:
                print("ERROR: No data parsed")
                return False
            
            print(f"✓ Parsed {len(parsed_data)} projects")

            # Step 3: Validate
            print("\n[3/5] Validating project data...")
            try:
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
            except Exception as e:
                print(f"WARNING: Validation issue - {e}")
                print("  Continuing with export anyway...")
                validation_results = {}

            # Step 4: Export CSV
            print("\n[4/5] Exporting to CSV...")
            try:
                csv_file = self.parser.export_csv(parsed_data)
                print(f"✓ CSV exported: {csv_file}")
            except Exception as e:
                print(f"ERROR: Failed to export CSV - {e}")
                return False

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
            'errors': validation_results.get('errors', [])[:10],
            'warnings': validation_results.get('warnings', [])[:10]
        }

        return summary

    def _save_summary(self, summary: Dict[str, Any]) -> Path:
        """Save summary to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.metadata_dir / f'pipeline_summary_{timestamp}.json'
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary_file


async def create_sample_metadata():
    """Create sample metadata for testing."""
    sample_projects = [
        {
            'project_name': 'Sample Project 1',
            'promoter_name': 'Sample Promoter',
            'registration_number': 'RERA/2024/001',
            'district': 'Delhi',
            'registration_date': '2024-01-01',
            'pdf_url': 'https://example.com/sample1.pdf'
        },
        {
            'project_name': 'Sample Project 2',
            'promoter_name': 'Another Promoter',
            'registration_number': 'RERA/2024/002',
            'district': 'Delhi',
            'registration_date': '2024-01-02',
            'pdf_url': 'https://example.com/sample2.pdf'
        }
    ]
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path('pipelines/rera_delhi_projects/metadata')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    project_file = output_dir / f'projects_{timestamp}.json'
    with open(project_file, 'w') as f:
        json.dump({
            'projects': sample_projects,
            'count': len(sample_projects),
            'source': 'sample_data',
            'timestamp': datetime.now().isoformat()
        }, f, indent=2)
    
    print(f"Created sample metadata: {project_file}")
    return project_file


async def main():
    """Main entry point."""
    import argparse
    
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    parser = argparse.ArgumentParser(description='RERA Delhi Projects Pipeline')
    parser.add_argument('--skip-crawl', action='store_true', 
                       help='Skip crawling and use existing metadata')
    parser.add_argument('--skip-download', action='store_true',
                       help='Skip PDF downloads')
    parser.add_argument('--manual-html', type=str,
                       help='Path to manually downloaded HTML file')
    parser.add_argument('--create-sample', action='store_true',
                       help='Create sample metadata for testing')
    args = parser.parse_args()

    # Create sample metadata if requested
    if args.create_sample:
        await create_sample_metadata()
        return True

    # Run pipeline
    pipeline = RERAPipeline(str(config_path))
    success = await pipeline.run(
        skip_crawl=args.skip_crawl,
        skip_download=args.skip_download,
        manual_html=args.manual_html
    )

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
