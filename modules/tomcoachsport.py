from datetime import datetime
import sqlite3
import threading
import time
import functools
import os
import sys

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger


################################################################################################
#                                                                                              #
#                                      Sport coach                                             #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "sport_coach",
  "class_name": "TomSportcoach",
  "description": "This module allows you to act as the user's personal fitness coach. Use it for any questions they might ask their sports coach.",
  "type": "personal",
  "complexity": 1
}

class TomSportcoach:

  def __init__(self, config, llm) -> None:

    self.db = config['cache_db']

    self.llm = llm

    self.background_status = None # {"ts": int(time.time()), "status": None}

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default CURRENT_TIMESTAMP,
        role TEXT,
        content TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "get_sport_history",
          "description": "Return the activity history, instructions, and sport advice.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "record_sport_history",
          "description": "",
          "parameters": {
            "type": "object",
            "properties": {
              "role": {
                "type": "string",
                "enum": ["coach", "user"],
                "description": f"",
              },
              "message": {
                "type": "string",
                "description": f"",
              },
            },
            "required": ["role", "message"],
            "additionalProperties": False,
          },
        },
      },

    ]

    self.systemContext = """
    You are a professional and motivational fitness coach with extensive knowledge in sports science, nutrition, and mental health. Your role is to guide me through my fitness journey by creating personalized workout plans, offering tips for proper technique, suggesting nutrition strategies, and providing encouragement. You should adapt your advice based on my goals, fitness level, and progress, while always being supportive and motivating. When I share updates about my workouts or challenges, respond constructively, offer adjustments if necessary, and keep me motivated to stay consistent and reach my goals.

    To fulfill your role as the user's fitness coach, you have access to two functions:

    - `get_sport_history`
    - `record_sport_history`

    The `get_sport_history` function allows you to retrieve all previous interactions you've had with the user as their fitness coach. This function returns a JSON in the following format (containing a list of past exchanges with the user):

    ```json
    {"sport_history": [{"date": "YYYY-MM-DD hh:mm", "role": "ROLE", "message": "CONTENT_MESSAGE"}]}
    ```

    ROLE: Indicates who wrote the "content" message. This role can be:
    - "coach": You, as the coach
    - "user": The user

    To keep track of important information and interactions between you (as the fitness coach) and the user, you must use the record_sport_history function. It is very important to maintain a comprehensive and coherent context of your coaching relationship with the user over time. For example, if the user tells you they’ve been running, walking, cycling, etc., you must record this information using the record_sport_history function. Similarly, keep track of discussions about the user's training questions and your responses on the subject.

    You must log all elements that seem relevant to your role as a fitness coach using this function.

    Feel free to ask for additional information if necessary. For example, if the user tells you they’ve been running, don’t hesitate to ask for details suchs as the distance, duration, difficulty, terrain type, etc.

    If, as a fitness coach, you don’t have enough information from the history of your interactions, don’t hesitate to ask the user for clarification (while making sure to record both your questions and the user’s answers using the record_sport_history function).

    If the history of your interactions with the user is empty or nearly empty, it means you are just starting your role as the user's fitness coach. In this case, before doing anything as a sport coach, you must begin by asking all the necessary questions to ensure you can perform your role effectively (e.g., age, weight, medical history, fitness level, goals, etc.).

    It is very important that during exchanges with the user, after each message you receive from the user in your role as a fitness coach, you must, before sending your response, record both their message and your response using the `record_sport_history` function. Only then should you send your response.
    """


    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "get_sport_history": {
        "function": functools.partial(self.get_history)
      },
      "record_sport_history": {
        "function": functools.partial(self.record_history)
      },
    }


    #self.thread = threading.Thread(target=self.thread_update)
    #self.thread.daemon = True  # Allow the thread to exit when the main program exits
    #self.thread.start()
    

  def get_history(self):

    history = []

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT datetime, role, content FROM history ORDER BY datetime ASC")
    values = cursor.fetchall()
    dbconn.close()


    if values:
      for val in values:
        history.append({"date": val[0], "role": val[1], "message": val[2]})

    logger.debug(history)

    return {"sport_history": history}





  #def thread_update(self):
  #  self.news_update()
  #  while True:
  #  #    try:
  #  #      logger.info("Update news ...")
  #  #      self.news_update()
  #  #    except:
  #  #      logger.error("Fail to update RSS")

  #    time.sleep(300)




  def record_history(self, role, message):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, message))
    dbconn.commit()
    dbconn.close()

    return {"status": "success", "message": "Message added to the sport_history"}
