import sqlite3
import os
import functools
import threading
import time
import json
import tomlogger

################################################################################################
#                                                                                              #
#                              Background tasks capability                                     #
#                                                                                              #
################################################################################################
class TomBackground:

  def __init__(self, global_config, username, services, llm) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "tasks.sqlite")

    self.username = username

    self.services = services

    self.llm = llm

    self.tasks = []
    self.last_update = 0
    self.status_id = 0

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

    update_msg= False

    for service in self.services:
      if hasattr(self.services[service]['obj'], 'background_status'):
        if self.services[service]['obj'].background_status:
          if self.services[service]['obj'].background_status['status']:
            self.tasks.append({"module": service, "status": self.services[service]['obj'].background_status['status']})
          if self.services[service]['obj'].background_status['ts'] > self.last_update:
            update_msg = True

    if update_msg == True:
      self.status_id = int(time.time())

    self.last_update = int(time.time())











