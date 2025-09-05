#!/usr/bin/env python3
"""
YouTube MCP Server
Provides YouTube channel management functionality via MCP protocol
Based on the original tomyoutube.py module
"""

import json
import os
import sys
import yaml
import functools
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

import feedparser
import yt_dlp
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
    tomlogger.info(f"🚀 YouTube MCP Server starting with log level: {log_level}", module_name="youtube")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for any question about the youtube videos and youtube channels."

# Initialize FastMCP server
server = FastMCP(name="youtube-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file using TOM_USER environment variable"""
    tom_user = os.environ.get('TOM_USER', 'unknown')
    config_path = f'/data/{tom_user}/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration for user '{tom_user}' from {config_path}", module_name="youtube")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="youtube")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="youtube")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class YouTubeService:
    """YouTube service class based on original TomYoutube"""
    
    def __init__(self, config: Dict[str, Any]):
        # Get user from environment for database path
        tom_user = os.environ.get('TOM_USER', 'unknown')
        self.db = f'/data/{tom_user}/youtube.sqlite'
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db), exist_ok=True)
        
        self.url = "https://youtube.com/feeds/videos.xml?channel_id="
        self.background_status = {"ts": int(time.time()), "status": None}
        
        # Initialize database
        self._init_database()
        
        # Start background update thread
        self.thread = threading.Thread(target=self.thread_update)
        self.thread.daemon = True
        self.thread.start()
        
        if tomlogger:
            tomlogger.info(f"✅ YouTube service initialized successfully with database: {self.db}", module_name="youtube")
    
    def _init_database(self):
        """Initialize SQLite database with required tables"""
        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        
        cursor.execute('''
        create table if not exists channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            channel_name TEXT,
            last_update DATETIME DEFAULT current_date
        )
        ''')
        
        cursor.execute('''
        create table if not exists videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            channel_id TEXT,
            channel_name TEXT,
            publication DATETIME,
            title TEXT,
            uri TEXT,
            viewed BOOLEAN DEFAULT 0,
            video_type TEXT DEFAULT 'video'
        )
        ''')
        
        dbconn.commit()
        dbconn.close()
        
        if tomlogger:
            tomlogger.debug("Database initialized successfully", module_name="youtube")
    
    def thread_update(self):
        """Background thread to update video feeds"""
        while True:
            try:
                if tomlogger:
                    tomlogger.info("Update videos ...", module_name="youtube")
                self.video_update()
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Failed to update videos: {str(e)}", module_name="youtube")
            
            time.sleep(900)  # Update every 15 minutes
    
    def video_update(self):
        """Update video feeds from subscribed channels"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT channel_id, channel_name, last_update FROM channels")
            channels = cursor.fetchall()
            dbconn.close()
            
            for channel in channels:
                channel_id = channel[0]
                name = channel[1]
                update = datetime.strptime(channel[2], "%Y-%m-%d %H:%M:%S").timetuple()
                
                url = self.url + channel_id
                feed = feedparser.parse(url)
                
                if feed:
                    # Get the last update
                    for video in feed['entries']:
                        dbconn = sqlite3.connect(self.db)
                        cursor = dbconn.cursor()
                        cursor.execute("SELECT video_id FROM videos WHERE channel_id=?", (channel_id,))
                        videos = cursor.fetchall()
                        dbconn.close()
                        
                        all_videos = [val[0] for val in videos]
                        
                        if video['id'] not in all_videos:
                            # Check if video is not too old (>5 months) before adding
                            should_add = True
                            if video.get('published_parsed'):
                                try:
                                    video_date = datetime.fromtimestamp(time.mktime(video['published_parsed']))
                                    five_months_ago = datetime.now() - timedelta(days=150)
                                    if video_date < five_months_ago:
                                        should_add = False
                                        if tomlogger:
                                            tomlogger.debug(f"Skipping old video (>5 months): {video['title']}", module_name="youtube")
                                except:
                                    # If date parsing fails, add the video anyway
                                    pass
                            
                            if should_add:
                                dbconn = sqlite3.connect(self.db)
                                cursor = dbconn.cursor()
                                video_type = 'short' if '/shorts/' in video['link'] else 'video'
                                cursor.execute(
                                    "INSERT INTO videos (video_id, channel_id, channel_name, publication, title, uri, video_type) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                    (video['id'], channel_id, name, datetime.fromtimestamp(time.mktime(video['published_parsed'])).strftime("%Y-%m-%d %H:%M:%S"), 
                                     video['title'], video['link'], video_type)
                                )
                                dbconn.commit()
                                dbconn.close()
                        
                        # Update channel last update to now
                        dbconn = sqlite3.connect(self.db)
                        cursor = dbconn.cursor()
                        cursor.execute("UPDATE channels SET last_update = datetime('now', 'localtime') WHERE channel_id=?", (channel_id,))
                        dbconn.commit()
                        dbconn.close()
                else:
                    if tomlogger:
                        tomlogger.error(f"Could not parse feed for channel: {name}", module_name="youtube")
            
            # Update background status
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT count(id) FROM videos WHERE viewed = 0")
            allvideos = cursor.fetchall()
            dbconn.close()
            
            nb_videos = allvideos[0][0]
            
            if nb_videos == 0:
                status = None
            else:
                status = f"{nb_videos} new videos"
            
            if status != self.background_status['status']:
                self.background_status['ts'] = int(time.time())
                self.background_status['status'] = status
            
            # Clean up old viewed videos (>6 months)
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("DELETE FROM videos WHERE viewed = 1 AND publication < datetime('now', '-6 months')")
            deleted_count = cursor.rowcount
            dbconn.commit()
            dbconn.close()
            
            if deleted_count > 0 and tomlogger:
                tomlogger.info(f"Cleanup: {deleted_count} old videos deleted", module_name="youtube")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error during video update: {str(e)}", module_name="youtube")
    
    def list_unviewed_videos(self) -> Dict[str, Any]:
        """Get all unviewed videos"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT id, channel_name, title, uri, video_type FROM videos WHERE viewed = 0")
            allvideos = cursor.fetchall()
            dbconn.close()
            
            videos = {"videos": []}
            
            for video in allvideos:
                video_id = video[0]
                channel = video[1]
                title = video[2]
                uri = video[3]
                video_type = video[4] if len(video) > 4 else 'video'
                
                videos['videos'].append({
                    "video_id": video_id, 
                    "channel": channel, 
                    "title": title, 
                    "url": uri, 
                    "video_type": video_type, 
                    "viewed": False
                })
            
            if tomlogger:
                tomlogger.debug(f"Retrieved {len(videos['videos'])} unviewed videos", module_name="youtube")
            
            if videos['videos']:
                return videos
            else:
                return {"status": "success", "message": "No non viewed video"}
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing unviewed videos: {str(e)}", module_name="youtube")
            return {"status": "error", "message": f"Failed to list videos: {str(e)}"}
    
    def mark_video_as_viewed(self, video_ids: List[str]) -> Dict[str, Any]:
        """Mark videos as viewed"""
        if isinstance(video_ids, str):
            video_ids = [video_ids]
        
        # Convert all video_ids to strings to handle both integer and string inputs
        video_ids = [str(vid) for vid in video_ids]
        
        if not video_ids:
            return {"status": "error", "message": "No video IDs provided"}
        
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            placeholders = ','.join('?' * len(video_ids))
            cursor.execute(f"UPDATE videos SET viewed=1 WHERE id IN ({placeholders})", video_ids)
            updated_rows = cursor.rowcount
            
            dbconn.commit()
            dbconn.close()
            
            if updated_rows == 1:
                message = "Video marked as viewed"
            else:
                message = f"{updated_rows} videos marked as viewed"
            
            if tomlogger:
                tomlogger.info(f"{message} (IDs: {video_ids})", module_name="youtube")
            
            return {"status": "success", "message": message}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error marking videos as viewed: {str(e)}", module_name="youtube")
            return {"status": "error", "message": f"Failed to mark videos as viewed: {str(e)}"}
    
    def search_youtube_channels(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search for YouTube channels based on a query term"""
        if not query or not query.strip():
            return {"status": "error", "message": "Search query cannot be empty"}
        
        if max_results > 20:
            max_results = 20
        elif max_results < 1:
            max_results = 1
        
        try:
            # Configuration yt-dlp for metadata extraction only
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'no_warnings': True,
            }
            
            channels = []
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Search for videos to find channels
                search_url = f"ytsearch{max_results * 2}:{query}"
                
                # Extract search results
                search_results = ydl.extract_info(search_url, download=False)
                
                if 'entries' not in search_results:
                    return {"status": "success", "channels": []}
                
                # Dictionary to avoid channel duplicates
                seen_channels = {}
                
                for entry in search_results['entries']:
                    if entry and len(channels) < max_results:
                        # Extract channel info from video
                        channel_info = self._extract_channel_from_video(entry)
                        if channel_info:
                            channel_id = channel_info.get('channel_id', '')
                            if channel_id and channel_id not in seen_channels:
                                seen_channels[channel_id] = True
                                channels.append(channel_info)
            
            if tomlogger:
                tomlogger.info(f"Found {len(channels)} channels for query: {query}", module_name="youtube")
            return {"status": "success", "channels": channels}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error searching YouTube channels: {e}", module_name="youtube")
            return {"status": "error", "message": f"Search failed: {str(e)}"}
    
    def _extract_channel_from_video(self, entry):
        """Extract channel information from a video entry"""
        try:
            uploader = entry.get('uploader', entry.get('channel', ''))
            channel_id = entry.get('channel_id', entry.get('uploader_id', ''))
            
            if not uploader or not channel_id:
                return None
            
            # Get real channel description
            real_description = self._get_channel_about(channel_id) if channel_id else ""
            
            # Channel information
            channel_info = {
                'name': uploader,
                'description': real_description,
                'channel_id': channel_id
            }
            
            return channel_info
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error extracting channel info: {e}", module_name="youtube")
            return None
    
    def _get_channel_about(self, channel_id):
        """Get the complete description (About) of a YouTube channel"""
        if not channel_id:
            return ""
        
        try:
            # Configuration for complete metadata retrieval
            ydl_opts = {
                'quiet': True,
                'extract_flat': False,
                'no_warnings': True,
                'skip_download': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                channel_url = f"https://www.youtube.com/channel/{channel_id}/about"
                
                # Extract info from channel About page
                info = ydl.extract_info(channel_url, download=False)
                
                if info:
                    # Look for description in different possible fields
                    description = (
                        info.get('description') or 
                        info.get('channel_description') or
                        info.get('uploader_description') or
                        ""
                    )
                    
                    if description and description.strip():
                        return description.strip()
                    
                    # If no description found, try main channel URL
                    channel_main_url = f"https://www.youtube.com/channel/{channel_id}"
                    main_info = ydl.extract_info(channel_main_url, download=False)
                    
                    if main_info:
                        main_description = (
                            main_info.get('description') or
                            main_info.get('channel_description') or
                            main_info.get('uploader_description') or
                            ""
                        )
                        
                        if main_description and main_description.strip():
                            return main_description.strip()
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error getting channel description for {channel_id}: {e}", module_name="youtube")
        
        return ""
    
    def get_channel_recent_videos(self, channel_id: str, max_videos: int = 15) -> Dict[str, Any]:
        """Get recent videos from a YouTube channel using RSS feed"""
        if not channel_id or not channel_id.strip():
            return {"status": "error", "message": "Channel ID cannot be empty"}
        
        if not channel_id.startswith('UC'):
            return {"status": "error", "message": "Channel ID must start with 'UC'"}
        
        if max_videos > 50:
            max_videos = 50
        elif max_videos < 1:
            max_videos = 1
        
        try:
            # Build RSS URL
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            
            # Parse RSS feed
            feed = feedparser.parse(rss_url)
            
            if not feed or not hasattr(feed, 'entries'):
                return {"status": "error", "message": "Could not fetch channel RSS feed"}
            
            if feed.bozo and tomlogger:
                tomlogger.warning(f"RSS feed parsing warning for channel {channel_id}: {feed.bozo_exception}", module_name="youtube")
            
            # Extract channel information
            channel_info = {
                'channel_name': feed.feed.get('title', 'Unknown Channel'),
                'channel_url': feed.feed.get('link', ''),
                'channel_id': channel_id
            }
            
            # Extract videos
            videos = []
            for entry in feed.entries[:max_videos]:
                try:
                    # Extract video information
                    video_id = entry.get('yt_videoid', '')
                    if not video_id:
                        # Fallback: extract from id field (format: yt:video:VIDEO_ID)
                        video_id = entry.get('id', '').replace('yt:video:', '')
                    
                    # Determine video type (video vs short)
                    video_url = entry.get('link', '')
                    video_type = 'short' if '/shorts/' in video_url else 'video'
                    
                    # Get publication date
                    published_parsed = entry.get('published_parsed')
                    publication_date = None
                    if published_parsed:
                        publication_date = datetime.fromtimestamp(time.mktime(published_parsed)).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Extract additional metadata
                    media_group = entry.get('media_group', {})
                    description = ""
                    thumbnail_url = ""
                    view_count = 0
                    rating = 0
                    
                    if media_group:
                        description = media_group.get('media_description', '')
                        thumbnails = media_group.get('media_thumbnail', [])
                        if thumbnails and isinstance(thumbnails, list):
                            thumbnail_url = thumbnails[0].get('url', '')
                        
                        # Extract statistics if available
                        community = media_group.get('media_community', {})
                        if community:
                            stats = community.get('media_statistics', {})
                            if stats:
                                view_count = int(stats.get('views', 0))
                            
                            rating_info = community.get('media_starrating', {})
                            if rating_info:
                                rating = float(rating_info.get('average', 0))
                    
                    video_info = {
                        'video_id': video_id,
                        'title': entry.get('title', ''),
                        'url': video_url,
                        'publication_date': publication_date,
                        'video_type': video_type,
                        'description': description,
                        'thumbnail': thumbnail_url,
                        'view_count': view_count,
                        'rating': rating
                    }
                    
                    videos.append(video_info)
                    
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error processing video entry: {e}", module_name="youtube")
                    continue
            
            result = {
                'status': 'success',
                'channel': channel_info,
                'videos': videos,
                'total_videos': len(videos)
            }
            
            if tomlogger:
                tomlogger.info(f"Retrieved {len(videos)} videos from channel {channel_id}", module_name="youtube")
            return result
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error fetching channel videos for {channel_id}: {e}", module_name="youtube")
            return {"status": "error", "message": f"Failed to fetch channel videos: {str(e)}"}
    
    def list_subscriptions(self) -> Dict[str, Any]:
        """List all subscribed YouTube channels"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT channel_id, channel_name, last_update FROM channels ORDER BY channel_name")
            channels = cursor.fetchall()
            dbconn.close()
            
            subscriptions = []
            for channel in channels:
                channel_id = channel[0]
                channel_name = channel[1]
                last_update = channel[2]
                
                # Count unviewed videos for this channel
                dbconn = sqlite3.connect(self.db)
                cursor = dbconn.cursor()
                cursor.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ? AND viewed = 0", (channel_id,))
                unviewed_count = cursor.fetchone()[0]
                dbconn.close()
                
                subscription_info = {
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'last_update': last_update,
                    'unviewed_videos': unviewed_count
                }
                
                subscriptions.append(subscription_info)
            
            result = {
                'status': 'success',
                'subscriptions': subscriptions,
                'total_channels': len(subscriptions)
            }
            
            if tomlogger:
                tomlogger.info(f"Retrieved {len(subscriptions)} subscribed channels", module_name="youtube")
            return result
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing subscriptions: {e}", module_name="youtube")
            return {"status": "error", "message": f"Failed to list subscriptions: {str(e)}"}
    
    def add_subscription(self, channel_id: str, channel_name: Optional[str] = None) -> Dict[str, Any]:
        """Add a YouTube channel to subscriptions"""
        if not channel_id or not channel_id.strip():
            return {"status": "error", "message": "Channel ID cannot be empty"}
        
        if not channel_id.startswith('UC'):
            return {"status": "error", "message": "Channel ID must start with 'UC'"}
        
        try:
            # Check if channel is already subscribed
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("SELECT channel_id FROM channels WHERE channel_id = ?", (channel_id,))
            existing = cursor.fetchone()
            dbconn.close()
            
            if existing:
                return {"status": "error", "message": "Channel is already in subscriptions"}
            
            # Auto-detect channel name if not provided
            if not channel_name:
                try:
                    # Try to get channel info from RSS feed
                    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    feed = feedparser.parse(rss_url)
                    
                    if feed and hasattr(feed, 'feed') and feed.feed.get('title'):
                        channel_name = feed.feed.get('title')
                    else:
                        channel_name = f"Channel {channel_id}"
                        
                except Exception as e:
                    if tomlogger:
                        tomlogger.warning(f"Could not auto-detect channel name for {channel_id}: {e}", module_name="youtube")
                    channel_name = f"Channel {channel_id}"
            
            # Add channel to database
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("""
                INSERT INTO channels (channel_id, channel_name, last_update) 
                VALUES (?, ?, datetime('now', 'localtime'))
            """, (channel_id, channel_name))
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info(f"Added subscription for channel: {channel_name} ({channel_id})", module_name="youtube")
            return {
                "status": "success", 
                "message": f"Successfully subscribed to channel: {channel_name}",
                "channel_id": channel_id,
                "channel_name": channel_name
            }
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error adding subscription for {channel_id}: {e}", module_name="youtube")
            return {"status": "error", "message": f"Failed to add subscription: {str(e)}"}
    
    def remove_subscription(self, channel_id: str) -> Dict[str, Any]:
        """Remove a YouTube channel from subscriptions"""
        if not channel_id or not channel_id.strip():
            return {"status": "error", "message": "Channel ID or name cannot be empty"}
        
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Try to find channel by ID first, then by name
            cursor.execute("SELECT channel_id, channel_name FROM channels WHERE channel_id = ?", (channel_id,))
            channel = cursor.fetchone()
            
            if not channel:
                cursor.execute("SELECT channel_id, channel_name FROM channels WHERE channel_name LIKE ?", (f"%{channel_id}%",))
                channel = cursor.fetchone()
            
            if not channel:
                dbconn.close()
                return {"status": "error", "message": f"Channel '{channel_id}' not found in subscriptions"}
            
            found_channel_id = channel[0]
            found_channel_name = channel[1]
            
            # Remove channel and all its videos
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (found_channel_id,))
            deleted_channels = cursor.rowcount
            
            cursor.execute("DELETE FROM videos WHERE channel_id = ?", (found_channel_id,))
            deleted_videos = cursor.rowcount
            
            dbconn.commit()
            dbconn.close()
            
            if deleted_channels > 0:
                if tomlogger:
                    tomlogger.info(f"Removed subscription for channel: {found_channel_name} ({found_channel_id}), deleted {deleted_videos} videos", module_name="youtube")
                return {
                    "status": "success", 
                    "message": f"Successfully unsubscribed from channel: {found_channel_name}",
                    "channel_id": found_channel_id,
                    "channel_name": found_channel_name,
                    "deleted_videos": deleted_videos
                }
            else:
                return {"status": "error", "message": "No channel was removed"}
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error removing subscription for {channel_id}: {e}", module_name="youtube")
            return {"status": "error", "message": f"Failed to remove subscription: {str(e)}"}


