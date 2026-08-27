#!/usr/bin/env python3
"""
Validate module for Vaishno Devi Yatra Statistics pipeline.
Validates extracted data.
"""
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class VaishnoDeviValidator:
    """Validator for Vaishno Devi Yatra data."""

    def __init__(self, config_path: str):
        """Initialize validator with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.output_dir = Path(self.config['paths']['output_dir'])
        self.datasets_config = self.config['dataset']['datasets']
        self.validation_config = self.config['validation']

    def _find_latest_json_file(self, pattern: str) -> Optional[Path]:
        """Find the most recent JSON file matching pattern."""
        json_files = list(self.output_dir.glob(pattern))
        if not json_files:
            return None
        json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return json_files[0]

    def _validate_dataset(self, data: List[Dict], dataset_name: str) -> Dict[str, Any]:
        """
        Validate a single dataset.
        """
        results = {
            'dataset': dataset_name,
            'total_rows': len(data),
            'valid_rows': 0,
            'invalid_rows': 0,
            'errors': [],
            'warnings': []
        }

        if not data:
            results['valid'] = False
            results['message'] = "Dataset is empty"
            return results

        # Get required columns
        required_cols = self.validation_config.get('required_columns', {}).get(dataset_name, [])
        if not required_cols:
            results['warnings'].append("No required columns defined for this dataset")

        # Validate each row
        for i, row in enumerate(data):
            row_errors = []
            row_warnings = []

            # Check required columns
            for col in required_cols:
                if col not in row or not row[col]:
                    row_errors.append(f"Missing required column: {col}")

            # Additional validation based on dataset type
            if dataset_name == 'annual':
                # Check Year is 4 digits
                if 'Year' in row and row['Year']:
                    year = str(row['Year']).strip()
                    if not (len(year) == 4 and year.isdigit()):
                        row_warnings.append(f"Invalid year format: {year}")
                
                # Check numeric value
                if 'No_of_Yatries_In_Lakhs' in row and row['No_of_Yatries_In_Lakhs']:
                    try:
                        float(row['No_of_Yatries_In_Lakhs'])
                    except ValueError:
                        row_errors.append(f"Invalid number: {row['No_of_Yatries_In_Lakhs']}")

            elif dataset_name == 'monthly_1986_onwards':
                # Check Year is 4 digits
                if 'Year' in row and row['Year']:
                    year = str(row['Year']).strip()
                    if not (len(year) == 4 and year.isdigit()):
                        row_warnings.append(f"Invalid year format: {year}")
                
                # Check Total is numeric if present
                if 'Total' in row and row['Total']:
                    try:
                        float(row['Total'])
                    except ValueError:
                        row_errors.append(f"Invalid total: {row['Total']}")

            elif dataset_name == 'monthly_2024_2025':
                # Check Month is present
                if 'Month' not in row or not row['Month']:
                    row_errors.append("Missing month name")
                
                # Check numeric value
                if 'No_of_Yatries' in row and row['No_of_Yatries']:
                    try:
                        float(row['No_of_Yatries'])
                    except ValueError:
                        row_errors.append(f"Invalid number: {row['No_of_Yatries']}")

            if row_errors:
                results['invalid_rows'] += 1
                results['errors'].append({
                    'row_index': i,
                    'row': row,
                    'errors': row_errors,
                    'warnings': row_warnings
                })
            else:
                results['valid_rows'] += 1

            if row_warnings:
                results['warnings'].extend(row_warnings)

        # Check minimum rows
        min_rows = self.validation_config.get('min_rows', 1)
        if results['valid_rows'] < min_rows:
            results['valid'] = False
            results['message'] = f"Only {results['valid_rows']} valid rows (min: {min_rows})"
        else:
            results['valid'] = True
            results['message'] = f"All {results['valid_rows']} rows are valid"

        return results

    def validate(self) -> Dict[str, Any]:
        """
        Validate all datasets.
        Returns validation results.
        """
        print("Validating Vaishno Devi Yatra datasets...")
        print("=" * 50)

        all_results = {}
        overall_valid = True

        # Validate each dataset
        for dataset_name in self.datasets_config.keys():
            print(f"\nValidating {dataset_name}...")
            
            # Find the latest JSON file for this dataset
            json_pattern = f'{self.datasets_config[dataset_name]["name"]}_*.json'
            json_file = self._find_latest_json_file(json_pattern)
            
            if json_file is None:
                print(f"  ✗ No data file found for {dataset_name}")
                all_results[dataset_name] = {
                    'dataset': dataset_name,
                    'valid': False,
                    'message': 'No data file found'
                }
                overall_valid = False
                continue

            # Load data
            with open(json_file, 'r') as f:
                data = json.load(f)
                rows = data.get('data', [])

            # Validate
            results = self._validate_dataset(rows, dataset_name)
            all_results[dataset_name] = results

            if results['valid']:
                print(f"  ✓ Valid: {results['valid_rows']}/{results['total_rows']} rows")
            else:
                print(f"  ✗ Invalid: {results['message']}")
                overall_valid = False

            if results['warnings']:
                print(f"  ⚠ Warnings: {len(results['warnings'])}")

        # Save validation report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.output_dir / f'validation_report_{timestamp}.json'
        
        final_report = {
            'timestamp': datetime.now().isoformat(),
            'overall_valid': overall_valid,
            'datasets': all_results
        }
        
        with open(report_file, 'w') as f:
            json.dump(final_report, f, indent=2)

        print("\n" + "=" * 50)
        if overall_valid:
            print("✓ All datasets passed validation")
        else:
            print("✗ Some datasets failed validation")

        return final_report


if __name__ == "__main__":
    """Main entry point for validation."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        exit(1)

    validator = VaishnoDeviValidator(str(config_path))

    try:
        results = validator.validate()
        exit(0 if results['overall_valid'] else 1)
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        exit(1)
