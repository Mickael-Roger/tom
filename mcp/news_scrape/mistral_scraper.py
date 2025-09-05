"""
Mistral AI news scraper extension
Scrapes news from Mistral AI CMS API
"""

import requests
from datetime import datetime
from typing import Dict, Any, List
from .base_scraper import BaseScraper


class MistralScraper(BaseScraper):
    """Scraper for Mistral AI news"""
    
    CMS_URL = "https://cms.mistral.ai/items/posts?fields=*,translations.*,category.*,parent.id&sort=-date&limit=10&page=1"
    BASE_URL = "https://mistral.ai"
    
    @property
    def name(self) -> str:
        return "mistral"
    
    @property
    def category(self) -> str:
        return "AI"
    
    @property
    def update_interval_hours(self) -> int:
        return 6  # Update every 6 hours to prevent blocking
    
    def scrape(self) -> Dict[str, Any]:
        """
        Scrape news from Mistral AI CMS
        
        Returns:
            Dict with success status, articles list, and potential error
        """
        try:
            response = requests.get(self.CMS_URL, timeout=30)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "articles": [],
                    "error": f"HTTP {response.status_code} when fetching Mistral CMS"
                }
            
            data = response.json()
            articles = []
            
            # Process articles from CMS data
            for item in data.get('data', []):
                item_id = item.get('id')
                date = item.get('date')
                slug = item.get('slug')
                
                if not all([item_id, date, slug]):
                    continue
                
                # Find English translation
                title_en = None
                description_en = None
                
                for translation in item.get('translations', []):
                    if translation.get('languages_code') == 'en':
                        title_en = translation.get('title')
                        description_en = translation.get('description')
                        break
                
                if not title_en:
                    continue  # Skip if no English translation
                
                # Format date
                article_date = None
                try:
                    date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                    article_date = date_obj.isoformat()
                except Exception:
                    pass  # Use None if date parsing fails
                
                # Build article URL
                article_url = f"{self.BASE_URL}/en/news/{slug}"
                
                article = {
                    "id": str(item_id),
                    "title": title_en,
                    "summary": description_en or "",
                    "url": article_url,
                    "date": article_date,
                    "author": "mistral"
                }
                
                articles.append(article)
            
            if self.logger:
                self.logger.info(f"Mistral scraper found {len(articles)} articles", module_name="news")
            
            return {
                "success": True,
                "articles": articles,
                "error": None
            }
            
        except requests.RequestException as e:
            error_msg = f"Network error scraping Mistral: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, module_name="news")
            return {
                "success": False,
                "articles": [],
                "error": error_msg
            }
        
        except Exception as e:
            error_msg = f"Error scraping Mistral news: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, module_name="news")
            return {
                "success": False,
                "articles": [],
                "error": error_msg
            }