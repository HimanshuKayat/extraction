#!/usr/bin/env python3
"""
Parse module for RERA Delhi Projects pipeline.
Reads project metadata and organizes PDF information.
"""
import os
import json
import yaml
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import csv


class RERAParser:
    """Parser for RERA Delhi project data."""

    def __init__(self, config_path: str):
        """Initialize parser with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.metadata_dir = Path(self.config['paths']['metadata_dir'])
        self.pdf_dir = Path(self.config['paths']['pdf_dir'])
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.canonical_columns = self.config['dataset']['canonical_columns']

    def _find_latest_metadata(self) -> Optional[Path]:
        """Find the most recent metadata file."""
        # First check for download_summary
        summary_files = list(self.metadata_dir.glob('download_summary_*.json'))
        if summary_files:
            summary_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return summary_files[0]

        # Fallback to projects file
        project_files = list(self.metadata_dir.glob('projects_*.json'))
        if project_files:
            project_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return project_files[0]

        return None

    def _clean_text(self, text: str) -> str:
        """Clean text data."""
        if not text:
            return ""
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Remove special characters
        text = re.sub(r'[^\w\s\-\.]', '', text)
        return text.strip()

    def _extract_registration_number(self, text: str) -> str:
        """Extract registration number from text."""
        if not text:
            return ""
        # Look for patterns like RERA/2024/XXX or similar
        patterns = [
            r'RERA[/\-]\d{4}[/\-][A-Z0-9]+',
            r'REG[/\-]\d{4}[/\-][A-Z0-9]+',
            r'\d{4}[/\-][A-Z]{2}[/\-]\d+',
            r'[A-Z]{2,}[/\-]\d{4}[/\-]\d+'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group()
        return text.strip()

    def _parse_date(self, date_str: str) -> str:
        """Parse and standardize date format."""
        if not date_str:
            return ""

        date_str = date_str.strip()
        # Try common formats
        formats = [
            ('%d-%m-%Y', '%Y-%m-%d'),
            ('%d/%m/%Y', '%Y-%m-%d'),
            ('%d %b %Y', '%Y-%m-%d'),
            ('%d %B %Y', '%Y-%m-%d'),
            ('%b %d, %Y', '%Y-%m-%d'),
            ('%Y-%m-%d', '%Y-%m-%d'),
            ('%d-%b-%Y', '%Y-%m-%d'),
        ]

        for input_fmt, output_fmt in formats:
            try:
                dt = datetime.strptime(date_str, input_fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return date_str

    def parse(self, metadata_file: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], Path]:
        """
        Parse the metadata and generate structured data.
        Returns (parsed_data, output_file_path).
        """
        # Find metadata file if not specified
        if metadata_file is None:
            metadata_file = self._find_latest_metadata()

        if metadata_file is None:
            raise FileNotFoundError("No metadata files found")

        print(f"Parsing metadata: {metadata_file}")

        # Read metadata
        with open(metadata_file, 'r') as f:
            data = json.load(f)

        # Extract project list
        projects = []
        if 'projects' in data:
            projects = data['projects']
        elif 'downloaded' in data:
            projects = data['downloaded']
        else:
            # Try to find projects in any key
            for key, value in data.items():
                if isinstance(value, list) and value:
                    if isinstance(value[0], dict) and 'project_name' in value[0]:
                        projects = value
                        break

        if not projects:
            raise ValueError("No projects found in metadata")

        print(f"Found {len(projects)} projects")

        # Parse each project
        parsed_data = []
        for project in projects:
            parsed_project = {}

            # Map to canonical columns
            parsed_project['Project_ID'] = self._extract_registration_number(
                project.get('registration_number', project.get('project_id', ''))
            )
            parsed_project['Project_Name'] = self._clean_text(
                project.get('project_name', 'Unknown')
            )
            parsed_project['Promoter_Name'] = self._clean_text(
                project.get('promoter_name', '')
            )
            parsed_project['District'] = self._clean_text(
                project.get('district', 'Delhi')
            )
            parsed_project['Registration_Number'] = self._extract_registration_number(
                project.get('registration_number', '')
            )
            parsed_project['Registration_Date'] = self._parse_date(
                project.get('registration_date', '')
            )
            parsed_project['PDF_URL'] = project.get('pdf_url', '')
            parsed_project['PDF_Local_Path'] = project.get('pdf_local_path', '')
            parsed_project['Download_Status'] = project.get('download_status', 'unknown')
            parsed_project['Download_Date'] = project.get('download_date', '')

            # Check if PDF exists
            if parsed_project['PDF_Local_Path']:
                pdf_path = Path(parsed_project['PDF_Local_Path'])
                if pdf_path.exists():
                    parsed_project['PDF_Size_Bytes'] = pdf_path.stat().st_size
                    parsed_project['PDF_Exists'] = True
                else:
                    parsed_project['PDF_Exists'] = False
                    parsed_project['PDF_Size_Bytes'] = 0
            else:
                parsed_project['PDF_Exists'] = False
                parsed_project['PDF_Size_Bytes'] = 0

            parsed_data.append(parsed_project)

        # Sort by project name or ID
        parsed_data.sort(key=lambda x: x.get('Project_ID', x.get('Project_Name', '')))

        # Save parsed data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'parsed_projects_{timestamp}.json'

        output_data = {
            'source': str(metadata_file),
            'parse_timestamp': datetime.now().isoformat(),
            'total_projects': len(parsed_data),
            'projects': parsed_data
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"Parsed {len(parsed_data)} projects")
        print(f"Saved parsed data to: {output_file}")

        return parsed_data, output_file

    def export_csv(self, parsed_data: List[Dict[str, Any]], 
                  output_file: Optional[Path] = None) -> Path:
        """
        Export parsed data to CSV.
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.output_dir / f'rera_projects_{timestamp}.csv'

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

        print(f"Exported {len(parsed_data)} rows to: {output_file}")
        return output_file


if __name__ == "__main__":
    config_path = Path(__file__).parent / 'config.yaml'
    parser = RERAParser(str(config_path))

    try:
        parsed_data, output_file = parser.parse()
        csv_file = parser.export_csv(parsed_data)
        print(f"Successfully parsed and exported {len(parsed_data)} projects")
    except Exception as e:
        print(f"Parsing failed: {e}")