# Load configuration and initialize YouTube service
config = load_config()
youtube_service = YouTubeService(config)


@server.tool()
def get_all_new_videos() -> str:
    """Retrieves a list of all non viewed youtube videos, organized by channel. This function returns for each channel, the video_id, the video title, the video publication date, the video url and a description of the video."""
    if tomlogger:
        tomlogger.info(f"Tool call: get_all_new_videos", module_name="youtube")
    
    result = youtube_service.list_unviewed_videos()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def mark_video_as_seen(video_ids: List[str]) -> str:
    """Marks one or multiple videos as viewed.
    
    Args:
        video_ids: Array of video IDs to mark as seen. Can contain a single ID or multiple IDs.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: mark_video_as_seen with video_ids={video_ids}", module_name="youtube")
    
    result = youtube_service.mark_video_as_viewed(video_ids)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def search_youtube_channels(query: str, max_results: int) -> str:
    """Search for YouTube channels based on a query term. Returns channel name, description, and channel ID for each result.
    
    Args:
        query: The search term to find YouTube channels
        max_results: Maximum number of channels to return (default: 10, max: 20)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: search_youtube_channels with query={query}, max_results={max_results}", module_name="youtube")
    
    result = youtube_service.search_youtube_channels(query, max_results)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def get_channel_recent_videos(channel_id: str, max_videos: int) -> str:
    """Get recent videos from a YouTube channel using its RSS feed. Returns detailed information about the channel's latest videos including title, description, publication date, view count, and video type.
    
    Args:
        channel_id: YouTube channel ID (format UCxxxxxxx)
        max_videos: Maximum number of videos to return (default: 15, max: 50)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_channel_recent_videos with channel_id={channel_id}, max_videos={max_videos}", module_name="youtube")
    
    result = youtube_service.get_channel_recent_videos(channel_id, max_videos)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def list_subscriptions() -> str:
    """List all subscribed YouTube channels with their information including unviewed video count."""
    if tomlogger:
        tomlogger.info(f"Tool call: list_subscriptions", module_name="youtube")
    
    result = youtube_service.list_subscriptions()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def add_subscription(channel_id: str, channel_name: str) -> str:
    """Add a YouTube channel to subscriptions. Channel name will be auto-detected if not provided.
    
    Args:
        channel_id: YouTube channel ID (format UCxxxxxxx)
        channel_name: Optional channel name (will be auto-detected if not provided)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: add_subscription with channel_id={channel_id}, channel_name={channel_name}", module_name="youtube")
    
    result = youtube_service.add_subscription(channel_id, channel_name)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def remove_subscription(channel_id: str) -> str:
    """Remove a YouTube channel from subscriptions. Can use either channel ID (UCxxxxxxx) or channel name.
    
    Args:
        channel_id: YouTube channel ID (format UCxxxxxxx) or channel name to remove
    """
    if tomlogger:
        tomlogger.info(f"Tool call: remove_subscription with channel_id={channel_id}", module_name="youtube")
    
    result = youtube_service.remove_subscription(channel_id)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://youtube")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


@server.resource("description://tom_notification")
def notification_status() -> str:
    """Return current background notification status - number of unviewed videos."""
    try:
        dbconn = sqlite3.connect(youtube_service.db)
        cursor = dbconn.cursor()
        cursor.execute("SELECT COUNT(*) FROM videos WHERE viewed = 0")
        unviewed_count = cursor.fetchone()[0]
        dbconn.close()
        
        if unviewed_count > 0:
            return str(unviewed_count)
        else:
            return ""  # No status to report when no unviewed videos
            
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"Error getting notification status: {str(e)}", module_name="youtube")
        return ""  # Return empty string on error to avoid breaking the system


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting YouTube MCP Server on port 80", module_name="youtube")
    else:
        print("Starting YouTube MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()