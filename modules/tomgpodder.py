import sqlite3
import threading
import time
import os
import sys
import requests
import xml.etree.ElementTree as ET
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

        # No tools exposed to LLM for now as requested
        self.tools = []
        
        self.systemContext = '''
        This module manages podcast subscriptions using gpodder.net service.
        Currently no functions are available to the LLM.
        '''
        
        self.complexity = tom_config.get("complexity", 0)
        self.functions = {}

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
        """Background thread to sync subscriptions every 60 minutes."""
        while True:
            try:
                logger.info("Starting background sync of GPodder subscriptions...")
                self._sync_subscriptions()
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
