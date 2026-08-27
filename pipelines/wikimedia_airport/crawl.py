#!/usr/bin/env python3
"""
Crawl module for Wikimedia Airport Data pipeline.
Fetches airport data from Wikidata SPARQL endpoint.
"""
import os
import json
import time
import yaml
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import quote


class WikidataCrawler:
    """Crawler for Wikidata SPARQL endpoint to fetch airport data."""

    def __init__(self, config_path: str):
        """Initialize crawler with configuration."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.endpoint = self.config['source']['endpoint']
        self.query = self.config['source']['query']
        self.raw_dir = Path(self.config['paths']['raw_dir'])
        self.metadata_dir = Path(self.config['paths']['metadata_dir'])

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # API settings
        self.timeout = self.config['api']['timeout']
        self.max_retries = self.config['api']['max_retries']
        self.retry_delay = self.config['api']['retry_delay']
        self.user_agent = self.config['api']['user_agent']

        # Headers
        self.headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }

    def _execute_sparql_query(self, query: str, retry_count: int = 0) -> Optional[Dict]:
        """
        Execute SPARQL query against Wikidata endpoint.
        Returns JSON response or None on failure.
        """
        # Prepare the query
        params = {
            'format': 'json',
            'query': query
        }

        print(f"Executing SPARQL query...")
        print(f"Query: {query[:200]}...")

        try:
            response = requests.get(
                self.endpoint,
                params=params,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            # Parse JSON
            data = response.json()
            return data

        except requests.exceptions.Timeout:
            print(f"Timeout error (attempt {retry_count + 1}/{self.max_retries})")
        except requests.exceptions.ConnectionError:
            print(f"Connection error (attempt {retry_count + 1}/{self.max_retries})")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error: {e} (attempt {retry_count + 1}/{self.max_retries})")
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        # Retry logic
        if retry_count < self.max_retries - 1:
            wait_time = self.retry_delay * (2 ** retry_count)
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            return self._execute_sparql_query(query, retry_count + 1)

        return None

    def _extract_airport_data(self, response: Dict) -> List[Dict[str, Any]]:
        """
        Extract airport data from Wikidata SPARQL response.
        """
        airports = []

        # Check if response has results
        if 'results' not in response:
            print("No 'results' field in response")
            return airports

        bindings = response['results'].get('bindings', [])
        print(f"Found {len(bindings)} airport entries")

        for i, binding in enumerate(bindings, 1):
            try:
                airport_data = {
                    'Sno.': i,
                    'Airport': self._get_value(binding, 'airportLabel'),
                    'City': self._get_value(binding, 'cityLabel'),
                    'Latitude': self._get_numeric_value(binding, 'lat'),
                    'Longitude': self._get_numeric_value(binding, 'lon')
                }

                # Only add if we have at least airport name and coordinates
                if airport_data['Airport'] and airport_data['Latitude'] is not None and airport_data['Longitude'] is not None:
                    airports.append(airport_data)
                else:
                    print(f"Skipping incomplete entry: {airport_data}")

            except Exception as e:
                print(f"Error processing binding {i}: {e}")
                continue

        return airports

    def _get_value(self, binding: Dict, key: str) -> str:
        """Extract string value from binding."""
        if key in binding:
            return binding[key].get('value', '').strip()
        return ''

    def _get_numeric_value(self, binding: Dict, key: str) -> Optional[float]:
        """Extract numeric value from binding."""
        if key in binding:
            value = binding[key].get('value', '')
            if value:
                try:
                    return float(value)
                except ValueError:
                    return None
        return None

    def crawl(self) -> Dict[str, Any]:
        """
        Main crawl method.
        Returns summary of crawl results.
        """
        print("=" * 60)
        print("WIKIMEDIA AIRPORT DATA EXTRACTION")
        print("=" * 60)

        # Execute query
        response = self._execute_sparql_query(self.query)

        if response is None:
            return {
                'success': False,
                'airports_found': 0,
                'message': 'Failed to fetch data from Wikidata'
            }

        # Save raw response
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        raw_file = self.raw_dir / f'wikidata_response_{timestamp}.json'
        with open(raw_file, 'w') as f:
            json.dump(response, f, indent=2)
        print(f"Saved raw response to: {raw_file}")

        # Extract airport data
        airports = self._extract_airport_data(response)

        if not airports:
            return {
                'success': False,
                'airports_found': 0,
                'message': 'No airport data extracted'
            }

        print(f"Extracted {len(airports)} airports")

        # Save processed data
        processed_file = self.metadata_dir / f'airports_{timestamp}.json'
        with open(processed_file, 'w') as f:
            json.dump({
                'airports': airports,
                'count': len(airports),
                'source': 'Wikidata SPARQL',
                'timestamp': datetime.now().isoformat(),
                'query': self.query
            }, f, indent=2)
        print(f"Saved processed data to: {processed_file}")

        return {
            'success': True,
            'airports_found': len(airports),
            'raw_file': str(raw_file),
            'processed_file': str(processed_file),
            'airports': airports
        }


def main():
    """Main entry point for crawling."""
    config_path = Path(__file__).parent / 'config.yaml'

    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    crawler = WikidataCrawler(str(config_path))
    results = crawler.crawl()

    if results.get('success'):
        print(f"\n✓ Successfully extracted {results['airports_found']} airports")
        return True
    else:
        print(f"\n✗ Crawl failed: {results.get('message', 'Unknown error')}")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
