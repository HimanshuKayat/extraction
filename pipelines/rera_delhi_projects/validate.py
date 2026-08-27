#!/usr/bin/env python3
"""
Validate module for RERA Delhi Projects pipeline.
Validates project data and PDF downloads.
"""
import json
import yaml
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


class RERAValidator:
    """Validator for RERA Delhi Projects data."""

    def __init__(self, config_path: str):
        """Initialize validator with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.output_dir = Path(self.config['paths']['output_dir'])
        self.pdf_dir = Path(self.config['paths']['pdf_dir'])
        self.canonical_columns = self.config['dataset']['canonical_columns']
        self.min_rows = self.config['validation']['min_rows']
        self.require_pdf = self.config['validation']['require_pdf_download']
        self.allowed_extensions = self.config['validation']['allowed_extensions']
        self.max_pdf_size_mb = self.config['validation']['max_pdf_size_mb']

    def _find_latest_parsed_file(self) -> Optional[Path]:
        """Find the most recent parsed data file."""
        parsed_files = list(self.output_dir.glob('parsed_projects_*.json'))
        if not parsed_files:
            return None
        parsed_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return parsed_files[0]

    def _validate_project_id(self, project_id: str) -> bool:
        """Validate project ID format."""
        if not project_id:
            return False
        # Check if it contains letters and numbers
        return bool(re.search(r'[A-Za-z]', project_id)) and bool(re.search(r'\d', project_id))

    def _validate_registration_number(self, reg_num: str) -> bool:
        """Validate registration number format."""
        if not reg_num:
            return True  # Optional field
        # Should contain some alphanumeric characters
        return len(reg_num) >= 4 and bool(re.search(r'[A-Za-z0-9]', reg_num))

    def _validate_pdf_file(self, pdf_path: str) -> Tuple[bool, str]:
        """
        Validate PDF file exists and is valid.
        Returns (is_valid, error_message).
        """
        if not pdf_path:
            return False, "PDF path is empty"

        path = Path(pdf_path)

        # Check if file exists
        if not path.exists():
            return False, f"PDF file not found: {pdf_path}"

        # Check extension
        if path.suffix.lower() not in self.allowed_extensions:
            return False, f"Invalid file extension: {path.suffix}"

        # Check file size
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_pdf_size_mb:
            return False, f"PDF too large: {file_size_mb:.2f} MB"

        # Check if file is non-empty
        if path.stat().st_size == 0:
            return False, "PDF file is empty"

        return True, ""

    def validate(self, parsed_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Validate the parsed data.
        Returns validation results.
        """
        # Load parsed data if not provided
        if parsed_data is None:
            parsed_file = self._find_latest_parsed_file()
            if parsed_file is None:
                raise FileNotFoundError("No parsed data file found")

            with open(parsed_file, 'r') as f:
                data = json.load(f)
                parsed_data = data.get('projects', [])

        if not parsed_data:
            raise ValueError(f"Dataset is empty (min_rows={self.min_rows})")

        print(f"Validating {len(parsed_data)} projects")

        # Validation results
        results = {
            'total_projects': len(parsed_data),
            'valid_projects': 0,
            'invalid_projects': 0,
            'errors': [],
            'warnings': [],
            'pdf_stats': {
                'downloaded': 0,
                'missing': 0,
                'corrupt': 0,
                'total_size_mb': 0
            }
        }

        # Validate each project
        for i, project in enumerate(parsed_data):
            project_errors = []
            project_warnings = []

            # 1. Validate Project_ID
            project_id = project.get('Project_ID', '')
            if not project_id:
                project_errors.append("Project_ID is empty")
            elif not self._validate_project_id(project_id):
                project_warnings.append(f"Project_ID format might be invalid: {project_id}")

            # 2. Validate Project_Name
            project_name = project.get('Project_Name', '')
            if not project_name or project_name == 'Unknown':
                project_warnings.append("Project_Name is missing or default")

            # 3. Validate PDF
            pdf_path = project.get('PDF_Local_Path', '')
            download_status = project.get('Download_Status', 'unknown')

            if self.require_pdf or download_status == 'success':
                is_valid, error = self._validate_pdf_file(pdf_path)
                if is_valid:
                    results['pdf_stats']['downloaded'] += 1
                    # Add file size
                    if pdf_path:
                        path = Path(pdf_path)
                        if path.exists():
                            results['pdf_stats']['total_size_mb'] += path.stat().st_size / (1024 * 1024)
                else:
                    if 'not found' in error.lower():
                        results['pdf_stats']['missing'] += 1
                    else:
                        results['pdf_stats']['corrupt'] += 1
                    project_errors.append(f"PDF validation failed: {error}")

            # 4. Check if required fields are present
            for col in self.canonical_columns:
                if col not in project:
                    project_errors.append(f"Missing required field: {col}")

            # Determine project validity
            is_valid = len(project_errors) == 0

            if is_valid:
                results['valid_projects'] += 1
            else:
                results['invalid_projects'] += 1
                results['errors'].append({
                    'project_index': i,
                    'project_name': project.get('Project_Name', 'Unknown'),
                    'errors': project_errors,
                    'warnings': project_warnings
                })

            # Add warnings separately
            if project_warnings:
                results['warnings'].append({
                    'project_index': i,
                    'project_name': project.get('Project_Name', 'Unknown'),
                    'warnings': project_warnings
                })

        # Save validation report
        report_file = self.output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Validation results: {results['valid_projects']}/{results['total_projects']} projects valid")
        if results['warnings']:
            print(f"Warnings: {len(results['warnings'])}")
        if results['errors']:
            print(f"Errors: {len(results['errors'])}")
            for error in results['errors'][:3]:  # Show first 3 errors
                print(f"  - Project {error['project_index']+1}: {', '.join(error['errors'][:2])}")

        return results


if __name__ == "__main__":
    # For standalone testing
    config_path = Path(__file__).parent / 'config.yaml'
    validator = RERAValidator(str(config_path))

    try:
        results = validator.validate()
        if results['valid_projects'] > 0:
            print("Validation passed!")
        else:
            print("Validation failed!")
    except Exception as e:
        print(f"Validation failed: {e}")
