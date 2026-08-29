#!/usr/bin/env python3
"""
Validate module for RERA Delhi Projects pipeline.
Validates the parsed data.
"""
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class RERAValidator:
    """Validator for RERA Delhi Projects data."""

    def __init__(self, config_path: str):
        """Initialize validator with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.output_dir = Path(self.config['paths']['output_dir'])
        self.canonical_columns = self.config['dataset']['canonical_columns']
        self.min_rows = self.config['validation']['min_rows']
        self.required_columns = self.config['validation']['required_columns']

    def _find_latest_parsed_file(self) -> Optional[Path]:
        """Find the most recent parsed data file."""
        parsed_files = list(self.output_dir.glob('parsed_projects_*.json'))
        if not parsed_files:
            return None
        parsed_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return parsed_files[0]

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
                parsed_data = data.get('records', [])

        if not parsed_data:
            raise ValueError(f"Dataset is empty (min_rows={self.min_rows})")

        print(f"Validating {len(parsed_data)} records")

        results = {
            'total_records': len(parsed_data),
            'valid_records': 0,
            'invalid_records': 0,
            'errors': [],
            'warnings': []
        }

        # Validate each record
        for i, record in enumerate(parsed_data):
            errors = []
            warnings = []

            # Check required columns
            for col in self.required_columns:
                if col not in record or not record[col]:
                    errors.append(f"Missing required column: {col}")

            # Validate Registration_Number
            reg_num = record.get('Registration_Number', '')
            if reg_num and not any(c.isdigit() for c in reg_num):
                warnings.append(f"Registration number might be invalid: {reg_num}")

            # Validate Project_Name
            if not record.get('Project_Name', ''):
                errors.append("Project name is missing")

            # Determine validity
            is_valid = len(errors) == 0

            if is_valid:
                results['valid_records'] += 1
            else:
                results['invalid_records'] += 1
                results['errors'].append({
                    'record_index': i,
                    'registration_number': record.get('Registration_Number', 'Unknown'),
                    'errors': errors,
                    'warnings': warnings
                })

            if warnings:
                results['warnings'].extend(warnings)

        # Check minimum rows
        if results['valid_records'] < self.min_rows:
            results['valid'] = False
            results['message'] = f"Only {results['valid_records']} valid records (min: {self.min_rows})"
        else:
            results['valid'] = True
            results['message'] = f"All {results['valid_records']} records are valid"

        # Save validation report
        report_file = self.output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Validation results: {results['valid_records']}/{results['total_records']} records valid")
        if results['warnings']:
            print(f"Warnings: {len(results['warnings'])}")
        if results['errors']:
            print(f"Errors: {len(results['errors'])}")
            for error in results['errors'][:3]:
                print(f"  - {error['registration_number']}: {', '.join(error['errors'][:2])}")

        return results


if __name__ == "__main__":
    """Main entry point for validation."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    validator = RERAValidator(str(config_path))

    try:
        results = validator.validate()
        if results['valid']:
            print(f"\n✓ Validation passed: {results['message']}")
            exit(0)
        else:
            print(f"\n✗ Validation failed: {results['message']}")
            exit(1)
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        exit(1)
