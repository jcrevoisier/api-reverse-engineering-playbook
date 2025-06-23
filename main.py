import argparse
import json
import logging
import sys
from pathlib import Path

from src.twitter.twitter_api import TwitterSearchAPI
from src.indeed.indeed_api import IndeedJobSearchAPI
from src.yelp.yelp_api import YelpBusinessSearchAPI
from src.utils import save_to_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def twitter_search(args):
    """
    Perform a Twitter search and save the results.
    
    Args:
        args: Command line arguments
    """
    query = args.query
    max_results = args.max_results
    output_dir = args.output_dir
    
    logger.info(f"Performing Twitter search for: {query} (max results: {max_results})")
    
    api = TwitterSearchAPI()
    results = []
    
    try:
        for tweet in api.search_all(query, max_results):
            results.append(tweet)
            if len(results) % 10 == 0:
                logger.info(f"Retrieved {len(results)} tweets so far")
        
        logger.info(f"Retrieved a total of {len(results)} tweets")
        
        if output_dir:
            filename = f"twitter_search_{query.replace(' ', '_')}_{len(results)}.json"
            save_to_json(results, filename, output_dir)
            logger.info(f"Results saved to {output_dir}/{filename}")
        else:
            print(json.dumps(results, indent=2))
            
    except Exception as e:
        logger.error(f"Error in Twitter search: {e}")
        sys.exit(1)

def indeed_search(args):
    """
    Perform an Indeed job search and save the results.
    
    Args:
        args: Command line arguments
    """
    query = args.query
    location = args.location
    max_results = args.max_results
    output_dir = args.output_dir
    
    logger.info(f"Performing Indeed job search for: {query} in {location} (max results: {max_results})")
    
    api = IndeedJobSearchAPI()
    results = []
    
    try:
        for job in api.search_all(query, location, max_results):
            results.append(job)
            if len(results) % 10 == 0:
                logger.info(f"Retrieved {len(results)} jobs so far")
        
        logger.info(f"Retrieved a total of {len(results)} jobs")
        
        if output_dir:
            filename = f"indeed_search_{query.replace(' ', '_')}_{location.replace(' ', '_')}_{len(results)}.json"
            save_to_json(results, filename, output_dir)
            logger.info(f"Results saved to {output_dir}/{filename}")
        else:
            print(json.dumps(results, indent=2))
            
    except Exception as e:
        logger.error(f"Error in Indeed search: {e}")
        sys.exit(1)

def yelp_search(args):
    """
    Perform a Yelp business search and save the results.
    
    Args:
        args: Command line arguments
    """
    term = args.term
    location = args.location
    max_results = args.max_results
    output_dir = args.output_dir
    
    logger.info(f"Performing Yelp business search for: {term} in {location} (max results: {max_results})")
    
    api = YelpBusinessSearchAPI()
    results = []
    
    try:
        for business in api.search_all(term, location, max_results):
            results.append(business)
            if len(results) % 10 == 0:
                logger.info(f"Retrieved {len(results)} businesses so far")
        
        logger.info(f"Retrieved a total of {len(results)} businesses")
        
        if output_dir:
            filename = f"yelp_search_{term.replace(' ', '_')}_{location.replace(' ', '_')}_{len(results)}.json"
            save_to_json(results, filename, output_dir)
            logger.info(f"Results saved to {output_dir}/{filename}")
        else:
            print(json.dumps(results, indent=2))
            
    except Exception as e:
        logger.error(f"Error in Yelp search: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="API Reverse Engineering Playbook")
    subparsers = parser.add_subparsers(dest="command", help="API to use")
    
    # Twitter search parser
    twitter_parser = subparsers.add_parser("twitter", help="Search Twitter")
    twitter_parser.add_argument("query", help="Search query")
    twitter_parser.add_argument("--max-results", type=int, default=50, help="Maximum number of results to retrieve")
    twitter_parser.add_argument("--output-dir", help="Directory to save results to")
    
    # Indeed search parser
    indeed_parser = subparsers.add_parser("indeed", help="Search Indeed jobs")
    indeed_parser.add_argument("query", help="Job search query")
    indeed_parser.add_argument("location", help="Location to search in")
    indeed_parser.add_argument("--max-results", type=int, default=50, help="Maximum number of results to retrieve")
    indeed_parser.add_argument("--output-dir", help="Directory to save results to")
    
    # Yelp search parser
    yelp_parser = subparsers.add_parser("yelp", help="Search Yelp businesses")
    yelp_parser.add_argument("term", help="Business search term")
    yelp_parser.add_argument("location", help="Location to search in")
    yelp_parser.add_argument("--max-results", type=int, default=50, help="Maximum number of results to retrieve")
    yelp_parser.add_argument("--output-dir", help="Directory to save results to")
    
    args = parser.parse_args()
    
    if args.command == "twitter":
        twitter_search(args)
    elif args.command == "indeed":
        indeed_search(args)
    elif args.command == "yelp":
        yelp_search(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
