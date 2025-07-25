import feedparser
from datetime import datetime
import time
import functools
import sqlite3
import threading
import time
import os
import sys

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
        viewed BOOLEAN DEFAULT 0
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
    ]

    self.systemContext = '''
    The function 'mark_video_as_seen' is used in 3 scenarios:
       - When the user has already wtached the video and wants to remove it from the non viewed video list.
       - When the user ask to mark as seen a video
       - When the user is not interested in watching this video and does not plan to watch it, but still wants to mark it as seen to declutter the non viewed video list.
    '''
    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "get_all_new_videos": {
        "function": functools.partial(self.list_unviewed_videos)
      },
      "mark_video_as_seen": {
        "function": functools.partial(self.mark_video_as_viewed)
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
            cursor.execute("INSERT INTO videos (video_id, channel_id, channel_name, publication, title, uri) VALUES (?, ?, ?, ?, ?, ?) ", (video['id'], id, name, datetime.fromtimestamp(time.mktime(video['published_parsed'])).strftime("%Y-%m-%d %H:%M:%S"), video['title'], video['link']))
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
    cursor.execute("SELECT id, channel_name, title, uri  FROM videos WHERE viewed = 0")
    allvideos = cursor.fetchall()
    dbconn.close()

    videos = {"videos": []}

    for video in allvideos:
      id = video[0]
      channel = video[1]
      title = video[2]
      uri = video[3]

      videos['videos'].append({"video_id": id, "channel": channel, "title": title, "url": uri, "viewed": False})

    logger.debug(videos)
    
    if videos['videos']:
      return videos
    else:
      return {"status": "success", "message": "No non viewed video"}
