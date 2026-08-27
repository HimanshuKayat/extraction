#!/usr/bin/env python3
"""
Parse module for Daily UPI Transactions pipeline.
Reads raw API response and extracts structured data.
"""
import os
import json
import yaml
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class NPIParser:
    """Parser for NPCI API responses."""

    def __init__(self, config_path: str):
        """Initialize parser with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.canonical_columns = self.config['dataset']['canonical_columns']
        self.api_params = self.config['source']['api_params']

    def _find_latest_raw_file(self) -> Optional[Path]:
        """Find the most recent raw API response file."""
        raw_files = list(self.raw_dir.glob('api_response_*.json'))
        if not raw_files:
            return None
        # Sort by modification time (newest first)
        raw_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return raw_files[0]

    def _clean_numeric_string(self, value: Any) -> Optional[float]:
        """
        Clean numeric string containing commas, currency symbols, etc.
        Returns float or None if not a valid number.
        """
        if value is None:
            return None

        # Convert to string if not already
        if not isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        # Remove common formatting characters
        cleaned = re.sub(r'[^0-9.\-]', '', value.strip())

        # Handle empty strings
        if not cleaned:
            return None

        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_date_value(self, value: Any) -> str:
        """
        Parse date/day value from API response.
        Returns string representation of the day.
        """
        if value is None:
            return ""

        # If it's a string, clean it
        if isinstance(value, str):
            # Handle common formats: "2026-04-01", "1 Apr 2026", etc.
            value = value.strip()
            # Try to standardize date format
            # Simple case: already in YYYY-MM-DD format
            if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                return value
            # Try to parse and reformat
            try:
                # For dates like "01-04-2026" or "1 Apr 2026"
                date_str = value
                # Handle "DD MMM YYYY" format
                months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                         'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
                for i, month in enumerate(months, 1):
                    if month in date_str.lower():
                        # Extract day and year
                        parts = date_str.replace(',', '').split()
                        day = parts[0].zfill(2)
                        year = parts[-1]
                        return f"{year}-{str(i).zfill(2)}-{day}"
            except:
                pass
            return value

        # If it's a number, treat as timestamp or day number
        if isinstance(value, (int, float)):
            # Check if it's a timestamp
            if value > 1000000000:  # Likely a timestamp
                import datetime
                dt = datetime.datetime.fromtimestamp(value / 1000)
                return dt.strftime('%Y-%m-%d')
            else:
                return str(value)

        return str(value)

    def _extract_headers(self, response_data: Dict[str, Any]) -> Tuple[List[str], Dict[str, str]]:
        """
        Extract table headers from API response.
        Returns (list of header names, mapping of header_key to header_name).
        """
        data = response_data.get('data', {})
        table_headers = data.get('table_headers', {})

        # Try to get headers from the response
        headers = table_headers.get('headers', [])

        if not headers:
            # Try alternative location
            if 'headers' in data:
                headers = data['headers']
            elif 'columns' in data:
                headers = data['columns']
            else:
                # Try to infer from results
                results = data.get('results', [])
                if results and isinstance(results[0], dict):
                    headers = [{'header_name': k.replace('_', ' ').title(),
                              'header_key': k} for k in results[0].keys()]
                else:
                    raise ValueError("Could not find headers in API response")

        header_names = []
        header_map = {}

        for header in headers:
            if isinstance(header, dict):
                name = header.get('header_name', '')
                key = header.get('header_key', '')
                if name:
                    header_names.append(name)
                    header_map[key] = name
            elif isinstance(header, str):
                header_names.append(header)
                # For string headers, use the string itself as both name and key
                sanitized_key = header.lower().replace(' ', '_').replace('(', '').replace(')', '')
                header_map[sanitized_key] = header

        return header_names, header_map

    def _extract_results(self, response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract results from API response."""
        data = response_data.get('data', {})
        results = data.get('results', [])

        if not results:
            # Try alternative locations
            if 'rows' in data:
                results = data['rows']
            elif 'data' in data and isinstance(data['data'], list):
                results = data['data']
            else:
                # Check if the data itself is a list
                if isinstance(data, list):
                    results = data

        return results

    def _map_to_canonical(self, row: Dict[str, Any],
                          header_map: Dict[str, str]) -> Dict[str, Any]:
        """
        Map API row to canonical columns.
        """
        result = {}
        found_day = False
        found_volume = False
        found_value = False

        for key, value in row.items():
            # Try to match to canonical columns
            header_name = header_map.get(key, key)

            # Determine which canonical column this maps to
            if 'day' in key.lower() or 'date' in key.lower() or 'month' in key.lower():
                result['Day'] = self._parse_date_value(value)
                found_day = True
            elif 'volume' in key.lower() and ('mn' in key.lower() or 'million' in key.lower()):
                result['Volume (In Mn.)'] = self._clean_numeric_string(value)
                found_volume = True
            elif 'value' in key.lower() and ('cr' in key.lower() or 'crore' in key.lower()):
                result['Value (In Cr.)'] = self._clean_numeric_string(value)
                found_value = True
            elif 'amount' in key.lower() or 'transaction' in key.lower():
                # Try to infer if it's value
                if not found_value and (isinstance(value, (int, float)) or
                                       (isinstance(value, str) and re.search(r'\d', value))):
                    result['Value (In Cr.)'] = self._clean_numeric_string(value)
                    found_value = True

        # If we couldn't map some fields, include them as extra columns
        if not found_day or not found_volume or not found_value:
            # Add all original fields for debugging
            for key, value in row.items():
                if key not in result:
                    # Try to add as extra field
                    result[f"_{key}"] = value

        return result

    def parse(self, raw_file: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], Path]:
        """
        Parse the raw API response.
        Returns (parsed data, output file path).
        """
        # Find raw file if not specified
        if raw_file is None:
            raw_file = self._find_latest_raw_file()

        if raw_file is None:
            raise FileNotFoundError("No raw API response files found")

        print(f"Parsing raw file: {raw_file}")

        # Read and parse JSON
        with open(raw_file, 'r') as f:
            response_data = json.load(f)

        # Check for success status
        status = response_data.get('status')
        if status != 200:
            raise ValueError(f"API response status is not 200: {status}")

        # Get the actual data
        data = response_data.get('data', {})
        if not data:
            raise ValueError("No data found in API response")

        # Extract headers
        header_names, header_map = self._extract_headers(response_data)

        # Extract results
        results = self._extract_results(response_data)

        if not results:
            raise ValueError("No results found in API response")

        print(f"Found {len(results)} rows with {len(header_names)} columns")
        print(f"Headers: {header_names}")

        # Map to canonical format
        parsed_data = []
        for row in results:
            if not isinstance(row, dict):
                continue
            canonical_row = self._map_to_canonical(row, header_map)
            parsed_data.append(canonical_row)

        # Save parsed data
        output_file = self.output_dir / f"parsed_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                'headers': header_names,
                'header_map': header_map,
                'rows': parsed_data,
                'count': len(parsed_data),
                'source': str(raw_file)
            }, f, indent=2)

        print(f"Parsed {len(parsed_data)} rows")
        print(f"Saved parsed data to: {output_file}")

        return parsed_data, output_file


if __name__ == "__main__":
    # For standalone testing
    import asyncio
    from datetime import datetime

    config_path = Path(__file__).parent / 'config.yaml'
    parser = NPIParser(str(config_path))

    try:
        parsed_data, output_file = parser.parse()
        print(f"Successfully parsed {len(parsed_data)} rows")
    except Exception as e:
        print(f"Parsing failed: {e}")
