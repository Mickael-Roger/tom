"""
Base scraper interface for news scraping extensions
All news scrapers must inherit from this base class
"""

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional


class BaseScraper(ABC):
    """Abstract base class for news scrapers"""
    
    def __init__(self, db_path: str, logger=None):
        self.db = db_path
        self.logger = logger
        self.last_update = datetime.now()
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the scraper (e.g., 'kyutai', 'mistral')"""
        pass
    
    @property
    @abstractmethod
    def category(self) -> str:
        """Return the default category for news from this scraper (e.g., 'AI', 'Tech')"""
        pass
    
    @property
    @abstractmethod
    def update_interval_hours(self) -> int:
        """Return the minimum hours between updates to prevent blocking"""
        pass
    
    @abstractmethod
    def scrape(self) -> Dict[str, Any]:
        """
        Scrape news from the source
        
        Returns:
            Dict with format:
            {
                "success": bool,
                "articles": [
                    {
                        "id": str,           # Unique identifier for the article
                        "title": str,        # Article title
                        "summary": str,      # Article description/summary
                        "url": str,          # Article URL
                        "date": Optional[str], # Article date (ISO format)
                        "author": str        # Source/author name
                    }
                ],
                "error": Optional[str]
            }
        """
        pass
    
    def get_existing_ids(self) -> List[str]:
        """Get existing news IDs from database for this scraper"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT news_id FROM news WHERE source = ?", (self.name,))
            ids = cursor.fetchall()
            dbconn.close()
            return [str(news_id[0]) for news_id in ids]
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error getting existing IDs for {self.name}: {str(e)}", module_name="news")
            return []
    
    def save_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Save new articles to database
        
        Args:
            articles: List of article dictionaries from scrape() method
            
        Returns:
            Dict with saved/skipped counts
        """
        existing_ids = self.get_existing_ids()
        saved_count = 0
        skipped_count = 0
        
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            for article in articles:
                article_id = str(article['id'])
                
                if article_id not in existing_ids:
                    # Parse date if provided
                    article_date = None
                    if article.get('date'):
                        try:
                            date_obj = datetime.fromisoformat(article['date'].replace('Z', '+00:00'))
                            article_date = date_obj.strftime('%Y-%m-%d')
                        except:
                            pass
                    
                    cursor.execute(
                        "INSERT INTO news (source, category, news_id, author, title, summary, url, datetime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            self.name,
                            self.category,
                            article_id,
                            article['author'],
                            article['title'],
                            article['summary'],
                            article['url'],
                            article_date
                        )
                    )
                    saved_count += 1
                else:
                    skipped_count += 1
            
            dbconn.commit()
            dbconn.close()
            
            if self.logger:
                self.logger.info(f"Scraper {self.name}: saved {saved_count} new articles, skipped {skipped_count}", module_name="news")
            
            return {
                "success": True,
                "saved": saved_count,
                "skipped": skipped_count
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error saving articles for {self.name}: {str(e)}", module_name="news")
            return {
                "success": False,
                "error": str(e),
                "saved": 0,
                "skipped": 0
            }
    
    def should_update(self) -> bool:
        """Check if enough time has passed since last update"""
        from datetime import timedelta
        time_diff = datetime.now() - self.last_update
        return time_diff > timedelta(hours=self.update_interval_hours)
    
    def update(self) -> Dict[str, Any]:
        """
        Update news from this scraper if enough time has passed
        
        Returns:
            Dict with update results
        """
        if not self.should_update():
            return {
                "success": True,
                "skipped": True,
                "reason": f"Too early to update (min {self.update_interval_hours}h interval)"
            }
        
        try:
            scrape_result = self.scrape()
            
            if not scrape_result.get("success"):
                return {
                    "success": False,
                    "error": scrape_result.get("error", "Scraping failed")
                }
            
            save_result = self.save_articles(scrape_result.get("articles", []))
            self.last_update = datetime.now()
            
            return {
                "success": save_result["success"],
                "saved": save_result["saved"],
                "skipped": save_result["skipped"],
                "error": save_result.get("error")
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error updating {self.name}: {str(e)}", module_name="news")
            return {
                "success": False,
                "error": str(e)
            }