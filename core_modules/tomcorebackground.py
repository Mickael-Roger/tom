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
    self.msg = ""

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
      #self.llm_synthesis(self.tasks)
      self.msg = self.llm_synthesis(self.tasks)
      self.status_id = int(time.time())

    self.last_update = int(time.time())


  def llm_synthesis(self, tasks):

    llm_consign = []

    context = """The user has an application running in the background that retrieves information or performs useful tasks for the user. Each module can provide relevant information to the user. For example, the 'news' module informs the user about the number of unread articles, or the 'weather' module can notify about an upcoming weather event.

    You are an agent to which the user will send a JSON array. Each module with information to report will add an entry to the JSON array. The JSON format is as follows:
    ```json
    "module": MODULE_NAME,
    "status": INFORMATION_USEFUL_FOR_THE_USER
    ```

    If there is no new information for a module, do not mention it in your response and do not say anything about that module.

    Your task is to synthesize the content of this JSON into a short and intelligible sentence.

    If the array is empty, you should respond with an empty message.
    Your answer must be in french and you must address me informally
    """

    llm_consign.append({"role": "system", "content": context})
    llm_consign.append({"role": "user", "content": json.dumps(tasks)})

    response = self.llm.callLLM(llm_consign, llm='mistral')

    if response:
      print(response.choices[0].message.content)
      return response.choices[0].message.content
    else:
      return ""









