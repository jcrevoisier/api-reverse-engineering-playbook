import json
import logging
import re
from typing import Dict, List, Any, Optional, Generator
from urllib.parse import urlencode, quote

import httpx
from bs4 import BeautifulSoup

from ..utils import get_random_user_agent, implement_rate_limiting

logger = logging.getLogger(__name__)

class IndeedJobSearchAPI:
    """
    A class to interact with Indeed's hidden job search API.
    """
    
    BASE_URL = "https://www.indeed.com"
    SEARCH_URL = "https://www.indeed.com/jobs"
    API_SEARCH_URL = "https://www.indeed.com/api/graphql"
    
    def __init__(self):
        """
        Initialize the Indeed Job Search API client.
        """
        self.headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.indeed.com/",
            "Content-Type": "application/json",
            "Origin": "https://www.indeed.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        
        self.client = httpx.Client(headers=self.headers, follow_redirects=True)
        self.csrf_token = None
        self.indeed_csrf_token = None
        self._initialize_session()
    
    def _initialize_session(self):
        """
        Initialize a session with Indeed to get necessary tokens.
        """
        try:
            # First, visit the homepage to get cookies
            response = self.client.get(self.BASE_URL)
            
            if response.status_code != 200:
                raise Exception(f"Failed to initialize session: {response.status_code}")
            
            # Extract CSRF token from the page
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_meta = soup.find('meta', attrs={'id': 'indeed-csrf-token'})
            
            if csrf_meta and 'content' in csrf_meta.attrs:
                self.csrf_token = csrf_meta['content']
                self.headers['Indeed-CSRF-Token'] = self.csrf_token
                logger.info(f"Obtained CSRF token: {self.csrf_token[:5]}...")
            else:
                logger.warning("Could not find CSRF token in the page")
            
            # Look for the GraphQL CSRF token in the page scripts
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string and 'window._initialData' in script.string:
                    match = re.search(r'"csrfToken":"([^"]+)"', script.string)
                    if match:
                        self.indeed_csrf_token = match.group(1)
                        logger.info(f"Obtained GraphQL CSRF token: {self.indeed_csrf_token[:5]}...")
                        break
            
        except Exception as e:
            logger.error(f"Error initializing session: {e}")
            raise
    
    def search(self, query: str, location: str, page: int = 0, limit: int = 10) -> Dict[str, Any]:
        """
        Search Indeed for jobs matching the query and location.
        
        Args:
            query: Job search query
            location: Location to search in
            page: Page number (0-based)
            limit: Number of results per page
            
        Returns:
            Dict containing search results
        """
        # First approach: Use the traditional search URL to get the initial results
        params = {
            'q': query,
            'l': location,
            'start': page * limit,
            'limit': limit
        }
        
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        
        implement_rate_limiting(2.0, 4.0)
        
        try:
            logger.info(f"Searching Indeed for: {query} in {location} (page {page})")
            response = self.client.get(url)
            
            if response.status_code != 200:
                raise Exception(f"Search failed: {response.status_code}")
            
            # Parse the HTML response to extract job listings
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract mosaic ID for GraphQL API
            mosaic_provider = soup.find('div', attrs={'id': 'mosaic-provider-jobcards'})
            mosaic_id = mosaic_provider['data-mosaic-id'] if mosaic_provider and 'data-mosaic-id' in mosaic_provider.attrs else None
            
            if not mosaic_id:
                logger.warning("Could not find mosaic ID, falling back to HTML parsing")
                return self._parse_html_results(soup)
            
            # Use the GraphQL API for better results
            return self._search_graphql(query, location, page, limit, mosaic_id)
            
        except Exception as e:
            logger.error(f"Error searching Indeed: {e}")
            raise
    
    def _search_graphql(self, query: str, location: str, page: int, limit: int, mosaic_id: str) -> Dict[str, Any]:
        """
        Search Indeed using the GraphQL API.
        
        Args:
            query: Job search query
            location: Location to search in
            page: Page number
            limit: Number of results per page
            mosaic_id: Mosaic ID from the HTML page
            
        Returns:
            Dict containing search results
        """
        if not self.indeed_csrf_token:
            raise Exception("GraphQL CSRF token not available")
        
        # GraphQL query for job search
        graphql_query = {
            "operationName": "JobSearchResults",
            "variables": {
                "searchParams": {
                    "keyword": query,
                    "location": location,
                    "page": page,
                    "pageSize": limit,
                    "sortBy": "relevance"
                },
                "mosaicProviderJobCardsKeyword": mosaic_id
            },
            "query": """
                query JobSearchResults($searchParams: JobSearchParams!, $mosaicProviderJobCardsKeyword: String!) {
                    jobSearch(params: $searchParams) {
                        results {
                            job {
                                key
                                title
                                company {
                                    name
                                    reviewCount
                                    rating
                                }
                                location {
                                    city
                                    state
                                    country
                                }
                                salarySnippet {
                                    text
                                }
                                jobTypes
                                description
                                url
                                postingDate
                            }
                        }
                        pageInfo {
                            totalResults
                            nextPageToken
                        }
                    }
                }
            """
        }
        
        headers = self.headers.copy()
        headers["Content-Type"] = "application/json"
        headers["Indeed-CSRF-Token"] = self.indeed_csrf_token
        
        implement_rate_limiting(2.0, 4.0)
        
        try:
            response = self.client.post(
                self.API_SEARCH_URL,
                json=graphql_query,
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"GraphQL search failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error in GraphQL search: {e}")
            raise
    
    def _parse_html_results(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Parse job listings from HTML when GraphQL API is not available.
        
        Args:
            soup: BeautifulSoup object of the search results page
            
        Returns:
            Dict containing parsed job listings
        """
        results = []
        
        job_cards = soup.find_all('div', class_='job_seen_beacon')
        
        for card in job_cards:
            try:
                # Extract job title and URL
                title_elem = card.find('h2', class_='jobTitle')
                title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
                
                job_link = title_elem.find('a') if title_elem else None
                job_url = f"{self.BASE_URL}{job_link['href']}" if job_link and 'href' in job_link.attrs else None
                job_id = job_link['data-jk'] if job_link and 'data-jk' in job_link.attrs else None
                
                # Extract company name
                company_elem = card.find('span', class_='companyName')
                company = company_elem.get_text(strip=True) if company_elem else "Unknown Company"
                
                # Extract location
                location_elem = card.find('div', class_='companyLocation')
                location = location_elem.get_text(strip=True) if location_elem else "Unknown Location"
                
                # Extract salary if available
                salary_elem = card.find('div', class_='salary-snippet')
                salary = salary_elem.get_text(strip=True) if salary_elem else None
                
                # Extract job snippet/description
                snippet_elem = card.find('div', class_='job-snippet')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else None
                
                # Extract posting date
                date_elem = card.find('span', class_='date')
                date = date_elem.get_text(strip=True) if date_elem else None
                
                results.append({
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary,
                    "description": snippet,
                    "url": job_url,
                    "date_posted": date
                })
                
            except Exception as e:
                logger.error(f"Error parsing job card: {e}")
                continue
        
        return {
            "results": results,
            "count": len(results)
        }
    
    def search_all(self, query: str, location: str, max_results: int = 100) -> Generator[Dict[str, Any], None, None]:
        """
        Search Indeed and paginate through all results up to max_results.
        
        Args:
            query: Job search query
            location: Location to search in
            max_results: Maximum number of results to return
            
        Yields:
            Job data dictionaries
        """
        results_count = 0
        page = 0
        page_size = 10
        
        logger.info(f"Searching Indeed for all results (max: {max_results}) with query: {query} in {location}")
        
        while results_count < max_results:
            batch_size = min(page_size, max_results - results_count)
            if batch_size <= 0:
                break
                
            response_data = self.search(query, location, page, batch_size)
            
            # Extract jobs from the response
            if "data" in response_data and "jobSearch" in response_data["data"]:
                # GraphQL response
                jobs = response_data["data"]["jobSearch"]["results"]
                has_next_page = response_data["data"]["jobSearch"]["pageInfo"]["nextPageToken"] is not None
            else:
                # HTML parsed response
                jobs = response_data.get("results", [])
                has_next_page = len(jobs) >= batch_size
            
            if not jobs:
                logger.info("No more jobs found")
                break
            
            # Yield each job
            for job in jobs:
                if "job" in job:  # GraphQL format
                    job_data = job["job"]
                    yield {
                        "id": job_data.get("key"),
                        "title": job_data.get("title"),
                        "company": job_data.get("company", {}).get("name"),
                        "location": self._format_location(job_data.get("location", {})),
                        "salary": job_data.get("salarySnippet", {}).get("text"),
                        "job_types": job_data.get("jobTypes", []),
                        "description": job_data.get("description"),
                        "url": f"{self.BASE_URL}/viewjob?jk={job_data.get('key')}",
                        "date_posted": job_data.get("postingDate")
                    }
                else:  # HTML parsed format
                    yield job
                
                results_count += 1
                if results_count >= max_results:
                    break
            
            if not has_next_page or results_count >= max_results:
                break
            
            page += 1
            implement_rate_limiting(3.0, 5.0)
    
    def _format_location(self, location: Dict[str, str]) -> str:
        """
        Format location dictionary into a string.
        
        Args:
            location: Location dictionary with city, state, country
            
        Returns:
            Formatted location string
        """
        parts = []
        if location.get("city"):
            parts.append(location["city"])
        if location.get("state"):
            parts.append(location["state"])
        if location.get("country") and not (location.get("city") or location.get("state")):
            parts.append(location["country"])
        
        return ", ".join(parts) if parts else "Remote"
