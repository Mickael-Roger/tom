import requests
import json
import os
from bs4 import BeautifulSoup
import sqlite3
import threading
import random
import time

from datetime import datetime, timedelta, date

################################################################################################
#                                                                                              #
#                                           Kwyk                                               #
#                                                                                              #
################################################################################################
class Kwyk:

  def __init__(self, config) -> None:
    self.url = "https://www.kwyk.fr/"

    self.db = config['db']
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

    self.update()

    self.tools = [
      {
        "type": "function",
        "description": "Get the Kwyk status. For example when a user aks 'How many kwyk exercises has been done today', 'What is the kwyk status', 'How many math exercise has been done today'",
        "function": {
            "name": "kwyk_get",
            "parameters": {},
        },
      },
    ]

    self.systemContext = "Kwyk is a math and french exercises plateform."

    self.thread = threading.Thread(target=self.run_update)
    self.thread.daemon = True  # Allow the thread to exit when the main program exits
    self.thread.start()
    
  def run_update(self):
    while True:
      print("Kwyk: Run auto update")
      self.update()
      time.sleep(random.randint(3, 12) * 3600)



  def update(self):


    if datetime.now() > (self.lastUpdate + timedelta(minutes=15)):

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
          print("Kwyk DB Updated")

          dbconn.close()


  def get(self, *args, **kwargs):

    self.update()
    data = {"math": []}

    dbconn = sqlite3.connect(self.db)
    entries = dbconn.execute('SELECT date, daycorrect, daymcq, dayincorrect, daytotal FROM autonomous ORDER BY date ASC')

    for entry in entries:
      data['math'].append({"date": entry[0], "correct_exercices": entry[1], "mcq_exercices": entry[2], "incorrect_exercices": entry[3], "total_exercices": entry[4]})

    print(data)

    dbconn.close()

    return True, data




