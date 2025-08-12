import sqlite3
import threading
import time
import os
import sys
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from mygpoclient.api import MygPodderClient

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

################################################################################################
#                                                                                              #
#                                   GPodder.net Module                                         #
#                                                                                              #
################################################################################################

tom_config = {
    "module_name": "gpodder",
    "class_name": "TomGPodder",
    "description": "This module is used for managing podcast subscriptions using gpodder.net service.",
    "type": "personal",
    "complexity": 1,
    "configuration_parameters": {
        "username": {
            "type": "string",
            "description": "GPodder.net username for authentication.",
            "required": True
        },
        "password": {
            "type": "string",
            "description": "GPodder.net password for authentication.",
            "required": True
        }
    }
}

class TomGPodder:

    def __init__(self, config, llm) -> None:
        
        self.db = config['cache_db']

        # Store credentials
        self.gpodder_username = config.get('username')
        self.gpodder_password = config.get('password')
        
        self.device_id = "tom"
        
        self.llm = llm
        self.background_status = {"ts": int(time.time()), "status": None}

        # Initialize database
        self._init_database()
        
        # Initialize GPodder client
        if self.gpodder_username and self.gpodder_password:
            self.client = MygPodderClient(self.gpodder_username, self.gpodder_password)
            self._create_device()
        else:
            self.client = None
            logger.warning("GPodder credentials not configured")
        
        # Start background sync thread
        if self.client:
            self.sync_thread = threading.Thread(target=self._background_sync)
            self.sync_thread.daemon = True
            self.sync_thread.start()

        # Tools exposed to LLM
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_podcast_subscriptions",
                    "description": "List all podcast subscriptions with their information including unheard episode count.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_unviewed_episodes",
                    "description": "List all unheard/unplayed podcast episodes, organized by podcast subscription.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of episodes to return (default: 50, max: 200)",
                                "minimum": 1,
                                "maximum": 200
                            }
                        },
                        "additionalProperties": False,
                    },
                },
            },
        ]
        
        self.systemContext = '''
        This module manages podcast subscriptions using gpodder.net service.
        
        The function 'list_podcast_subscriptions' shows all subscribed podcasts:
           - Use this to show the user what podcasts they are currently subscribed to
           - Returns podcast titles, URLs, and count of unheard episodes for each subscription
           - Helps users understand their current podcast library
        
        The function 'list_unheard' shows unheard/unplayed episodes:
           - Use this to show the user which podcast episodes they haven't listened to yet
           - Episodes are organized by podcast for better readability
           - Includes episode titles, publication dates, descriptions, and URLs
           - Can limit the number of results to avoid overwhelming the user
           - Episodes are sorted by publication date (newest first)
        '''
        
        self.complexity = tom_config.get("complexity", 0)
        self.functions = {
            "list_podcast_subscriptions": {
                "function": self.list_podcast_subscriptions
            },
            "list_unheard_episodes": {
                "function": self.list_unheard_episodes
            },
        }

    def _init_database(self):
        """Initialize the SQLite database with required tables."""
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
        
        logger.info(f"GPodder database initialized at {self.db}")

    def _create_device(self):
        """Create the 'tom' device on GPodder.net if it doesn't exist."""
        if not self.client:
            return
            
        try:
            self.client.create_device(self.device_id, "desktop", "Tom Assistant")
            logger.info(f"Created device '{self.device_id}' on GPodder.net")
        except Exception as e:
            logger.debug(f"Device '{self.device_id}' already exists or error creating: {e}")

    def _sync_subscriptions(self):
        """Synchronize subscriptions from GPodder.net to local database."""
        if not self.client:
            return
            
        try:
            # Get subscriptions from GPodder.net
            subscriptions = self.client.get_subscriptions(self.device_id)
            logger.info(f"Retrieved {len(subscriptions)} subscriptions from GPodder.net")
            
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
                    logger.info(f"Added new subscription: {title}")
                    
                except Exception as e:
                    logger.error(f"Error adding subscription {sub_url}: {e}")
                    continue
            
            # Remove deleted subscriptions
            deleted_subscriptions = db_subscriptions - gpodder_subscriptions
            for sub_url in deleted_subscriptions:
                try:
                    cursor.execute("SELECT title FROM subscriptions WHERE url = ?", (sub_url,))
                    result = cursor.fetchone()
                    title = result[0] if result else "Unknown"
                    
                    cursor.execute("DELETE FROM subscriptions WHERE url = ?", (sub_url,))
                    logger.info(f"Removed deleted subscription: {title}")
                    
                except Exception as e:
                    logger.error(f"Error removing subscription {sub_url}: {e}")
                    continue
            
            dbconn.commit()
            dbconn.close()
            
            logger.info(f"Subscriptions synchronized: {len(new_subscriptions)} added, {len(deleted_subscriptions)} removed")
            
        except Exception as e:
            logger.error(f"Error syncing subscriptions from GPodder.net: {e}")

    def _background_sync(self):
        """Background thread to sync subscriptions and episodes every 60 minutes."""
        while True:
            try:
                logger.info("Starting background sync of GPodder data...")
                # First sync subscriptions, then episodes, then episode status sequentially
                self._sync_subscriptions()
                self._sync_episodes()
                self._sync_episode_status()
                self._cleanup_old_episodes()
                self._update_background_status()
                logger.info("Background sync completed successfully")
            except Exception as e:
                logger.error(f"Error in background sync: {e}")
            
            # Wait 60 minutes (3600 seconds)
            time.sleep(3600)

    def _extract_podcast_title(self, sub_url):
        """Extract the real podcast title from RSS feed, like in gpodder_checker.py."""
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
            logger.error(f"Error extracting title from RSS feed {sub_url}: {e}")
            # Fallback to URL-based title
            return sub_url.split('/')[-1] if '/' in sub_url else sub_url

    def _sync_episodes(self):
        """Synchronize episodes from RSS feeds to local database, based on gpodder_checker.py."""
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
                    logger.debug(f"Syncing episodes for subscription {subscription_id}: {sub_url}")
                    
                    # Get RSS feed (same as gpodder_checker.py line 48-50)
                    response = requests.get(sub_url)
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                    
                    # Parse all episodes from RSS feed (same as gpodder_checker.py line 63)
                    for item in root.findall('./channel/item'):
                        try:
                            # Extract episode data (same as gpodder_checker.py line 64-65)
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
                                    from email.utils import parsedate_to_datetime
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
                                # Insert new episode
                                cursor.execute("""
                                    INSERT INTO episodes (subscription_id, title, publication_date, url, description)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (subscription_id, episode_title, publication_date, episode_url, description))
                                
                                logger.debug(f"Added new episode: {episode_title}")
                            
                        except Exception as e:
                            logger.error(f"Error processing episode in {sub_url}: {e}")
                            continue
                    
                except Exception as e:
                    logger.error(f"Error syncing episodes for subscription {sub_url}: {e}")
                    continue
            
            dbconn.commit()
            dbconn.close()
            
            logger.info("Episodes synchronization completed")
            
        except Exception as e:
            logger.error(f"Error syncing episodes: {e}")

    def _sync_episode_status(self):
        """Synchronize episode play status based on GPodder episode actions, based on gpodder_checker.py."""
        if not self.client:
            return
            
        try:
            # Calculate timestamp for 24 hours ago
            since_timestamp = int(time.time()) - (24 * 60 * 60)  # 24 hours ago
            
            logger.info(f"Syncing episode status for actions since last 24 hours (timestamp: {since_timestamp})")
            
            try:
                # Get episode actions from last 24 hours (same as gpodder_checker.py line 56 but with since parameter)
                episode_actions = self.client.download_episode_actions(since=since_timestamp)
                logger.info(f"Retrieved {len(episode_actions.actions)} episode actions from last 24h")
                
                if not episode_actions.actions:
                    logger.info("No recent episode actions to sync")
                    return
                
                dbconn = sqlite3.connect(self.db)
                cursor = dbconn.cursor()
                
                # Process each episode action
                for action in episode_actions.actions:
                    try:
                        episode_url = action.episode
                        action_type = action.action
                        
                        # Same logic as gpodder_checker.py line 57 - check if action is 'play'
                        if action_type == 'play':
                            # Update episode status to 'played'
                            cursor.execute("""
                                UPDATE episodes 
                                SET status = 'played' 
                                WHERE url = ? AND status != 'played'
                            """, (episode_url,))
                            
                            if cursor.rowcount > 0:
                                logger.debug(f"Marked episode as played: {episode_url}")
                        
                        # Handle other possible actions (download, delete, etc.)
                        elif action_type == 'download':
                            cursor.execute("""
                                UPDATE episodes 
                                SET status = 'downloaded' 
                                WHERE url = ? AND status = 'unplayed'
                            """, (episode_url,))
                            
                            if cursor.rowcount > 0:
                                logger.debug(f"Marked episode as downloaded: {episode_url}")
                                
                    except Exception as e:
                        logger.error(f"Error processing episode action {action}: {e}")
                        continue
                
                dbconn.commit()
                dbconn.close()
                
                logger.info("Episode status synchronization completed")
                
            except Exception as e:
                logger.error(f"Error downloading episode actions: {e}")
                
        except Exception as e:
            logger.error(f"Error syncing episode status: {e}")

    def list_podcast_subscriptions(self):
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
            
            logger.info(f"Retrieved {len(subscriptions)} podcast subscriptions")
            return result
            
        except Exception as e:
            logger.error(f"Error listing podcast subscriptions: {e}")
            return {
                'status': 'error',
                'message': f'Failed to list subscriptions: {str(e)}'
            }

    def list_unheard_episodes(self, limit=50):
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
            
            logger.info(f"Retrieved {total_episodes} unheard episodes across {len(podcasts_list)} podcasts")
            return result
            
        except Exception as e:
            logger.error(f"Error listing unheard episodes: {e}")
            return {
                'status': 'error',
                'message': f'Failed to list unheard episodes: {str(e)}'
            }

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
                logger.info(f"Nettoyage: {deleted_count} épisodes anciens supprimés")
                
        except Exception as e:
            logger.error(f"Error cleaning up old episodes: {e}")

    def _update_background_status(self):
        """Update background status with unheard episode count, like in tomyoutube.py."""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Count unheard episodes (same logic as tomyoutube.py line 362)
            cursor.execute("SELECT COUNT(id) FROM episodes WHERE status = 'unplayed'")
            unheard_episodes = cursor.fetchall()
            dbconn.close()
            
            nb_episodes = unheard_episodes[0][0]
            
            # Same logic as tomyoutube.py lines 368-371
            if nb_episodes == 0:
                status = None
            else:
                status = f"{nb_episodes} unheard episodes"
            
            # Update background_status if changed (same logic as tomyoutube.py lines 373-375)
            if status != self.background_status['status']:
                self.background_status['ts'] = int(time.time())
                self.background_status['status'] = status
                
        except Exception as e:
            logger.error(f"Error updating background status: {e}")
