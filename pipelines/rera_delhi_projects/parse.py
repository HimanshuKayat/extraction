#!/usr/bin/env python3
"""
Parse module for RERA Delhi Projects pipeline.
Converts Excel file to CSV.
"""
import os
import json
import yaml
import csv
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


class RERAParser:
    """Parser for RERA Delhi Excel data."""

    def __init__(self, config_path: str):
        """Initialize parser with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.canonical_columns = self.config['dataset']['canonical_columns']

    def _find_latest_excel_file(self) -> Optional[Path]:
        """Find the most recent Excel file."""
        excel_files = list(self.raw_dir.glob('rera_projects_*.xlsx')) + \
                     list(self.raw_dir.glob('rera_projects_*.xls')) + \
                     list(self.raw_dir.glob('rera_projects_*.csv'))
        if not excel_files:
            return None
        excel_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return excel_files[0]

    def _clean_text(self, text: str) -> str:
        """Clean text."""
        if not text or pd.isna(text):
            return ''
        return ' '.join(str(text).strip().split())

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to match canonical format.
        """
        # Column mapping based on common RERA Excel column names
        col_mapping = {
            'S.No': 'Registration_Number',
            'S.No.': 'Registration_Number',
            'Registration No': 'Registration_Number',
            'Registration Number': 'Registration_Number',
            'Reg No': 'Registration_Number',
            'Reg. No.': 'Registration_Number',
            'Project Name': 'Project_Name',
            'Project': 'Project_Name',
            'Promoter Name': 'Promoter_Name',
            'Promoter': 'Promoter_Name',
            'District': 'District',
            'Reg Date': 'Registration_Date',
            'Registration Date': 'Registration_Date',
            'Status': 'Status',
            'Category': 'Category',
            'Address': 'Address',
        }
        
        # Rename columns
        df = df.rename(columns=col_mapping)
        
        # If Registration_Number is missing, try to create from index
        if 'Registration_Number' not in df.columns:
            df['Registration_Number'] = df.index + 1
        
        # Ensure all canonical columns exist
        for col in self.canonical_columns:
            if col not in df.columns:
                df[col] = ''
        
        return df

    def parse(self, excel_file: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], Path]:
        """
        Parse the Excel file and convert to structured data.
        Returns (parsed_data, output_file_path).
        """
        # Find Excel file if not specified
        if excel_file is None:
            excel_file = self._find_latest_excel_file()

        if excel_file is None:
            raise FileNotFoundError("No Excel file found")

        print(f"Parsing Excel file: {excel_file}")

        try:
            # Read Excel file
            if excel_file.suffix == '.csv':
                df = pd.read_csv(excel_file)
            else:
                df = pd.read_excel(excel_file, engine='openpyxl')
            
            print(f"Loaded {len(df)} rows and {len(df.columns)} columns")
            print(f"Columns: {list(df.columns)}")
            
        except Exception as e:
            print(f"Error reading Excel: {e}")
            raise

        # Normalize columns
        df = self._normalize_columns(df)

        # Clean data
        for col in self.canonical_columns:
            if col in df.columns:
                df[col] = df[col].apply(self._clean_text)

        # Convert to list of dicts
        parsed_data = df[self.canonical_columns].to_dict('records')
        
        # Remove empty rows
        parsed_data = [row for row in parsed_data if any(row.values())]

        print(f"Parsed {len(parsed_data)} records")

        # Save parsed data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.output_dir / f'parsed_projects_{timestamp}.json'

        with open(output_file, 'w') as f:
            json.dump({
                'total_records': len(parsed_data),
                'records': parsed_data,
                'source_file': str(excel_file),
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)

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
                csv_row = {col: row.get(col, '') for col in fieldnames}
                writer.writerow(csv_row)

        print(f"✓ Exported {len(parsed_data)} records to: {output_file}")
        return output_file


if __name__ == "__main__":
    """Main entry point for parsing."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    parser = RERAParser(str(config_path))

    try:
        parsed_data, output_file = parser.parse()
        csv_file = parser.export_csv(parsed_data)
        print(f"\n✓ Successfully parsed and exported {len(parsed_data)} records")
        print(f"CSV saved to: {csv_file}")
        exit(0)
    except Exception as e:
        print(f"✗ Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
