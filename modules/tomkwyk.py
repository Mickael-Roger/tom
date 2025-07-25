import requests
import json
import os
from bs4 import BeautifulSoup
import sqlite3
import threading
import random
import time

from datetime import datetime, timedelta, date
import functools

# Logging
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

################################################################################################
#                                                                                              #
#                                           Kwyk                                               #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "kwyk",
  "class_name": "TomKwyk",
  "description": "This module is used to get information from Kwyk. Kwyk is an online platform for math and French exercises.",
  "type": "global",
  "complexity": 0,
  "configuration_parameters": {
    "username": {
      "type": "string",
      "description": "Username for Kwyk platform authentication",
      "required": True
    },
    "password": {
      "type": "string",
      "description": "Password for Kwyk platform authentication",
      "required": True
    },
    "id": {
      "type": "string",
      "description": "User ID for accessing Kwyk autonomous exercise statistics",
      "required": True
    }
  }
}

class TomKwyk:

  _update_thread_started = False

  def __init__(self, config, llm) -> None:
    self.url = "https://www.kwyk.fr/"

    # Generate cache database path from all_datadir + module name
    all_datadir = config.get('all_datadir', '/data/all/')
    os.makedirs(all_datadir, exist_ok=True)
    self.db = os.path.join(all_datadir, 'kwyk.sqlite')
    
    self.username = config['username']
    self.password = config['password']
    self.id = config['id']


    self.lastUpdate = datetime.now() - timedelta(hours=24)

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    # create the table `autonomous` if it does not exist
    cursor.execute('''
    create table if not exists autonomous (
        date date default current_date,
        daycorrect integer,
        daymcq integer,
        dayincorrect integer,
        daytotal integer,
        fullcorrect integer,
        fullmcq integer,
        fullincorrect integer,
        fulltotal integer
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "kwyk_get",
          "description": "Get the Kwyk status. For example when a user aks 'How many kwyk exercises has been done today', 'What is the kwyk status', 'How many math exercise has been done today'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "period_from": {
                "type": "string",
                "description": f"Must be in the form of '%Y-%m-%d'. Define the starting date to search for. Oldest starting date is '2020-01-01'.",
              },
              "period_to": {
                "type": "string",
                "description": f"Must be in the form of '%Y-%m-%d'. Define the ending date to search for. Maximum ending date is today.",
              },
            },
            "required": ["period_from", "period_to"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""
    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "kwyk_get": {
        "function": functools.partial(self.get)
      },
    }



    if not TomKwyk._update_thread_started:
      TomKwyk._update_thread_started = True
      self.thread = threading.Thread(target=self.run_update)
      self.thread.daemon = True  # Allow the thread to exit when the main program exits
      self.thread.start()
    

  def run_update(self):
    while True:
      time.sleep(random.randint(3, 10) * 3600)
      logger.info("Kwyk: Run auto update")
      self.update()



  def update(self):

      session = requests.Session()

      headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Referer': 'https://www.kwyk.fr/', 'Origin': 'https://www.kwyk.fr', 'X-Requested-With': 'XMLHttpRequest', 'DNT': '1', 'Sec-GPC': '1', 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-origin', 'TE': 'trailers'}

      response = session.get('https://www.kwyk.fr/')

      soup = BeautifulSoup(response.text, 'html.parser')
      csrf_token_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
      csrf_token = csrf_token_input.get('value')
      
      data = {'csrfmiddlewaretoken': csrf_token, 'login': self.username, 'password': self.password}

      headers['Referer'] = f'https://www.kwyk.fr/bilan/{self.id}/onglets/autonomie/student/'
      response2=session.post('https://www.kwyk.fr/accounts/login/', data=data, headers=headers, allow_redirects=False)

      if response2.status_code == 200:
        autonomousStatus = session.get(f'https://www.kwyk.fr/bilan/{self.id}/onglets/autonomie/student/', headers=headers, allow_redirects=False)

        if autonomousStatus.status_code == 200:
          # Convert the JSON response to a dictionary
          data = autonomousStatus.json()
          correct = data['instances_done_autonomous']['correct']
          mcq = data['instances_done_autonomous']['mcq']
          incorrect = data['instances_done_autonomous']['incorrect']
          total = data['instances_done_autonomous']['total']

          dbconn = sqlite3.connect(self.db)
          cursor = dbconn.cursor()

          today = date.today().isoformat()

          cursor.execute('''
          DELETE FROM autonomous WHERE date = ? 
          ''', (today,))
          
          dbconn.commit()

          cursor = dbconn.cursor()
          cursor.execute("SELECT fullcorrect, fullmcq, fullincorrect, fulltotal FROM autonomous WHERE date < DATE('now') ORDER BY date DESC LIMIT 1")
          lastValues = cursor.fetchone()

          if lastValues:
            daycorrect = correct - lastValues[0]
            daymcq = mcq - lastValues[1]
            dayincorrect = incorrect - lastValues[2]
            daytotal = total - lastValues[3]
          else:
            daycorrect = correct
            daymcq = mcq
            dayincorrect = incorrect
            daytotal = total

          cursor.execute('''
          INSERT INTO autonomous (fullcorrect, fullmcq, fullincorrect, fulltotal, daycorrect, daymcq, dayincorrect, daytotal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          ''', (correct, mcq, incorrect, total, daycorrect, daymcq, dayincorrect, daytotal))
          
          dbconn.commit()

          self.lastUpdate = datetime.now()
          logger.info("Kwyk DB Updated")

          dbconn.close()


  def get(self, period_from, period_to):

    self.update()


    
    dbconn = sqlite3.connect(self.db)
    entries = dbconn.execute('SELECT date, daycorrect, daymcq, dayincorrect, daytotal FROM autonomous WHERE date BETWEEN ? AND ? ORDER BY date ASC', (period_from, period_to))

    # Initialize sums for each exercise type
    total_correct = 0
    total_mcq = 0
    total_incorrect = 0
    total_exercises = 0

    for entry in entries:
      total_correct += entry[1]
      total_mcq += entry[2] 
      total_incorrect += entry[3]
      total_exercises += entry[4]

    dbconn.close()

    # Create aggregated response
    data = {
      "period": {
        "start_date": period_from,
        "end_date": period_to,
      },
      "math": {
        "correct_exercises": total_correct,
        "mcq_exercises": total_mcq,
        "incorrect_exercises": total_incorrect,
        "total_exercises": total_exercises
      }
    }

    logger.debug(data)

    return data
