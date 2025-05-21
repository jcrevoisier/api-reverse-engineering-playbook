import json
import logging
import re
from typing import Dict, List, Any, Optional, Generator
from urllib.parse import urlencode, quote

import httpx
from bs4 import BeautifulSoup

from ..utils import get_random_user_agent, implement_rate_limiting

logger = logging.getLogger(__name__)

class YelpBusinessSearchAPI:
    """
    A class to interact with Yelp's hidden business search API.
    
    This implementation is based on reverse engineering the API used by
    Yelp's web interface when performing business searches.
    """
    
    BASE_URL = "https://www.yelp.com"
    SEARCH_URL = "https://www.yelp.com/search"
    GRAPHQL_URL = "https://www.yelp.com/gql"
    
    def __init__(self):
        """
        Initialize the Yelp Business Search API client.
        """
        self.headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.yelp.com/",
            "Content-Type": "application/json",
            "Origin": "https://www.yelp.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        
        self.client = httpx.Client(headers=self.headers, follow_redirects=True)
        self.csrf_token = None
        self._initialize_session()
    
    def _initialize_session(self):
        """
        Initialize a session with Yelp to get necessary tokens.
        """
        try:
            # First, visit the homepage to get cookies and CSRF token
            response = self.client.get(self.BASE_URL)
            
            if response.status_code != 200:
                raise Exception(f"Failed to initialize session: {response.status_code}")
            
            # Extract CSRF token from the page
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the CSRF token in the page scripts
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string and 'yelp.www.init.csrf' in script.string:
                    match = re.search(r'csrf: "([^"]+)"', script.string)
                    if match:
                        self.csrf_token = match.group(1)
                        logger.info(f"Obtained CSRF token: {self.csrf_token[:5]}...")
                        self.headers['X-CSRF-Token'] = self.csrf_token
                        break
            
            if not self.csrf_token:
                logger.warning("Could not find CSRF token in the page")
            
        except Exception as e:
            logger.error(f"Error initializing session: {e}")
            raise
    
    def search(self, term: str, location: str, offset: int = 0, limit: int = 10) -> Dict[str, Any]:
        """
        Search Yelp for businesses matching the term and location.
        
        Args:
            term: Business search term
            location: Location to search in
            offset: Offset for pagination
            limit: Number of results per page
            
        Returns:
            Dict containing search results
        """
        # First approach: Use the traditional search URL to get the initial results
        params = {
            'find_desc': term,
            'find_loc': location,
            'start': offset
        }
        
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        
        implement_rate_limiting(2.0, 4.0)
        
        try:
            logger.info(f"Searching Yelp for: {term} in {location} (offset {offset})")
            response = self.client.get(url)
            
            if response.status_code != 200:
                raise Exception(f"Search failed: {response.status_code}")
            
            # Try to extract the GraphQL data from the page
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the initial state data in the page scripts
            script_tags = soup.find_all('script')
            initial_data = None
            
            for script in script_tags:
                if script.string and 'window.__INITIAL_STATE__ = ' in script.string:
                    match = re.search(r'window\.__INITIAL_STATE__ = (.+?);\s*window\.__INITIAL_PROPS__', script.string, re.DOTALL)
                    if match:
                        try:
                            initial_data = json.loads(match.group(1))
                            break
                        except json.JSONDecodeError:
                            continue
            
            if initial_data and 'searchPageProps' in initial_data:
                # Extract business data from the initial state
                return self._extract_from_initial_state(initial_data)
            else:
                # Fall back to HTML parsing
                logger.warning("Could not find initial state data, falling back to HTML parsing")
                return self._parse_html_results(soup)
            
        except Exception as e:
            logger.error(f"Error searching Yelp: {e}")
            raise
    
    def _extract_from_initial_state(self, initial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract business data from the initial state object.
        
        Args:
            initial_data: Initial state data from the page
            
        Returns:
            Dict containing business data
        """
        search_page_props = initial_data.get('searchPageProps', {})
        search_results = search_page_props.get('searchResultsProps', {})
        search_response = search_results.get('searchResponse', {})
        
        businesses = []
        
        for business in search_response.get('searchResults', []):
            if business.get('type') != 'business':
                continue
                
            business_data = business.get('business', {})
            
            businesses.append({
                "id": business_data.get('id'),
                "name": business_data.get('name'),
                "url": f"{self.BASE_URL}{business_data.get('businessUrl')}",
                "image_url": business_data.get('photoPageUrl'),
                "review_count": business_data.get('reviewCount'),
                "rating": business_data.get('rating'),
                "price": business_data.get('priceRange'),
                "categories": [
                    {"title": cat.get('title'), "alias": cat.get('alias')}
                    for cat in business_data.get('categories', [])
                ],
                "location": {
                    "address1": business_data.get('formattedAddress'),
                    "city": business_data.get('neighborhoods', [None])[0],
                    "state": None,  # Not directly available in this data
                    "zip_code": None,  # Not directly available in this data
                    "display_address": business_data.get('formattedAddress')
                },
                "phone": business_data.get('phone'),
                "distance": business_data.get('distance')
            })
        
        return {
            "businesses": businesses,
            "total": search_response.get('totalResults', len(businesses)),
            "region": {
                "center": {
                    "latitude": search_page_props.get('mapState', {}).get('center', {}).get('latitude'),
                    "longitude": search_page_props.get('mapState', {}).get('center', {}).get('longitude')
                }
            }
        }
    
    def _parse_html_results(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Parse business listings from HTML when initial state data is not available.
        
        Args:
            soup: BeautifulSoup object of the search results page
            
        Returns:
            Dict containing parsed business listings
        """
        businesses = []
        
        business_cards = soup.find_all('div', class_='businessName__09f24__EYSZE')
        
        for card in business_cards:
            try:
                # Find the parent container
                container = card.find_parent('div', class_='container__09f24__mpR8_')
                if not container:
                    continue
                
                # Extract business name and URL
                name_elem = card.find('a')
                name = name_elem.get_text(strip=True) if name_elem else "Unknown Business"
                url = f"{self.BASE_URL}{name_elem['href']}" if name_elem and 'href' in name_elem.attrs else None
                
                # Extract business ID from URL
                business_id = None
                if url:
                    id_match = re.search(r'/biz/([^?]+)', url)
                    if id_match:
                        business_id = id_match.group(1)
                
                # Extract rating
                rating_elem = container.find('div', class_='five-stars')
                rating = None
                if rating_elem and 'aria-label' in rating_elem.attrs:
                    rating_text = rating_elem['aria-label']
                    rating_match = re.search(r'([\d.]+) star rating', rating_text)
                    if rating_match:
                        rating = float(rating_match.group(1))
                
                # Extract review count
                review_count_elem = container.find('span', string=re.compile(r'\d+ reviews?'))
                review_count = None
                if review_count_elem:
                    count_match = re.search(r'(\d+) reviews?', review_count_elem.get_text())
                    if count_match:
                        review_count = int(count_match.group(1))
                
                # Extract price range
                price_elem = container.find('span', string=re.compile(r'^\$+$'))
                price = price_elem.get_text() if price_elem else None
                
                # Extract categories
                categories = []
                category_elems = container.find_all('a', class_='categoryLink')
                for cat_elem in category_elems:
                    categories.append({
                        "title": cat_elem.get_text(strip=True),
                        "alias": cat_elem['href'].split('/')[-1] if 'href' in cat_elem.attrs else None
                    })
                
                # Extract address
                address_elem = container.find('address')
                address = address_elem.get_text(strip=True) if address_elem else None
                
                businesses.append({
                    "id": business_id,
                    "name": name,
                    "url": url,
                    "image_url": None,  # Not easily extractable from HTML
                    "review_count": review_count,
                    "rating": rating,
                    "price": price,
                    "categories": categories,
                    "location": {
                        "display_address": address
                    },
                    "phone": None  # Not easily extractable from HTML
                })
                
            except Exception as e:
                logger.error(f"Error parsing business card: {e}")
                continue
        
        return {
            "businesses": businesses,
            "total": len(businesses),
            "region": {
                "center": {
                    "latitude": None,
                    "longitude": None
                }
            }
        }
    
    def search_graphql(self, term: str, location: str, offset: int = 0, limit: int = 10) -> Dict[str, Any]:
        """
        Search Yelp using the GraphQL API.
        
        Args:
            term: Business search term
            location: Location to search in
            offset: Offset for pagination
            limit: Number of results per page
            
        Returns:
            Dict containing search results
        """
        if not self.csrf_token:
            raise Exception("CSRF token not available")
        
        # GraphQL query for business search
        graphql_query = {
            "operationName": "SearchPage",
            "variables": {
                "term": term,
                "location": location,
                "offset": offset,
                "limit": limit,
                "sortBy": "best_match"
            },
            "query": """
                query SearchPage($term: String!, $location: String!, $offset: Int!, $limit: Int!, $sortBy: String!) {
                    search(term: $term, location: $location, offset: $offset, limit: $limit, sortBy: $sortBy) {
                        total
                        business {
                            id
                            name
                            url
                            photos
                            rating
                            review_count
                            price
                            categories {
                                title
                                alias
                            }
                            location {
                                address1
                                city
                                state
                                postal_code
                                formatted_address
                            }
                            phone
                            distance
                        }
                        region {
                            center {
                                latitude
                                longitude
                            }
                        }
                    }
                }
            """
        }
        
        headers = self.headers.copy()
        headers["X-CSRF-Token"] = self.csrf_token
        
        implement_rate_limiting(2.0, 4.0)
        
        try:
            response = self.client.post(
                self.GRAPHQL_URL,
                json=graphql_query,
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"GraphQL search failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error in GraphQL search: {e}")
            # Fall back to regular search
            logger.info("Falling back to regular search")
            return self.search(term, location, offset, limit)
    
    def search_all(self, term: str, location: str, max_results: int = 100) -> Generator[Dict[str, Any], None, None]:
        """
        Search Yelp and paginate through all results up to max_results.
        
        Args:
            term: Business search term
            location: Location to search in
            max_results: Maximum number of results to return
            
        Yields:
            Business data dictionaries
        """
        results_count = 0
        offset = 0
        page_size = 10
        
        logger.info(f"Searching Yelp for all results (max: {max_results}) with term: {term} in {location}")
        
        while results_count < max_results:
            batch_size = min(page_size, max_results - results_count)
            if batch_size <= 0:
                break
                
            try:
                # Try GraphQL first
                response_data = self.search_graphql(term, location, offset, batch_size)
                businesses = response_data.get("data", {}).get("search", {}).get("business", [])
                total = response_data.get("data", {}).get("search", {}).get("total", 0)
            except Exception:
                # Fall back to regular search
                response_data = self.search(term, location, offset, batch_size)
                businesses = response_data.get("businesses", [])
                total = response_data.get("total", 0)
            
            if not businesses:
                logger.info("No more businesses found")
                break
            
            # Yield each business
            for business in businesses:
                yield business
                results_count += 1
                if results_count >= max_results:
                    break
            
            if results_count >= total or results_count >= max_results:
                break
            
            offset += batch_size
            implement_rate_limiting(3.0, 5.0)
