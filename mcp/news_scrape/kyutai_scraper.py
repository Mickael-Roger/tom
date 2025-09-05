"""
Kyutai news scraper extension
Scrapes news from Kyutai AI research lab blog
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from .base_scraper import BaseScraper


class KyutaiScraper(BaseScraper):
    """Scraper for Kyutai AI research lab news"""
    
    BASE_URL = "https://kyutai.org"
    BLOG_URL = f"{BASE_URL}/blog.html"
    
    @property
    def name(self) -> str:
        return "kyutai"
    
    @property
    def category(self) -> str:
        return "AI"
    
    @property
    def update_interval_hours(self) -> int:
        return 6  # Update every 6 hours to prevent blocking
    
    def scrape(self) -> Dict[str, Any]:
        """
        Scrape news from Kyutai blog
        
        Returns:
            Dict with success status, articles list, and potential error
        """
        try:
            response = requests.get(self.BLOG_URL, timeout=30)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "articles": [],
                    "error": f"HTTP {response.status_code} when fetching {self.BLOG_URL}"
                }
            
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = []
            
            # Parse articles from h1 tags with links
            for h1 in soup.find_all('h1'):
                a_tag = h1.find('a')
                if a_tag:
                    item_url = a_tag['href']
                    item_title = a_tag.get_text(strip=True)
                    
                    # Get description from next sibling div with class 'post-text'
                    post_text_div = h1.find_next_sibling('div', class_='post-text')
                    item_description = ""
                    if post_text_div and post_text_div.p:
                        item_description = post_text_div.p.get_text(strip=True)
                    
                    # Use the relative URL as unique ID
                    article_id = item_url
                    full_url = f"{self.BASE_URL}/{item_url}"
                    
                    article = {
                        "id": article_id,
                        "title": item_title,
                        "summary": item_description,
                        "url": full_url,
                        "date": None,  # Kyutai doesn't provide structured dates
                        "author": "kyutai"
                    }
                    
                    articles.append(article)
            
            if self.logger:
                self.logger.info(f"Kyutai scraper found {len(articles)} articles", module_name="news")
            
            return {
                "success": True,
                "articles": articles,
                "error": None
            }
            
        except requests.RequestException as e:
            error_msg = f"Network error scraping Kyutai: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, module_name="news")
            return {
                "success": False,
                "articles": [],
                "error": error_msg
            }
        
        except Exception as e:
            error_msg = f"Error scraping Kyutai news: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, module_name="news")
            return {
                "success": False,
                "articles": [],
                "error": error_msg
            }