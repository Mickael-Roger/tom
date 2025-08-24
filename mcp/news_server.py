#!/usr/bin/env python3
"""
News MCP Server
Provides news management functionality via MCP protocol
Based on the original tomnews.py module
"""

import json
import os
import sys
import yaml
import functools
import threading
import time
import requests
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 News MCP Server starting with log level: {log_level}", module_name="news")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for any question about the news. It provides access to RSS feeds and web-scraped news from various sources, with the ability to read, summarize, and manage news articles."

# Initialize FastMCP server
server = FastMCP(name="news-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file using TOM_USER environment variable"""
    tom_user = os.environ.get('TOM_USER', 'unknown')
    config_path = f'/data/{tom_user}/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration for user '{tom_user}' from {config_path}", module_name="news")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="news")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="news")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class NewsService:
    """News service class based on original TomNews"""
    
    def __init__(self, config: Dict[str, Any]):
        # Load news configuration from config
        news_config = config.get('news', {})
        
        # Validate required config fields
        required_fields = ['url', 'user', 'password']
        for field in required_fields:
            if field not in news_config:
                raise KeyError(f"Missing required news config field: {field}")
        
        self.config = news_config
        self.url = news_config['url']
        self.username = news_config['user']
        self.password = news_config['password']
        
        # Set up database path
        tom_user = os.environ.get('TOM_USER', 'unknown')
        self.db = f'/data/{tom_user}/news.sqlite'
        
        self.lastUpdate = datetime.now() - timedelta(hours=48)
        self.background_status = {"ts": int(time.time()), "status": None}
        
        # Initialize database
        self._init_database()
        
        # Start background update thread
        self.thread = threading.Thread(target=self._thread_update)
        self.thread.daemon = True
        self.thread.start()
        
        if tomlogger:
            tomlogger.info(f"✅ News service initialized successfully", module_name="news")
    
    def _init_database(self):
        """Initialize the SQLite database"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute('''
            create table if not exists news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime DATETIME default current_date,
                source TEXT,
                category TEXT,
                news_id INTEGER,
                author TEXT,
                read BOOLEAN DEFAULT 0,
                to_read BOOLEAN DEFAULT 0,
                title TEXT,
                summary TEXT,
                url TEXT
            )
            ''')
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info(f"✅ News database initialized at {self.db}", module_name="news")
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing news database: {str(e)}", module_name="news")
            raise
    
    def api_call(self, path: str, method: str, args: Optional[Dict] = None) -> Optional[Dict]:
        """Make API call to RSS server"""
        url = self.url + path
        
        try:
            if method == 'get':
                response = requests.get(url, auth=HTTPBasicAuth(self.username, self.password), params=args)
                if response.status_code == 200:
                    return response.json()
                else:
                    if tomlogger:
                        tomlogger.error(f"API call failed with status {response.status_code}", module_name="news")
                    return None
            elif method == 'post':
                response = requests.post(url, auth=HTTPBasicAuth(self.username, self.password), data=args)
                if response.status_code == 200:
                    return response.json()
                else:
                    if tomlogger:
                        tomlogger.error(f"API call failed with status {response.status_code}", module_name="news")
                    return None
            else:
                if tomlogger:
                    tomlogger.error(f"Unknown method: {method}", module_name="news")
                return None
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"API call error: {str(e)}", module_name="news")
            return None
    
    def make_summary(self, news_id: str) -> Optional[str]:
        """Generate summary for a news article using LLM"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT source, news_id, url FROM news WHERE id = ?", (news_id,))
            news = cursor.fetchone()
            dbconn.close()
            
            if not news:
                return None
                
            content = ""
            
            # If it's RSS feed, get content from API
            if news[0] == 'rss':
                news_id_int = int(news[1]) + 1
                val = self.api_call(path='/items', method='get', args={"batchSize": 1, "offset": news_id_int})
                if val:
                    content = val['items'][0]['body']
            
            # Otherwise, try to get URL content
            if content == '':
                try:
                    res = requests.get(news[2], timeout=30)
                    if res.status_code == 200:
                        content = res.text
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error fetching URL content: {str(e)}", module_name="news")
                    return None
            
            if content == '':
                return None
                
            # Extract text content
            soup = BeautifulSoup(content, 'html.parser')
            content_text = soup.get_text(separator=' ', strip=True)
            
            # For now, return a simple truncated version as summary
            # In a real implementation, this would call an LLM
            summary = content_text[:500] + "..." if len(content_text) > 500 else content_text
            
            if tomlogger:
                tomlogger.debug(f"Generated summary for news {news_id}", module_name="news")
            
            return summary
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error making summary for news {news_id}: {str(e)}", module_name="news")
            return None
    
    def get_all_news(self) -> str:
        """Get all unread news articles organized by category"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT id, category, author, title, url FROM news WHERE read = 0")
            allnews = cursor.fetchall()
            dbconn.close()
            
            unread_news = {"category": {}}
            
            for news in allnews:
                news_id = news[0]
                category = news[1]
                author = news[2]
                title = news[3]
                url = news[4]
                
                if category not in unread_news['category'].keys():
                    unread_news['category'][category] = []
                
                unread_news['category'][category].append({
                    "news_id": news_id,
                    "author": author,
                    "title": title,
                    "url": url
                })
            
            if unread_news['category']:
                if tomlogger:
                    total_news = sum(len(articles) for articles in unread_news['category'].values())
                    tomlogger.info(f"Retrieved {total_news} unread news articles", module_name="news")
                return json.dumps(unread_news, ensure_ascii=False)
            else:
                return json.dumps({"status": "success", "message": "No unread news"}, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error getting all news: {str(e)}", module_name="news")
            return json.dumps({"error": f"Failed to get news: {str(e)}"}, ensure_ascii=False)
    
    def get_news_summary(self, news_id: str) -> str:
        """Get summary of a specific news article"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT title, summary, url FROM news WHERE id = ?", (news_id,))
            news = cursor.fetchone()
            dbconn.close()
            
            if not news:
                return json.dumps({"error": "News article not found"}, ensure_ascii=False)
            
            title, summary, url = news
            
            # If no summary exists, generate one
            if not summary:
                summary = self.make_summary(news_id)
                
                if summary:
                    # Update database with generated summary
                    dbconn = sqlite3.connect(self.db)
                    cursor = dbconn.cursor()
                    cursor.execute("UPDATE news SET summary=? WHERE id = ?", (summary, news_id))
                    dbconn.commit()
                    dbconn.close()
                else:
                    return json.dumps({"error": "Could not generate summary"}, ensure_ascii=False)
            
            result = {
                "news_id": news_id,
                "title": title,
                "summary": summary,
                "url": url
            }
            
            if tomlogger:
                tomlogger.info(f"Retrieved summary for news {news_id}", module_name="news")
                
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error getting news summary for {news_id}: {str(e)}", module_name="news")
            return json.dumps({"error": f"Failed to get summary: {str(e)}"}, ensure_ascii=False)
    
    def mark_news_as_read(self, news_id: str) -> str:
        """Mark a news article as read"""
        try:
            # Get news details
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT news_id, source FROM news WHERE id = ?", (news_id,))
            news = cursor.fetchone()
            dbconn.close()
            
            if not news:
                return json.dumps({"error": "News article not found"}, ensure_ascii=False)
            
            # Mark as read in local database
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("UPDATE news SET read=1 WHERE id = ?", (news_id,))
            dbconn.commit()
            dbconn.close()
            
            # If it's RSS, also mark as read on server
            if news[1] == 'rss':
                result = self.api_call(path=f"/items/{news[0]}/read", method='post')
                if not result:
                    if tomlogger:
                        tomlogger.warning(f"Could not mark RSS item {news[0]} as read on server", module_name="news")
            
            if tomlogger:
                tomlogger.info(f"Marked news {news_id} as read", module_name="news")
                
            return json.dumps({"status": "success", "message": "News marked as read"}, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error marking news {news_id} as read: {str(e)}", module_name="news")
            return json.dumps({"error": f"Failed to mark as read: {str(e)}"}, ensure_ascii=False)
    
    def mark_news_to_read(self, news_id: str) -> str:
        """Mark a news article to be read later"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("UPDATE news SET to_read=1 WHERE id = ?", (news_id,))
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info(f"Marked news {news_id} to read later", module_name="news")
                
            return json.dumps({"status": "success", "message": "News marked to read later"}, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error marking news {news_id} to read: {str(e)}", module_name="news")
            return json.dumps({"error": f"Failed to mark to read: {str(e)}"}, ensure_ascii=False)
    
    def _thread_update(self):
        """Background thread to update news"""
        self._news_update()
        while True:
            try:
                if tomlogger:
                    tomlogger.info("Updating news...", module_name="news")
                self._news_update()
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Failed to update news: {str(e)}", module_name="news")
            
            time.sleep(300)  # Update every 5 minutes
    
    def _news_update(self):
        """Update news from various sources"""
        try:
            self._update_rss_news()
            self._update_web_news()
            self._update_background_status()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error during news update: {str(e)}", module_name="news")
    
    def _update_rss_news(self):
        """Update RSS news"""
        try:
            # Get existing RSS IDs from database
            rss_ids = {}
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT news_id, read FROM news WHERE source = 'rss'")
            ids = cursor.fetchall()
            dbconn.close()
            
            for news_id, read in ids:
                rss_ids[news_id] = read
            
            # Get folders and feeds
            folders = {}
            res = self.api_call(path='/folders', method='get')
            if res:
                for folder in res['folders']:
                    folders[folder['id']] = folder['name']
            
            feeds = {}
            res = self.api_call(path='/feeds', method='get')
            if res:
                for feed in res['feeds']:
                    feeds[feed['id']] = {
                        "source": feed['title'],
                        "category": folders.get(feed['folderId'], 'Uncategorized')
                    }
            
            # Get unread news
            val = self.api_call(path='/items', method='get', args={"type": 3, "id": 0})
            if val:
                for item in val['items']:
                    if item['id'] not in rss_ids:
                        # New news, insert into database
                        feed_info = feeds.get(item['feedId'], {"source": "Unknown", "category": "Uncategorized"})
                        dbconn = sqlite3.connect(self.db)
                        cursor = dbconn.cursor()
                        cursor.execute(
                            "INSERT INTO news (source, category, news_id, author, title, url) VALUES ('rss', ?, ?, ?, ?, ?)",
                            (feed_info['category'], item['id'], feed_info['source'], item['title'], item['url'])
                        )
                        dbconn.commit()
                        dbconn.close()
                    else:
                        # Update read status if changed
                        read = not item['unread']
                        if rss_ids[item['id']] != read:
                            dbconn = sqlite3.connect(self.db)
                            cursor = dbconn.cursor()
                            cursor.execute("UPDATE news SET read=? WHERE source = 'rss' AND news_id=?", (read, item['id']))
                            dbconn.commit()
                            dbconn.close()
                            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating RSS news: {str(e)}", module_name="news")
    
    def _update_web_news(self):
        """Update web-scraped news (Kyutai, Mistral)"""
        time_diff = datetime.now() - self.lastUpdate
        
        # Only scrape every 6 hours to prevent blocking
        if time_diff > timedelta(hours=6):
            self._scrape_kyutai_news()
            self._scrape_mistral_news()
            self.lastUpdate = datetime.now()
    
    def _scrape_kyutai_news(self):
        """Scrape Kyutai blog for news"""
        try:
            kyutai_url = "https://kyutai.org/blog.html"
            response = requests.get(kyutai_url, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Get existing Kyutai news IDs
                kyutai_news_ids = []
                dbconn = sqlite3.connect(self.db)
                cursor = dbconn.cursor()
                cursor.execute("SELECT news_id FROM news WHERE source = 'kyutai'")
                ids = cursor.fetchall()
                dbconn.close()
                
                for news_id in ids:
                    kyutai_news_ids.append(news_id[0])
                
                # Parse new articles
                for h1 in soup.find_all('h1'):
                    a_tag = h1.find('a')
                    if a_tag:
                        item_url = a_tag['href']
                        item_title = a_tag.get_text(strip=True)
                        
                        post_text_div = h1.find_next_sibling('div', class_='post-text')
                        item_description = post_text_div.p.get_text(strip=True) if post_text_div and post_text_div.p else ""
                        
                        if item_url not in kyutai_news_ids:
                            dbconn = sqlite3.connect(self.db)
                            cursor = dbconn.cursor()
                            cursor.execute(
                                "INSERT INTO news (source, category, news_id, author, title, summary, url) VALUES ('kyutai', 'AI', ?, 'kyutai', ?, ?, ?)",
                                (item_url, item_title, item_description, f"https://kyutai.org/{item_url}")
                            )
                            dbconn.commit()
                            dbconn.close()
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error scraping Kyutai news: {str(e)}", module_name="news")
    
    def _scrape_mistral_news(self):
        """Scrape Mistral news"""
        try:
            mistral_url = 'https://cms.mistral.ai/items/posts?fields=*,translations.*,category.*,parent.id&sort=-date&limit=10&page=1'
            response = requests.get(mistral_url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Get existing Mistral news IDs
                mistral_news_ids = []
                dbconn = sqlite3.connect(self.db)
                cursor = dbconn.cursor()
                cursor.execute("SELECT news_id FROM news WHERE source = 'mistral'")
                ids = cursor.fetchall()
                dbconn.close()
                
                for news_id in ids:
                    mistral_news_ids.append(news_id[0])
                
                # Process new articles
                for item in data['data']:
                    item_id = item['id']
                    date = item['date']
                    slug = item['slug']
                    
                    for news_lang in item['translations']:
                        if news_lang['languages_code'] == 'en':
                            title_en = news_lang['title']
                            description_en = news_lang['description']
                            
                            if item_id not in mistral_news_ids:
                                dbconn = sqlite3.connect(self.db)
                                cursor = dbconn.cursor()
                                
                                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                                news_date = date_obj.strftime('%Y-%m-%d')
                                
                                cursor.execute(
                                    "INSERT INTO news (source, category, news_id, author, title, summary, url, datetime) VALUES ('mistral', 'AI', ?, 'mistral', ?, ?, ?, ?)",
                                    (item_id, title_en, description_en, f"https://mistral.ai/en/news/{slug}", news_date)
                                )
                                dbconn.commit()
                                dbconn.close()
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error scraping Mistral news: {str(e)}", module_name="news")
    
    def _update_background_status(self):
        """Update background status with unread count"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT count(news_id) FROM news WHERE read=0")
            val = cursor.fetchall()
            dbconn.close()
            
            unread = val[0][0]
            if int(unread) > 0:
                status = f"{unread} news"
            else:
                status = None
            
            if status != self.background_status['status']:
                self.background_status['ts'] = int(time.time())
                self.background_status['status'] = status
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating background status: {str(e)}", module_name="news")


