import json
import random
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from fake_useragent import UserAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_har_file(file_path: str) -> Dict[str, Any]:
    """
    Load and parse a HAR file.
    
    Args:
        file_path: Path to the HAR file
        
    Returns:
        Dict containing the parsed HAR data
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading HAR file: {e}")
        raise


def extract_api_calls(har_data: Dict[str, Any], url_pattern: str) -> List[Dict[str, Any]]:
    """
    Extract API calls matching a specific pattern from HAR data.
    
    Args:
        har_data: Parsed HAR data
        url_pattern: String pattern to match in URLs
        
    Returns:
        List of matching API calls
    """
    matching_calls = []
    
    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        
        if url_pattern in url:
            matching_calls.append({
                'url': url,
                'method': request.get('method'),
                'headers': {h.get('name'): h.get('value') for h in request.get('headers', [])},
                'query_params': {p.get('name'): p.get('value') for p in request.get('queryString', [])},
                'post_data': request.get('postData', {}),
                'response': entry.get('response', {})
            })
    
    return matching_calls


def get_random_user_agent() -> str:
    """
    Generate a random user agent string.
    
    Returns:
        Random user agent string
    """
    ua = UserAgent()
    return ua.random


def implement_rate_limiting(min_delay: float = 1.0, max_delay: float = 3.0) -> None:
    """
    Implement a simple rate limiting delay.
    
    Args:
        min_delay: Minimum delay in seconds
        max_delay: Maximum delay in seconds
    """
    delay = random.uniform(min_delay, max_delay)
    logger.debug(f"Rate limiting: sleeping for {delay:.2f} seconds")
    time.sleep(delay)


def save_to_json(data: Any, filename: str, directory: Optional[str] = None) -> str:
    """
    Save data to a JSON file.
    
    Args:
        data: Data to save
        filename: Name of the file
        directory: Directory to save to (optional)
        
    Returns:
        Path to the saved file
    """
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / filename
    else:
        file_path = Path(filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Data saved to {file_path}")
    return str(file_path)


def extract_cookies_from_har(har_data: Dict[str, Any], domain: str) -> Dict[str, str]:
    """
    Extract cookies for a specific domain from HAR data.
    
    Args:
        har_data: Parsed HAR data
        domain: Domain to extract cookies for
        
    Returns:
        Dict of cookie name-value pairs
    """
    cookies = {}
    
    for entry in har_data.get('log', {}).get('entries', []):
        request_url = entry.get('request', {}).get('url', '')
        
        if domain in request_url:
            for cookie in entry.get('request', {}).get('cookies', []):
                name = cookie.get('name')
                value = cookie.get('value')
                if name and value:
                    cookies[name] = value
    
    return cookies
