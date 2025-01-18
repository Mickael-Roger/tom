import sqlite3
import os
import functools
import threading
import time
import json

################################################################################################
#                                                                                              #
#                              Background tasks capability                                     #
#                                                                                              #
################################################################################################
class TomBackground:

  def __init__(self, global_config, username, services) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "tasks.sqlite")

    self.username = username

    self.services = services

    self.tasks = []

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        last_update DATETIME default current_date,
        module TEXT,
        status TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.thread = threading.Thread(target=self.run_update)
    self.thread.daemon = True  # Allow the thread to exit when the main program exits
    self.thread.start()
    
  def run_update(self):
    while True:
      #try:
      self.background_tasks_status()
      #except:
      #  print("Could not update background tasks")
      time.sleep(10)


  def background_tasks_status(self):
    self.tasks = []

    for service in self.services:
      if hasattr(self.services[service]['obj'], 'background_status'):
        if self.services[service]['obj'].background_status:
          self.tasks.append({"module": service, "status": self.services[service]['obj'].background_status})





