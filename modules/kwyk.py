import requests
import json
import os
from bs4 import BeautifulSoup
import sqlite3

from datetime import datetime, timedelta

################################################################################################
#                                                                                              #
#                                           Kwyk                                               #
#                                                                                              #
################################################################################################
class Kwyk:

  def __init__(self, config) -> None:
    self.url = "https://www.kwyk.fr/"

    self.db = config['kwyk']['db']
    self.username = config['kwyk']['username']
    self.password = config['kwyk']['password']
    self.id = config['kwyk']['id']

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    # create the table `autonomous` if it does not exist
    cursor.execute('''
    create table if not exists autonomous (
        id integer primary key autoincrement,
        timestamp datetime default current_timestamp,
        correct integer,
        mcq integer,
        incorrect integer,
        total integer
    )
    ''')
    dbconn.commit()

    dbconn.close()

    self.update()

    self.tools = [
      {
        "type": "function",
        "description": "Get the Kwyk status. For example when a user aks 'How many kwyk exercises has been done today', 'What is the kwyk status', 'How many math exercise has been done today'. Returned data are incremental values. So to have the number of execercise done a day, you must take the day values and remove the previous day value. All figures are a total increment.",
        "function": {
            "name": "kwyk_get",
            "parameters": {},
        },
      },
    ]

    self.systemContext = "Kwyk is a math and french exercises plateform."


  def update(self):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    # Retrieve the most recent entry
    cursor.execute('SELECT timestamp FROM autonomous ORDER BY timestamp DESC LIMIT 1')
    timeentry = cursor.fetchone()

    if timeentry is not None:
      dateUpdate = datetime.strptime(timeentry[0], '%Y-%m-%d %H:%M:%S')
    else:
      dateUpdate = datetime.now() - timedelta(hours=24)

    if datetime.now() > (dateUpdate + timedelta(minutes=15)):

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

          cursor = dbconn.cursor()
          cursor.execute('''
          INSERT INTO autonomous (correct, mcq, incorrect, total) VALUES (?, ?, ?, ?)
          ''', (correct, mcq, incorrect, total))
          
          dbconn.commit()

          print("Kwyk DB Updated")

      dbconn.close()


  def get(self, *args, **kwargs):

    self.update()
    data = {"math": []}

    dbconn = sqlite3.connect(self.db)
    entries = dbconn.execute('SELECT timestamp, correct, mcq, incorrect, total FROM autonomous ORDER BY timestamp ASC')

    for entry in entries:
      data['math'].append({"timestamp": entry[0], "correct": entry[1], "mcq": entry[2], "incorrect": entry[3], "total": entry[4]})

    dbconn.close()

    return True, data




