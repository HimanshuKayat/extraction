#!/usr/bin/env python3
"""
Validate module for Wikimedia Airport Data pipeline.
Validates airport data structure and coordinates.
"""
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


class WikimediaAirportValidator:
    """Validator for Wikimedia airport data."""

    def __init__(self, config_path: str):
        """Initialize validator with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.output_dir = Path(self.config['paths']['output_dir'])
        self.canonical_columns = self.config['dataset']['canonical_columns']
        self.required_columns = self.config['validation']['required_columns']
        self.min_rows = self.config['validation']['min_rows']
        self.lat_range = self.config['validation']['latitude_range']
        self.lon_range = self.config['validation']['longitude_range']

    def _find_latest_parsed_file(self) -> Optional[Path]:
        """Find the most recent parsed data file."""
        parsed_files = list(self.output_dir.glob('airports_parsed_*.json'))
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
                parsed_data = data.get('airports', [])

        if not parsed_data:
            if self.min_rows == 0:
                return {'valid': True, 'message': 'Empty dataset allowed'}
            else:
                raise ValueError(f"Dataset is empty (min_rows={self.min_rows})")

        print(f"Validating {len(parsed_data)} airports")

        # Validation results
        results = {
            'total_airports': len(parsed_data),
            'valid_airports': 0,
            'invalid_airports': 0,
            'errors': [],
            'warnings': []
        }

        # Validate each airport
        for i, airport in enumerate(parsed_data):
            errors = []
            warnings = []

            # Check required columns
            for col in self.required_columns:
                if col not in airport or airport[col] is None:
                    errors.append(f"Missing required column: {col}")

            # Validate Airport name
            if not airport.get('Airport', ''):
                errors.append("Airport name is empty")

            # Validate Latitude
            lat = airport.get('Latitude')
            if lat is None:
                errors.append("Latitude is empty")
            else:
                if not self._validate_coordinate(lat, self.lat_range):
                    errors.append(f"Invalid latitude: {lat} (range: {self.lat_range})")

            # Validate Longitude
            lon = airport.get('Longitude')
            if lon is None:
                errors.append("Longitude is empty")
            else:
                if not self._validate_coordinate(lon, self.lon_range):
                    errors.append(f"Invalid longitude: {lon} (range: {self.lon_range})")

            # Validate City (warning if missing)
            if not airport.get('City', ''):
                warnings.append("City is missing")

            # Determine validity
            is_valid = len(errors) == 0

            if is_valid:
                results['valid_airports'] += 1
            else:
                results['invalid_airports'] += 1
                results['errors'].append({
                    'airport_index': i,
                    'airport_name': airport.get('Airport', 'Unknown'),
                    'errors': errors,
                    'warnings': warnings
                })

            if warnings:
                results['warnings'].extend(warnings)

        # Check minimum rows
        if results['valid_airports'] < self.min_rows:
            results['valid'] = False
            results['message'] = f"Only {results['valid_airports']} valid airports (min: {self.min_rows})"
        else:
            results['valid'] = True
            results['message'] = f"All {results['valid_airports']} airports are valid"

        # Save validation report
        report_file = self.output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Validation results: {results['valid_airports']}/{results['total_airports']} airports valid")
        if results['warnings']:
            print(f"Warnings: {len(results['warnings'])}")
        if results['errors']:
            print(f"Errors: {len(results['errors'])}")
            for error in results['errors'][:3]:  # Show first 3 errors
                print(f"  - {error['airport_name']}: {', '.join(error['errors'][:2])}")

        return results

    def _validate_coordinate(self, coord: float, range_values: List[float]) -> bool:
        """Validate coordinate is within range."""
        if not isinstance(coord, (int, float)):
            return False
        return range_values[0] <= coord <= range_values[1]


def main():
    """Main entry point for validation."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    validator = WikimediaAirportValidator(str(config_path))

    try:
        results = validator.validate()
        if results['valid']:
            print(f"\n✓ Validation passed: {results['message']}")
            return True
        else:
            print(f"\n✗ Validation failed: {results['message']}")
            return False
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
