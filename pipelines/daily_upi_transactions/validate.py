#!/usr/bin/env python3
"""
Validate module for Daily UPI Transactions pipeline.
Validates parsed data structure and content.
"""
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re


class NPIValidator:
    """Validator for Daily UPI Transactions data."""

    def __init__(self, config_path: str):
        """Initialize validator with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.output_dir = Path(self.config['paths']['output_dir'])
        self.canonical_columns = self.config['dataset']['canonical_columns']
        self.min_rows = self.config['validation']['min_rows']
        self.allow_empty = self.config['validation']['allow_empty']

    def _find_parsed_file(self) -> Optional[Path]:
        """Find the most recent parsed data file."""
        parsed_files = list(self.output_dir.glob('parsed_data_*.json'))
        if not parsed_files:
            return None
        parsed_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return parsed_files[0]

    def _validate_columns(self, data: List[Dict[str, Any]]) -> List[str]:
        """
        Validate that required columns exist.
        Returns list of missing columns.
        """
        if not data:
            return self.canonical_columns  # All columns missing

        # Get all column names from first row
        first_row = data[0]
        row_columns = set(first_row.keys())

        # Check for required columns
        missing = []
        for col in self.canonical_columns:
            if col not in row_columns:
                missing.append(col)

        return missing

    def _validate_date_format(self, date_str: str) -> bool:
        """
        Validate that the string is a valid date format.
        """
        if not date_str or date_str == "":
            return False

        # Try common date formats
        formats = [
            '%Y-%m-%d',      # 2026-04-01
            '%d-%m-%Y',      # 01-04-2026
            '%d/%m/%Y',      # 01/04/2026
            '%d %b %Y',      # 1 Apr 2026
            '%d %B %Y',      # 1 April 2026
            '%b %d, %Y',     # Apr 1, 2026
            '%Y/%m/%d',      # 2026/04/01
            '%m-%d-%Y',      # 04-01-2026
            '%m/%d/%Y',      # 04/01/2026
        ]

        for fmt in formats:
            try:
                datetime.strptime(date_str, fmt)
                return True
            except (ValueError, TypeError):
                continue

        # Check if it's just a number (day of month)
        if date_str.isdigit() and 1 <= int(date_str) <= 31:
            return True

        return False

    def _validate_numeric(self, value: Any) -> bool:
        """
        Validate that the value is numeric.
        """
        if value is None:
            return False

        # Check if it's already a number
        if isinstance(value, (int, float)):
            return True

        # Check if it's a string with numbers
        if isinstance(value, str):
            cleaned = re.sub(r'[^0-9.\-]', '', value.strip())
            if not cleaned:
                return False
            try:
                float(cleaned)
                return True
            except ValueError:
                return False

        return False

    def _validate_row(self, row: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a single row of data.
        Returns (is_valid, error_message).
        """
        # Check if row is empty
        if not row or len(row) == 0:
            return False, "Empty row"

        # Check for required columns
        for col in self.canonical_columns:
            if col not in row:
                return False, f"Missing required column: {col}"

        # Validate Day
        day_value = row.get('Day', '')
        if not day_value:
            return False, "Day is empty"
        if not self._validate_date_format(str(day_value)):
            return False, f"Invalid date format: {day_value}"

        # Validate Volume
        volume = row.get('Volume (In Mn.)', None)
        if volume is None or volume == "":
            return False, "Volume is empty"
        if not self._validate_numeric(volume):
            return False, f"Invalid numeric value for Volume: {volume}"

        # Validate Value
        value = row.get('Value (In Cr.)', None)
        if value is None or value == "":
            return False, "Value is empty"
        if not self._validate_numeric(value):
            return False, f"Invalid numeric value for Value: {value}"

        return True, ""

    def _check_duplicate_days(self, data: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Check for duplicate days in the data.
        Returns (has_duplicates, duplicate_days).
        """
        days = [row.get('Day', '') for row in data if row.get('Day')]
        seen = set()
        duplicates = []
        for day in days:
            if day in seen:
                duplicates.append(day)
            else:
                seen.add(day)

        return len(duplicates) > 0, list(set(duplicates))

    def validate(self, parsed_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Validate the parsed data.
        Returns validation results.
        """
        # Load parsed data if not provided
        if parsed_data is None:
            parsed_file = self._find_parsed_file()
            if parsed_file is None:
                raise FileNotFoundError("No parsed data file found")

            with open(parsed_file, 'r') as f:
                parsed_data = json.load(f)['rows']

        if not parsed_data:
            if self.allow_empty:
                return {'valid': True, 'message': 'Empty dataset allowed'}
            else:
                raise ValueError(f"Dataset is empty (min_rows={self.min_rows})")

        print(f"Validating {len(parsed_data)} rows")

        # Validation results
        results = {
            'total_rows': len(parsed_data),
            'valid_rows': 0,
            'invalid_rows': 0,
            'errors': [],
            'warnings': [],
            'duplicate_days': []
        }

        # 1. Validate columns
        missing_columns = self._validate_columns(parsed_data)
        if missing_columns:
            error_msg = f"Missing required columns: {', '.join(missing_columns)}"
            results['errors'].append(error_msg)
            raise ValueError(error_msg)

        # 2. Validate each row
        for i, row in enumerate(parsed_data):
            is_valid, error = self._validate_row(row)
            if is_valid:
                results['valid_rows'] += 1
            else:
                results['invalid_rows'] += 1
                results['errors'].append(f"Row {i+1}: {error}")

        # 3. Check minimum rows
        if results['valid_rows'] < self.min_rows:
            error_msg = f"Only {results['valid_rows']} valid rows (min: {self.min_rows})"
            results['errors'].append(error_msg)
            raise ValueError(error_msg)

        # 4. Check for duplicate days
        has_duplicates, duplicate_days = self._check_duplicate_days(parsed_data)
        if has_duplicates:
            results['warnings'].append(f"Duplicate days found: {', '.join(duplicate_days)}")
            results['duplicate_days'] = duplicate_days

        # 5. Check for completely empty rows
        empty_rows = [i for i, row in enumerate(parsed_data)
                     if not any(v for v in row.values() if v not in [None, "", 0, 0.0])]
        if empty_rows:
            results['warnings'].append(f"Empty rows found: {empty_rows}")

        # Determine overall validity
        results['valid'] = (results['invalid_rows'] == 0 and
                           len(results['errors']) == 0 and
                           results['total_rows'] >= self.min_rows)

        # Save validation report
        report_file = self.output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Validation results: {results['valid_rows']}/{results['total_rows']} rows valid")
        if results['warnings']:
            print(f"Warnings: {len(results['warnings'])}")
        if results['errors']:
            print(f"Errors: {len(results['errors'])}")
            for error in results['errors']:
                print(f"  - {error}")

        return results


if __name__ == "__main__":
    # For standalone testing
    config_path = Path(__file__).parent / 'config.yaml'
    validator = NPIValidator(str(config_path))

    try:
        results = validator.validate()
        if results['valid']:
            print("Validation passed!")
        else:
            print("Validation failed!")
    except Exception as e:
        print(f"Validation failed: {e}")
