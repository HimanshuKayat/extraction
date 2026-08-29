#!/usr/bin/env python3
"""
Validate module for Indian Railways Jan Shatabdi Trains pipeline.
Validates train data.
"""
import json
import yaml
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class IndianRailwaysValidator:
    """Validator for Indian Railways train data."""

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
        parsed_files = list(self.output_dir.glob('jan_shatabdi_trains_*.json'))
        if not parsed_files:
            return None
        parsed_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return parsed_files[0]

    def _validate_train_number(self, train_num: str) -> bool:
        """Validate train number format."""
        if not train_num:
            return False
        # Indian train numbers are typically 4-5 digits
        return bool(re.match(r'^\d{4,5}$', str(train_num).strip()))

    def _validate_time(self, time_str: str) -> bool:
        """Validate time format."""
        if not time_str:
            return True  # Optional field
        # Check for common time formats
        patterns = [
            r'^\d{1,2}:\d{2}\s*(AM|PM)$',
            r'^\d{1,2}:\d{2}$',
            r'^\d{1,2}\.\d{2}\s*(AM|PM)$',
        ]
        return any(re.match(pattern, str(time_str).strip(), re.IGNORECASE) for pattern in patterns)

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
                parsed_data = data.get('trains', [])

        if not parsed_data:
            if self.min_rows == 0:
                return {'valid': True, 'message': 'Empty dataset allowed'}
            else:
                raise ValueError(f"Dataset is empty (min_rows={self.min_rows})")

        print(f"Validating {len(parsed_data)} Jan Shatabdi trains")

        # Validation results
        results = {
            'total_trains': len(parsed_data),
            'valid_trains': 0,
            'invalid_trains': 0,
            'errors': [],
            'warnings': []
        }

        # Validate each train
        for i, train in enumerate(parsed_data):
            errors = []
            warnings = []

            # Check required columns
            for col in self.required_columns:
                if col not in train or not train[col]:
                    errors.append(f"Missing required column: {col}")

            # Validate Train_Number
            train_num = train.get('Train_Number', '')
            if train_num:
                if not self._validate_train_number(train_num):
                    warnings.append(f"Invalid train number format: {train_num}")
            else:
                errors.append("Train number is missing")

            # Validate Train_Name
            train_name = train.get('Train_Name', '')
            if not train_name:
                errors.append("Train name is missing")
            elif 'Jan Shatabdi' not in train_name and 'JAN SHATABDI' not in train_name.upper():
                warnings.append(f"Train may not be Jan Shatabdi: {train_name}")

            # Validate Source_Station
            if not train.get('Source_Station', ''):
                warnings.append("Source station is missing")

            # Validate Destination_Station
            if not train.get('Destination_Station', ''):
                warnings.append("Destination station is missing")

            # Validate times if present
            dep_time = train.get('Departure_Time', '')
            if dep_time and not self._validate_time(dep_time):
                warnings.append(f"Invalid departure time format: {dep_time}")

            arr_time = train.get('Arrival_Time', '')
            if arr_time and not self._validate_time(arr_time):
                warnings.append(f"Invalid arrival time format: {arr_time}")

            # Determine validity
            is_valid = len(errors) == 0

            if is_valid:
                results['valid_trains'] += 1
            else:
                results['invalid_trains'] += 1
                results['errors'].append({
                    'train_index': i,
                    'train_number': train.get('Train_Number', 'Unknown'),
                    'train_name': train.get('Train_Name', 'Unknown'),
                    'errors': errors,
                    'warnings': warnings
                })

            if warnings:
                results['warnings'].extend(warnings)

        # Check minimum rows
        if results['valid_trains'] < self.min_rows:
            results['valid'] = False
            results['message'] = f"Only {results['valid_trains']} valid trains (min: {self.min_rows})"
        else:
            results['valid'] = True
            results['message'] = f"All {results['valid_trains']} trains are valid"

        # Save validation report
        report_file = self.output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Validation results: {results['valid_trains']}/{results['total_trains']} trains valid")
        if results['warnings']:
            print(f"Warnings: {len(results['warnings'])}")
        if results['errors']:
            print(f"Errors: {len(results['errors'])}")
            for error in results['errors'][:3]:
                print(f"  - {error['train_number']}: {', '.join(error['errors'][:2])}")

        return results


if __name__ == "__main__":
    """Main entry point for validation."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    validator = IndianRailwaysValidator(str(config_path))

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
