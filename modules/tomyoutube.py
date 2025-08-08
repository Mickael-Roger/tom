import feedparser
from datetime import datetime
import time
import functools
import sqlite3
import threading
import time
import os
import sys
import yt_dlp

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger


################################################################################################
#                                                                                              #
#                                   Youtube Channel                                            #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "youtube",
  "class_name": "TomYoutube",
  "description": "This module is used for for any question about the youtube videos and youtube channels.",
  "type": "personal",
  "complexity": 1,
  "configuration_parameters": {
    "cache_db": {
      "type": "string",
      "description": "Path to the SQLite database file for caching YouTube channels and videos data.",
      "required": True
    }
  }
}

class TomYoutube:

  def __init__(self, config, llm) -> None:

    self.db = config['cache_db']

    self.url = "https://youtube.com/feeds/videos.xml?channel_id="

    self.llm = llm
    self.background_status = {"ts": int(time.time()), "status": None}

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

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "get_all_new_videos",
          "description": "Retrieves a list of all non viewed youtube videos, organized by channel. This function returns for each channel, the video_id, the video title, the video publicaiton date, the video url and a description of the video.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "mark_video_as_seen",
          "description": "Marks one or multiple videos as viewed.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "video_ids": {
                "type": "array",
                "items": {
                  "type": "string"
                },
                "description": "Array of video IDs to mark as seen. Can contain a single ID or multiple IDs.",
              },
            },
            "required": ["video_ids"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "search_youtube_channels",
          "description": "Search for YouTube channels based on a query term. Returns channel name, description, and channel ID for each result.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "query": {
                "type": "string",
                "description": "The search term to find YouTube channels",
              },
              "max_results": {
                "type": "integer",
                "description": "Maximum number of channels to return (default: 10, max: 20)",
                "minimum": 1,
                "maximum": 20
              }
            },
            "required": ["query", "max_results"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_channel_recent_videos",
          "description": "Get recent videos from a YouTube channel using its RSS feed. Returns detailed information about the channel's latest videos including title, description, publication date, view count, and video type.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "channel_id": {
                "type": "string",
                "description": "YouTube channel ID (format UCxxxxxxx)",
              },
              "max_videos": {
                "type": "integer",
                "description": "Maximum number of videos to return (default: 15, max: 50)",
                "minimum": 1,
                "maximum": 50
              }
            },
            "required": ["channel_id", "max_videos"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = '''
    The function 'mark_video_as_seen' is used in 3 scenarios:
       - When the user has already wtached the video and wants to remove it from the non viewed video list.
       - When the user ask to mark as seen a video
       - When the user is not interested in watching this video and does not plan to watch it, but still wants to mark it as seen to declutter the non viewed video list.
    
    The function 'search_youtube_channels' allows searching for YouTube channels:
       - Use this when the user wants to find new YouTube channels to follow
       - Returns channel name, description, and channel ID (format UCxxxxxxx)
       - The channel ID can later be used to add the channel to the tracking list
    
    The function 'get_channel_recent_videos' retrieves recent videos from a specific channel:
       - Use this when the user wants to see the latest videos from a specific YouTube channel
       - Requires the channel ID (format UCxxxxxxx) which can be obtained from search_youtube_channels
       - Returns detailed information about recent videos including title, description, publication date, view count, and video type
       - Useful for previewing channel content before deciding to follow it
    '''
    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "get_all_new_videos": {
        "function": functools.partial(self.list_unviewed_videos)
      },
      "mark_video_as_seen": {
        "function": functools.partial(self.mark_video_as_viewed)
      },
      "search_youtube_channels": {
        "function": functools.partial(self.search_youtube_channels)
      },
      "get_channel_recent_videos": {
        "function": functools.partial(self.get_channel_recent_videos)
      },
    }


    self.thread = threading.Thread(target=self.thread_update)
    self.thread.daemon = True  # Allow the thread to exit when the main program exits
    self.thread.start()
    

  def mark_video_as_viewed(self, video_ids):
    if isinstance(video_ids, str):
      video_ids = [video_ids]
    
    if not video_ids:
      return {"status": "error", "message": "No video IDs provided"}

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    
    placeholders = ','.join('?' * len(video_ids))
    cursor.execute(f"UPDATE videos SET viewed=1 WHERE id IN ({placeholders})", video_ids)
    updated_rows = cursor.rowcount
    
    dbconn.commit()
    dbconn.close()

    if updated_rows == 1:
      return {"status": "success", "message": "Video marked as viewed"}
    else:
      return {"status": "success", "message": f"{updated_rows} videos marked as viewed"}




  def thread_update(self):
    while True:
      try:
        logger.info("Update videos ...")
        self.video_update()
      except:
        logger.error("Fail to update videos")

      time.sleep(900)


  def video_update(self):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT channel_id, channel_name, last_update FROM channels")
    channels = cursor.fetchall()
    dbconn.close()


    for channel in channels:
      id = channel[0]
      name = channel[1]
      update = datetime.strptime(channel[2], "%Y-%m-%d %H:%M:%S").timetuple()

      url = self.url + id
      feed = feedparser.parse(url)

      if feed:
        # Get the last update
        for video in feed['entries']:
          dbconn = sqlite3.connect(self.db)
          cursor = dbconn.cursor()
          cursor.execute("SELECT video_id FROM videos WHERE channel_id=?", (id,))
          videos = cursor.fetchall()
          dbconn.close()

          all_videos = []
          for val in videos:
            all_videos.append(val[0])

          if video['id'] not in all_videos:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            video_type = 'short' if '/shorts/' in video['link'] else 'video'
            cursor.execute("INSERT INTO videos (video_id, channel_id, channel_name, publication, title, uri, video_type) VALUES (?, ?, ?, ?, ?, ?, ?) ", (video['id'], id, name, datetime.fromtimestamp(time.mktime(video['published_parsed'])).strftime("%Y-%m-%d %H:%M:%S"), video['title'], video['link'], video_type))
            dbconn.commit()
            dbconn.close()

          # Update channel last update to now
          dbconn = sqlite3.connect(self.db)
          cursor = dbconn.cursor()
          cursor.execute("UPDATE channels SET last_update = datetime('now', 'localtime') WHERE channel_id=?", (id,))
          dbconn.commit()
          dbconn.close()

      else:
        logger.error(f"Could not parse feed for channel: {name}")

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


  def list_unviewed_videos(self):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT id, channel_name, title, uri, video_type FROM videos WHERE viewed = 0")
    allvideos = cursor.fetchall()
    dbconn.close()

    videos = {"videos": []}

    for video in allvideos:
      id = video[0]
      channel = video[1]
      title = video[2]
      uri = video[3]
      video_type = video[4] if len(video) > 4 else 'video'

      videos['videos'].append({"video_id": id, "channel": channel, "title": title, "url": uri, "video_type": video_type, "viewed": False})

    logger.debug(videos)
    
    if videos['videos']:
      return videos
    else:
      return {"status": "success", "message": "No non viewed video"}

  def search_youtube_channels(self, query, max_results=None):
    """
    Search for YouTube channels based on a query term.
    Inspired by youtube_channel_search.py implementation.
    
    Args:
        query: Search term to find YouTube channels
        max_results: Maximum number of channels to return (default: 10, max: 20)
    
    Returns:
        List of channels with name, description, and channel_id
    """
    if not query or not query.strip():
      return {"status": "error", "message": "Search query cannot be empty"}
    
    # Set default value if not provided
    if max_results is None:
      max_results = 10
    
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
      
      logger.info(f"Found {len(channels)} channels for query: {query}")
      return {"status": "success", "channels": channels}
      
    except Exception as e:
      logger.error(f"Error searching YouTube channels: {e}")
      return {"status": "error", "message": f"Search failed: {str(e)}"}

  def _extract_channel_from_video(self, entry):
    """
    Extract channel information from a video entry.
    
    Args:
        entry: Video entry from search results
    
    Returns:
        Dictionary with channel information or None
    """
    try:
      # Extract channel info from video
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
      logger.error(f"Error extracting channel info: {e}")
      return None

  def _get_channel_about(self, channel_id):
    """
    Get the complete description (About) of a YouTube channel.
    
    Args:
        channel_id: YouTube channel ID (format UCxxxxxxxxx)
    
    Returns:
        Complete channel description or empty string
    """
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
      logger.error(f"Error getting channel description for {channel_id}: {e}")
    
    return ""

  def get_channel_recent_videos(self, channel_id, max_videos=15):
    """
    Get recent videos from a YouTube channel using RSS feed.
    
    Args:
        channel_id: YouTube channel ID (format UCxxxxxxx)
        max_videos: Maximum number of videos to return (default: 15)
    
    Returns:
        Dictionary with status and list of recent videos
    """
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
      
      if feed.bozo:
        logger.warning(f"RSS feed parsing warning for channel {channel_id}: {feed.bozo_exception}")
      
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
          logger.error(f"Error processing video entry: {e}")
          continue
      
      result = {
        'status': 'success',
        'channel': channel_info,
        'videos': videos,
        'total_videos': len(videos)
      }
      
      logger.info(f"Retrieved {len(videos)} videos from channel {channel_id}")
      return result
      
    except Exception as e:
      logger.error(f"Error fetching channel videos for {channel_id}: {e}")
      return {"status": "error", "message": f"Failed to fetch channel videos: {str(e)}"}
