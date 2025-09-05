#!/usr/bin/env python3
"""
GPodder MCP Server
Provides podcast management functionality via MCP protocol
Based on the original tomgpodder.py module
"""

import json
import os
import sys
import yaml
import threading
import time
import sqlite3
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional, List
from mygpoclient.api import MygPodderClient

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
    tomlogger.info(f"🚀 GPodder MCP Server starting with log level: {log_level}", module_name="gpodder")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for managing podcast subscriptions using gpodder.net service. It provides access to podcast subscriptions, unheard episodes, and synchronization with gpodder.net. Note: This service only handles podcasts (audio content), not music streaming or music files."

# Initialize FastMCP server
server = FastMCP(name="gpodder-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file using TOM_USER environment variable"""
    tom_user = os.environ.get('TOM_USER', 'unknown')
    config_path = f'/data/{tom_user}/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration for user '{tom_user}' from {config_path}", module_name="gpodder")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="gpodder")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="gpodder")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class GPodderService:
    """GPodder service class based on original TomGPodder"""
    
    def __init__(self, config: Dict[str, Any]):
        # Load gpodder configuration from config
        gpodder_config = config.get('gpodder', {})
        
        # Validate required config fields
        required_fields = ['username', 'password']
        for field in required_fields:
            if field not in gpodder_config:
                raise KeyError(f"Missing required gpodder config field: {field}")
        
        # Store credentials
        self.gpodder_username = gpodder_config['username']
        self.gpodder_password = gpodder_config['password']
        
        # Set up database path
        tom_user = os.environ.get('TOM_USER', 'unknown')
        self.db = f'/data/{tom_user}/gpodder.sqlite'
        
        self.device_id = "tom"
        self.background_status = {"ts": int(time.time()), "status": None}
        
        # Initialize database
        self._init_database()
        
        # Initialize GPodder client
        if self.gpodder_username and self.gpodder_password:
            self.client = MygPodderClient(self.gpodder_username, self.gpodder_password)
            self._create_device()
        else:
            self.client = None
            if tomlogger:
                tomlogger.warning("GPodder credentials not configured", module_name="gpodder")
        
        # Start background sync thread
        if self.client:
            self.sync_thread = threading.Thread(target=self._background_sync)
            self.sync_thread.daemon = True
            self.sync_thread.start()
        
        if tomlogger:
            tomlogger.info(f"✅ GPodder service initialized successfully", module_name="gpodder")
    
    def _init_database(self):
        """Initialize the SQLite database with required tables."""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Create subscriptions table with ID, title, and URL columns
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE
            )
            ''')
            
            # Create episodes table with subscription relationship
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                publication_date TEXT,
                url TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'unplayed',
                FOREIGN KEY (subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE
            )
            ''')
            
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info(f"✅ GPodder database initialized at {self.db}", module_name="gpodder")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing GPodder database: {str(e)}", module_name="gpodder")
            raise

    def _create_device(self):
        """Create the 'tom' device on GPodder.net if it doesn't exist."""
        if not self.client:
            return
            
        try:
            self.client.create_device(self.device_id, "desktop", "Tom Assistant")
            if tomlogger:
                tomlogger.info(f"Created device '{self.device_id}' on GPodder.net", module_name="gpodder")
        except Exception as e:
            if tomlogger:
                tomlogger.debug(f"Device '{self.device_id}' already exists or error creating: {e}", module_name="gpodder")

    def _background_sync(self):
        """Background thread to sync subscriptions and episodes every 60 minutes."""
        while True:
            try:
                if tomlogger:
                    tomlogger.info("Starting background sync of GPodder data...", module_name="gpodder")
                # First sync subscriptions, then episodes, then episode status sequentially
                self._sync_subscriptions()
                self._sync_episodes()
                self._sync_episode_status()
                self._cleanup_old_episodes()
                self._update_background_status()
                if tomlogger:
                    tomlogger.info("Background sync completed successfully", module_name="gpodder")
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Error in background sync: {e}", module_name="gpodder")
            
            # Wait 15 minutes (900 seconds)
            time.sleep(900)

    def _sync_subscriptions(self):
        """Synchronize subscriptions from GPodder.net to local database."""
        if not self.client:
            return
            
        try:
            # Get subscriptions from GPodder.net
            subscriptions = self.client.get_subscriptions(self.device_id)
            if tomlogger:
                tomlogger.info(f"Retrieved {len(subscriptions)} subscriptions from GPodder.net", module_name="gpodder")
            
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Get current subscriptions from database
            cursor.execute("SELECT url FROM subscriptions")
            db_subscriptions = {row[0] for row in cursor.fetchall()}
            
            # Convert GPodder subscriptions to set
            gpodder_subscriptions = set(subscriptions)
            
            # Add new subscriptions
            new_subscriptions = gpodder_subscriptions - db_subscriptions
            for sub_url in new_subscriptions:
                try:
                    title = self._extract_podcast_title(sub_url)
                    cursor.execute('''
                        INSERT INTO subscriptions (title, url) 
                        VALUES (?, ?)
                    ''', (title, sub_url))
                    if tomlogger:
                        tomlogger.info(f"Added new subscription: {title}", module_name="gpodder")
                    
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error adding subscription {sub_url}: {e}", module_name="gpodder")
                    continue
            
            # Remove deleted subscriptions
            deleted_subscriptions = db_subscriptions - gpodder_subscriptions
            for sub_url in deleted_subscriptions:
                try:
                    cursor.execute("SELECT title FROM subscriptions WHERE url = ?", (sub_url,))
                    result = cursor.fetchone()
                    title = result[0] if result else "Unknown"
                    
                    cursor.execute("DELETE FROM subscriptions WHERE url = ?", (sub_url,))
                    if tomlogger:
                        tomlogger.info(f"Removed deleted subscription: {title}", module_name="gpodder")
                    
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error removing subscription {sub_url}: {e}", module_name="gpodder")
                    continue
            
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info(f"Subscriptions synchronized: {len(new_subscriptions)} added, {len(deleted_subscriptions)} removed", module_name="gpodder")
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error syncing subscriptions from GPodder.net: {e}", module_name="gpodder")

    def _extract_podcast_title(self, sub_url):
        """Extract the real podcast title from RSS feed."""
        try:
            response = requests.get(sub_url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            # Extract podcast title from RSS feed
            podcast_title = root.findtext('./channel/title')
            if podcast_title:
                return podcast_title.strip()
            else:
                return sub_url.split('/')[-1] if '/' in sub_url else sub_url
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error extracting title from RSS feed {sub_url}: {e}", module_name="gpodder")
            # Fallback to URL-based title
            return sub_url.split('/')[-1] if '/' in sub_url else sub_url

    def _sync_episodes(self):
        """Synchronize episodes from RSS feeds to local database."""
        if not self.client:
            return
            
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Get all subscriptions
            cursor.execute("SELECT id, url FROM subscriptions")
            subscriptions = cursor.fetchall()
            
            for subscription_id, sub_url in subscriptions:
                try:
                    if tomlogger:
                        tomlogger.debug(f"Syncing episodes for subscription {subscription_id}: {sub_url}", module_name="gpodder")
                    
                    # Get RSS feed
                    response = requests.get(sub_url)
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                    
                    # Parse all episodes from RSS feed
                    for item in root.findall('./channel/item'):
                        try:
                            # Extract episode data
                            episode_title = item.findtext('title')
                            episode_url = item.find('enclosure').get('url') if item.find('enclosure') is not None else item.findtext('link')
                            
                            if not episode_title or not episode_url:
                                continue
                            
                            # Extract additional episode data
                            description = item.findtext('description', '')
                            pub_date_str = item.findtext('pubDate', '')
                            
                            # Parse publication date
                            publication_date = None
                            if pub_date_str:
                                try:
                                    # Try parsing RFC 2822 format (common in RSS)
                                    publication_date = parsedate_to_datetime(pub_date_str).isoformat()
                                except:
                                    # Fallback: store raw date string
                                    publication_date = pub_date_str
                            
                            # Check if episode already exists
                            cursor.execute("""
                                SELECT id FROM episodes 
                                WHERE subscription_id = ? AND url = ?
                            """, (subscription_id, episode_url))
                            
                            if not cursor.fetchone():
                                # Check if episode is not too old (>5 months) before adding
                                should_add = True
                                if publication_date:
                                    try:
                                        episode_date = parsedate_to_datetime(pub_date_str) if pub_date_str else None
                                        if episode_date:
                                            five_months_ago = datetime.now(episode_date.tzinfo) - timedelta(days=150)
                                            if episode_date < five_months_ago:
                                                should_add = False
                                                if tomlogger:
                                                    tomlogger.debug(f"Skipping old episode (>5 months): {episode_title}", module_name="gpodder")
                                    except:
                                        # If date parsing fails, add the episode anyway
                                        pass
                                
                                if should_add:
                                    # Insert new episode
                                    cursor.execute("""
                                        INSERT INTO episodes (subscription_id, title, publication_date, url, description)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (subscription_id, episode_title, publication_date, episode_url, description))
                                    
                                    if tomlogger:
                                        tomlogger.debug(f"Added new episode: {episode_title}", module_name="gpodder")
                            
                        except Exception as e:
                            if tomlogger:
                                tomlogger.error(f"Error processing episode in {sub_url}: {e}", module_name="gpodder")
                            continue
                    
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error syncing episodes for subscription {sub_url}: {e}", module_name="gpodder")
                    continue
            
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info("Episodes synchronization completed", module_name="gpodder")
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error syncing episodes: {e}", module_name="gpodder")

    def _sync_episode_status(self):
        """Synchronize episode play status based on GPodder episode actions."""
        if not self.client:
            return
            
        try:
            # Calculate timestamp for 24 hours ago
            since_timestamp = int(time.time()) - (24 * 60 * 60)  # 24 hours ago
            
            if tomlogger:
                tomlogger.info(f"Syncing episode status for actions since last 24 hours (timestamp: {since_timestamp})", module_name="gpodder")
            
            try:
                # Get episode actions from last 24 hours
                episode_actions = self.client.download_episode_actions(since=since_timestamp)
                if tomlogger:
                    tomlogger.info(f"Retrieved {len(episode_actions.actions)} episode actions from last 24h", module_name="gpodder")
                
                if not episode_actions.actions:
                    if tomlogger:
                        tomlogger.info("No recent episode actions to sync", module_name="gpodder")
                    return
                
                dbconn = sqlite3.connect(self.db)
                cursor = dbconn.cursor()
                
                # Process each episode action
                for action in episode_actions.actions:
                    try:
                        episode_url = action.episode
                        action_type = action.action
                        
                        # Check if action is 'play'
                        if action_type == 'play':
                            # Update episode status to 'played'
                            cursor.execute("""
                                UPDATE episodes 
                                SET status = 'played' 
                                WHERE url = ? AND status != 'played'
                            """, (episode_url,))
                            
                            if cursor.rowcount > 0:
                                if tomlogger:
                                    tomlogger.debug(f"Marked episode as played: {episode_url}", module_name="gpodder")
                        
                        # Handle other possible actions (download, delete, etc.)
                        elif action_type == 'download':
                            cursor.execute("""
                                UPDATE episodes 
                                SET status = 'downloaded' 
                                WHERE url = ? AND status = 'unplayed'
                            """, (episode_url,))
                            
                            if cursor.rowcount > 0:
                                if tomlogger:
                                    tomlogger.debug(f"Marked episode as downloaded: {episode_url}", module_name="gpodder")
                                
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Error processing episode action {action}: {e}", module_name="gpodder")
                        continue
                
                dbconn.commit()
                dbconn.close()
                
                if tomlogger:
                    tomlogger.info("Episode status synchronization completed", module_name="gpodder")
                
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Error downloading episode actions: {e}", module_name="gpodder")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error syncing episode status: {e}", module_name="gpodder")

    def _cleanup_old_episodes(self):
        """Clean up old played episodes (older than 6 months)."""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            cursor.execute("""
                DELETE FROM episodes 
                WHERE status = 'played' 
                AND publication_date < datetime('now', '-6 months')
            """)
            deleted_count = cursor.rowcount
            
            dbconn.commit()
            dbconn.close()
            
            if deleted_count > 0:
                if tomlogger:
                    tomlogger.info(f"Cleanup: {deleted_count} old episodes removed", module_name="gpodder")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error cleaning up old episodes: {e}", module_name="gpodder")

    def _update_background_status(self):
        """Update background status with unheard episode count."""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Count unheard episodes
            cursor.execute("SELECT COUNT(id) FROM episodes WHERE status = 'unplayed'")
            unheard_episodes = cursor.fetchall()
            dbconn.close()
            
            nb_episodes = unheard_episodes[0][0]
            
            if nb_episodes == 0:
                status = None
            else:
                status = f"{nb_episodes} unheard episodes"
            
            # Update background_status if changed
            if status != self.background_status['status']:
                self.background_status['ts'] = int(time.time())
                self.background_status['status'] = status
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating background status: {e}", module_name="gpodder")

    def list_podcast_subscriptions(self) -> str:
        """List all podcast subscriptions with unheard episode counts."""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Get all subscriptions with unheard episode counts
            cursor.execute("""
                SELECT s.id, s.title, s.url, 
                       COUNT(e.id) as total_episodes,
                       COUNT(CASE WHEN e.status = 'unplayed' THEN 1 END) as unheard_count
                FROM subscriptions s
                LEFT JOIN episodes e ON s.id = e.subscription_id
                GROUP BY s.id, s.title, s.url
                ORDER BY s.title
            """)
            
            subscriptions_data = cursor.fetchall()
            dbconn.close()
            
            subscriptions = []
            for row in subscriptions_data:
                sub_id, title, url, total_episodes, unheard_count = row
                
                subscription_info = {
                    'id': sub_id,
                    'title': title,
                    'url': url,
                    'total_episodes': total_episodes,
                    'unheard_episodes': unheard_count
                }
                
                subscriptions.append(subscription_info)
            
            result = {
                'status': 'success',
                'subscriptions': subscriptions,
                'total_subscriptions': len(subscriptions)
            }
            
            if tomlogger:
                tomlogger.info(f"Retrieved {len(subscriptions)} podcast subscriptions", module_name="gpodder")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing podcast subscriptions: {e}", module_name="gpodder")
            return json.dumps({
                'status': 'error',
                'message': f'Failed to list subscriptions: {str(e)}'
            }, ensure_ascii=False)

    def list_unheard_episodes(self, limit: int = 50) -> str:
        """List all unheard podcast episodes, organized by subscription."""
        try:
            # Validate limit parameter
            if limit is None:
                limit = 50
            elif limit > 200:
                limit = 200
            elif limit < 1:
                limit = 1
                
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Get unheard episodes with subscription information, ordered by publication date (newest first)
            cursor.execute("""
                SELECT s.title as podcast_title, s.url as podcast_url,
                       e.id, e.title, e.publication_date, e.url, e.description, e.status
                FROM episodes e
                JOIN subscriptions s ON e.subscription_id = s.id
                WHERE e.status = 'unplayed'
                ORDER BY e.publication_date DESC, e.id DESC
                LIMIT ?
            """, (limit,))
            
            episodes_data = cursor.fetchall()
            dbconn.close()
            
            # Organize episodes by podcast
            podcasts = {}
            for row in episodes_data:
                podcast_title, podcast_url, ep_id, ep_title, pub_date, ep_url, description, status = row
                
                if podcast_title not in podcasts:
                    podcasts[podcast_title] = {
                        'podcast_title': podcast_title,
                        'podcast_url': podcast_url,
                        'episodes': []
                    }
                
                episode_info = {
                    'id': ep_id,
                    'title': ep_title,
                    'publication_date': pub_date,
                    'url': ep_url,
                    'description': description[:300] + '...' if description and len(description) > 300 else description,
                    'status': status
                }
                
                podcasts[podcast_title]['episodes'].append(episode_info)
            
            # Convert to list and count total episodes
            podcasts_list = list(podcasts.values())
            total_episodes = sum(len(podcast['episodes']) for podcast in podcasts_list)
            
            result = {
                'status': 'success',
                'podcasts': podcasts_list,
                'total_unheard_episodes': total_episodes,
                'limit_applied': limit
            }
            
            if tomlogger:
                tomlogger.info(f"Retrieved {total_episodes} unheard episodes across {len(podcasts_list)} podcasts", module_name="gpodder")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing unheard episodes: {e}", module_name="gpodder")
            return json.dumps({
                'status': 'error',
                'message': f'Failed to list unheard episodes: {str(e)}'
            }, ensure_ascii=False)


# Load configuration and initialize gpodder service
config = load_config()
gpodder_service = GPodderService(config)


@server.tool()
def list_podcast_subscriptions() -> str:
    """List all podcast subscriptions with their information including unheard episode count."""
    if tomlogger:
        tomlogger.info("Tool call: list_podcast_subscriptions", module_name="gpodder")
    
    return gpodder_service.list_podcast_subscriptions()


@server.tool()
def list_unheard_episodes(limit: int = 50) -> str:
    """List all unheard/unplayed podcast episodes, organized by podcast subscription.
    
    Args:
        limit: Maximum number of episodes to return (default: 50, max: 200)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_unheard_episodes with limit={limit}", module_name="gpodder")
    
    return gpodder_service.list_unheard_episodes(limit)


@server.resource("description://gpodder")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


@server.resource("description://tom_notification")
def notification_status() -> str:
    """Return current background notification status - number of unheard episodes."""
    try:
        dbconn = sqlite3.connect(gpodder_service.db)
        cursor = dbconn.cursor()
        cursor.execute("SELECT COUNT(*) FROM episodes WHERE status = 'unplayed'")
        unheard_count = cursor.fetchone()[0]
        dbconn.close()
        
        if unheard_count > 0:
            return str(unheard_count)
        else:
            return ""  # No status to report when no unheard episodes
            
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"Error getting notification status: {str(e)}", module_name="gpodder")
        return ""  # Return empty string on error to avoid breaking the system


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting GPodder MCP Server on port 80", module_name="gpodder")
    else:
        print("Starting GPodder MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