# Load configuration and initialize news service
config = load_config()
news_service = NewsService(config)


@server.tool()
def get_all_news() -> str:
    """Retrieves a list of all unread news articles, organized by category. This function returns the news_id, the news title, author and category."""
    if tomlogger:
        tomlogger.info("Tool call: get_all_news", module_name="news")
    
    return news_service.get_all_news()


@server.tool()
def get_news_summary(news_id: str) -> str:
    """Get the summary of a news article. This function must only be used when the user asks for a summary of a particular article.
    
    Args:
        news_id: ID of the news you want to have a summary. The 'news_id' value can be retrieved from 'get_all_news' function.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_news_summary with news_id={news_id}", module_name="news")
    
    return news_service.get_news_summary(news_id)


@server.tool()
def mark_news_as_read(news_id: str) -> str:
    """Marks a specific news article as read.
    
    Args:
        news_id: ID of the news you want to mark as read.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: mark_news_as_read with news_id={news_id}", module_name="news")
    
    return news_service.mark_news_as_read(news_id)


@server.tool()
def mark_news_to_read(news_id: str) -> str:
    """Mark a news to read it later.
    
    Args:
        news_id: ID of the news you want to keep to read.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: mark_news_to_read with news_id={news_id}", module_name="news")
    
    return news_service.mark_news_to_read(news_id)


@server.resource("description://news")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting News MCP Server on port 80", module_name="news")
    else:
        print("Starting News MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()