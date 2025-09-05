"""
Anisa Yari blog scraper extension
Scrapes tech blog posts from Anisa Yari's personal blog
"""

import requests
import json
import re
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from datetime import datetime
from .base_scraper import BaseScraper


class AnisaYariScraper(BaseScraper):
    """Scraper for Anisa Yari tech blog"""
    
    BASE_URL = "https://www.anisayari.com"
    BLOG_URL = f"{BASE_URL}/blog"
    
    @property
    def name(self) -> str:
        return "anisayari"
    
    @property
    def category(self) -> str:
        return "Tech"
    
    @property
    def update_interval_hours(self) -> int:
        return 12  # Update every 12 hours for personal blog
    
    def scrape(self) -> Dict[str, Any]:
        """
        Scrape blog posts from Anisa Yari's blog
        
        Returns:
            Dict with success status, articles list, and potential error
        """
        try:
            # Get the blog page
            response = requests.get(self.BLOG_URL, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "articles": [],
                    "error": f"HTTP {response.status_code} when fetching {self.BLOG_URL}"
                }
            
            articles = []
            
            # Try to parse Next.js data from script tags or page content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Method 1: Look for JSON data in script tags
            articles_from_scripts = self._extract_from_scripts(soup)
            if articles_from_scripts:
                articles.extend(articles_from_scripts)
            
            # Method 2: Fallback to HTML parsing if script method fails
            if not articles:
                articles_from_html = self._extract_from_html(soup)
                articles.extend(articles_from_html)
            
            if self.logger:
                self.logger.info(f"Anisa Yari scraper found {len(articles)} articles", module_name="news")
            
            return {
                "success": True,
                "articles": articles,
                "error": None
            }
            
        except requests.RequestException as e:
            error_msg = f"Network error scraping Anisa Yari blog: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, module_name="news")
            return {
                "success": False,
                "articles": [],
                "error": error_msg
            }
        
        except Exception as e:
            error_msg = f"Error scraping Anisa Yari blog: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, module_name="news")
            return {
                "success": False,
                "articles": [],
                "error": error_msg
            }
    
    def _extract_from_scripts(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract blog data from Next.js script tags"""
        articles = []
        
        try:
            # Look for Next.js data in script tags
            script_tags = soup.find_all('script')
            
            for script in script_tags:
                if script.string and ('blog' in script.string.lower() or 'post' in script.string.lower()):
                    script_content = script.string
                    
                    # Try to find JSON-like structures containing blog data
                    json_matches = re.findall(r'\{[^{}]*"slug"[^{}]*\}', script_content)
                    
                    for match in json_matches:
                        try:
                            # Clean up the JSON string
                            cleaned_match = self._clean_json_string(match)
                            blog_data = json.loads(cleaned_match)
                            
                            # Extract article information
                            if self._is_valid_blog_post(blog_data):
                                article = self._convert_to_article(blog_data)
                                if article:
                                    articles.append(article)
                                    
                        except (json.JSONDecodeError, KeyError):
                            continue
                            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Could not extract from scripts: {str(e)}", module_name="news")
        
        return articles
    
    def _extract_from_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Fallback method to extract blog data from HTML elements"""
        articles = []
        
        try:
            # Look for blog post containers
            # Try common blog post selectors
            post_selectors = [
                'article',
                '[class*="post"]',
                '[class*="blog"]',
                '[class*="card"]',
                '.grid > div',
                '[href*="/blog/"]'
            ]
            
            for selector in post_selectors:
                elements = soup.select(selector)
                
                for element in elements:
                    # Look for links to blog posts
                    links = element.find_all('a', href=re.compile(r'/blog/[\w-]+'))
                    
                    for link in links:
                        href = link.get('href', '')
                        if href.startswith('/blog/') and len(href) > 6:  # More than just "/blog/"
                            
                            # Extract slug from URL
                            slug = href.replace('/blog/', '')
                            
                            # Try to find title
                            title = link.get_text(strip=True)
                            if not title:
                                # Look for title in nearby elements
                                title_elem = element.find(['h1', 'h2', 'h3', 'h4'])
                                title = title_elem.get_text(strip=True) if title_elem else f"Article: {slug}"
                            
                            # Use slug as unique ID
                            article = {
                                "id": slug,
                                "title": title,
                                "summary": f"Tech article from Anisa Yari's blog",
                                "url": f"{self.BASE_URL}{href}",
                                "date": None,  # No reliable date extraction from HTML
                                "author": "Anisa Yari"
                            }
                            
                            articles.append(article)
                
                # Break if we found articles
                if articles:
                    break
                    
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Could not extract from HTML: {str(e)}", module_name="news")
        
        return articles
    
    def _clean_json_string(self, json_str: str) -> str:
        """Clean and prepare JSON string for parsing"""
        # Remove JavaScript-specific syntax
        cleaned = json_str.replace("'", '"')  # Replace single quotes
        cleaned = re.sub(r'(\w+):', r'"\1":', cleaned)  # Quote unquoted keys
        cleaned = re.sub(r',\s*}', '}', cleaned)  # Remove trailing commas
        return cleaned
    
    def _is_valid_blog_post(self, data: Dict) -> bool:
        """Check if the data represents a valid blog post"""
        required_fields = ['slug', 'title']
        return all(field in data for field in required_fields)
    
    def _convert_to_article(self, blog_data: Dict) -> Dict[str, Any]:
        """Convert blog post data to article format"""
        try:
            slug = blog_data.get('slug', {})
            if isinstance(slug, dict):
                slug_current = slug.get('current', '')
            else:
                slug_current = str(slug)
            
            title = blog_data.get('title', f'Article: {slug_current}')
            
            # Try to parse date
            article_date = None
            published_at = blog_data.get('publishedAt')
            if published_at:
                try:
                    date_obj = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    article_date = date_obj.isoformat()
                except Exception:
                    pass
            
            return {
                "id": slug_current,
                "title": title,
                "summary": blog_data.get('excerpt', f"Tech article from Anisa Yari's blog"),
                "url": f"{self.BASE_URL}/blog/{slug_current}",
                "date": article_date,
                "author": "Anisa Yari"
            }
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Error converting blog data: {str(e)}", module_name="news")
            return None