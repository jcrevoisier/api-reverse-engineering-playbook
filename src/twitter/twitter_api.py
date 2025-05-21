import json
import logging
from typing import Dict, List, Any, Optional, Generator
import urllib.parse

import httpx

from ..utils import get_random_user_agent, implement_rate_limiting

logger = logging.getLogger(__name__)

class TwitterSearchAPI:
    """
    A class to interact with Twitter's hidden search API.
    
    This implementation is based on reverse engineering the API used by
    Twitter's web interface when performing searches.
    """
    
    BASE_URL = "https://twitter.com/i/api/graphql"
    SEARCH_ENDPOINT = "7s4lUZO6Cgy-BdpXmK_MUQ/SearchTimeline"
    
    def __init__(self, guest_token: Optional[str] = None):
        """
        Initialize the Twitter Search API client.
        
        Args:
            guest_token: Optional guest token for authentication
        """
        self.headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://twitter.com/search",
            "Content-Type": "application/json",
            "X-Twitter-Client-Language": "en",
            "X-Twitter-Active-User": "yes",
            "Origin": "https://twitter.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        
        self.client = httpx.Client(headers=self.headers, follow_redirects=True)
        
        if guest_token:
            self.headers["X-Guest-Token"] = guest_token
        else:
            self._obtain_guest_token()
    
    def _obtain_guest_token(self) -> None:
        """
        Obtain a guest token from Twitter's API.
        """
        try:
            response = self.client.post(
                "https://api.twitter.com/1.1/guest/activate.json",
                headers={"Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"}
            )
            
            if response.status_code == 200:
                data = response.json()
                guest_token = data.get("guest_token")
                self.headers["X-Guest-Token"] = guest_token
                logger.info(f"Obtained guest token: {guest_token[:5]}...")
            else:
                raise Exception(f"Failed to obtain guest token: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error obtaining guest token: {e}")
            raise
    
    def search(self, query: str, count: int = 20, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Search Twitter for the given query.
        
        Args:
            query: Search query
            count: Number of results to return
            cursor: Pagination cursor
            
        Returns:
            Dict containing search results
        """
        variables = {
            "rawQuery": query,
            "count": count,
            "querySource": "typed_query",
            "product": "Top"
        }
        
        if cursor:
            variables["cursor"] = cursor
        
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_enhance_cards_enabled": False
        }
        
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features)
        }
        
        url = f"{self.BASE_URL}/{self.SEARCH_ENDPOINT}"
        
        implement_rate_limiting(2.0, 5.0)  # Be respectful with rate limits
        
        try:
            logger.info(f"Searching Twitter for: {query}")
            response = self.client.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Search failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error searching Twitter: {e}")
            raise
    
    def search_all(self, query: str, max_results: int = 100) -> Generator[Dict[str, Any], None, None]:
        """
        Search Twitter and paginate through all results up to max_results.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Yields:
            Tweet data dictionaries
        """
        results_count = 0
        cursor = None
        
        logger.info(f"Searching Twitter for all results (max: {max_results}) with query: {query}")
        
        while results_count < max_results:
            batch_size = min(20, max_results - results_count)
            if batch_size <= 0:
                break
                
            response_data = self.search(query, count=batch_size, cursor=cursor)
            
            # Extract tweets from the response
            instructions = response_data.get("data", {}).get("search_by_raw_query", {}).get("search_timeline", {}).get("timeline", {}).get("instructions", [])
            
            entries = []
            for instruction in instructions:
                if instruction.get("type") == "TimelineAddEntries":
                    entries.extend(instruction.get("entries", []))
            
            # Find the next cursor
            cursor = None
            for entry in entries:
                if entry.get("content", {}).get("entryType") == "TimelineTimelineCursor" and entry.get("content", {}).get("cursorType") == "Bottom":
                    cursor = entry.get("content", {}).get("value")
                    break
            
            # Extract and yield tweets
            tweets_in_batch = 0
            for entry in entries:
                content = entry.get("content", {})
                if content.get("entryType") == "TimelineTimelineItem" and "tweet_results" in content.get("itemContent", {}):
                    tweet_data = content.get("itemContent", {}).get("tweet_results", {}).get("result", {})
                    if tweet_data:
                        results_count += 1
                        tweets_in_batch += 1
                        yield self.extract_tweet_data(tweet_data)
            
            logger.info(f"Retrieved {tweets_in_batch} tweets in this batch, total: {results_count}/{max_results}")
            
            if not cursor or results_count >= max_results:
                break
            
            # Be respectful with rate limits
            implement_rate_limiting(3.0, 6.0)
    
    def extract_tweet_data(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant data from a tweet object.
        
        Args:
            tweet: Raw tweet data from the API
            
        Returns:
            Dict containing cleaned tweet data
        """
        legacy = tweet.get("legacy", {})
        user = tweet.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
        
        return {
            "id": tweet.get("rest_id"),
            "created_at": legacy.get("created_at"),
            "text": legacy.get("full_text"),
            "retweet_count": legacy.get("retweet_count"),
            "favorite_count": legacy.get("favorite_count"),
            "reply_count": legacy.get("reply_count"),
            "quote_count": legacy.get("quote_count"),
            "user": {
                "id": user.get("id_str"),
                "name": user.get("name"),
                "screen_name": user.get("screen_name"),
                "followers_count": user.get("followers_count"),
                "friends_count": user.get("friends_count"),
                "verified": user.get("verified", False)
            },
            "hashtags": [h.get("text") for h in legacy.get("entities", {}).get("hashtags", [])],
            "urls": [u.get("expanded_url") for u in legacy.get("entities", {}).get("urls", [])],
            "mentions": [
                {
                    "screen_name": m.get("screen_name"),
                    "name": m.get("name"),
                    "id": m.get("id_str")
                } 
                for m in legacy.get("entities", {}).get("user_mentions", [])
            ],
            "media": [
                {
                    "type": m.get("type"),
                    "url": m.get("media_url_https"),
                    "alt_text": m.get("ext_alt_text")
                }
                for m in legacy.get("entities", {}).get("media", [])
            ] if "media" in legacy.get("entities", {}) else []
        }