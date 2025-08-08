from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, quote
import re
import sqlite3
import functools
import json
import threading
import time

from datetime import datetime, timedelta, date
import os
import sys

# Logging and HTTP helper
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger
from tomhttphelper import TomHttpHelper


################################################################################################
#                                                                                              #
#                                         Cafetariat                                           #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "cafetaria",
  "class_name": "TomCafetaria",
  "description": "This module is used to manage the use of the school cafeteria, such as reserving or canceling a cafeteria meal or checking the remaining credit.",
  "type": "global",
  "complexity": 0,
  "configuration_parameters": {
    "username": {
      "type": "string",
      "description": "Username for school cafeteria payment system authentication",
      "required": True
    },
    "password": {
      "type": "string",
      "description": "Password for school cafeteria payment system authentication",
      "required": True
    }
  }
}

class TomCafetaria:

  _update_thread_started = False

  def __init__(self, config, llm) -> None:

    self.url = 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152'
    self.username = config['username']
    self.password = config['password']
    
    # Generate cache database path from all_datadir + module name
    all_datadir = config.get('all_datadir', '/data/all/')
    os.makedirs(all_datadir, exist_ok=True)
    self.db = os.path.join(all_datadir, 'cafetaria.sqlite')

    self.lastUpdate = datetime.now() - timedelta(hours=48)

    self.background_status = {"ts": int(time.time()), "status": None}

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    # create the table `autonomous` if it does not exist
    cursor.execute('''
    create table if not exists cafetaria (
        date DATETIME PRIMARY KEY,
        id TEXT,
        is_reserved BOOLEAN
    )
    ''')
    cursor.execute('''
    create table if not exists solde (
        solde TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()


    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "get_cafetaria_credit",
          "description": "Get the high school cafetaria credit. For example when a user aks 'How much cafeteria credit do I have?'",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "list_cafetaria_reservations",
          "description": "List the high school cafetaria reservations. For example when a user aks 'Is the cafetaria reserved for this day?'. This function provides high school cafetaria reservations information.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "make_a_cafetaria_reservation",
          "description": "Make a reservation for high school cafetaria. For example when a user aks 'Book the high school cafetaria for tomorrow'. This function does not provide any resevation information. Must only be used when the user explicitly ask for making a new reservation.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Day you want to make a cafetaria reservation. Must be in the form of '%Y-%m-%d'. Date is always in the futur. So ",
              },
            },
            "required": ["date"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "cancel_a_cafetaria_reservation",
          "description": "Cancel a reservation for high school cafetaria. For example when a user aks 'Cancel the high school cafetaria reservation for tomorrow'. This function does not provide any resevation information.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Day you want to cancel the cafetaria reservation. Must be in the form of '%Y-%m-%d'. Date is always in the futur.",
              },
            },
            "required": ["date"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""
    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "get_cafetaria_credit": {
        "function": functools.partial(self.credit)
      },
      "list_cafetaria_reservations": {
        "function": functools.partial(self.reservations)
      },
      "make_a_cafetaria_reservation": {
        "function": functools.partial(self.add)
      },
      "cancel_a_cafetaria_reservation": {
        "function": functools.partial(self.cancel)
      },
    }


    if not TomCafetaria._update_thread_started:
      TomCafetaria._update_thread_started = True
      self.thread = threading.Thread(target=self.run_update)
      self.thread.daemon = True  # Allow the thread to exit when the main program exits
      self.thread.start()
    

  def run_update(self):
    while True:
      time.sleep(3600)
      logger.info("Cafetaria: Run auto update", module_name="cafetaria")
      time_diff = datetime.now() - self.lastUpdate
      if time_diff > timedelta(hours=48):
        self.update()


  def update(self):
    
    data = {
      "txtLogin": self.username,
      "txtMdp": self.password,
      "y": "19"
    }

    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Referer': 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 'Origin': 'https://webparent.paiementdp.com'}

    with TomHttpHelper("cafetaria", default_timeout=30) as http_helper:
      try:
        http_helper.get('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152')
        resp_main = http_helper.post('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', data=data, headers=headers)

        if resp_main.status_code == 200:
          soup = BeautifulSoup(resp_main.text, 'html.parser')
          solde = soup.find('label', {'for': 'CLI_ID'}).get_text()

          dbconn = sqlite3.connect(self.db)
          dbconn.execute("""DELETE FROM solde""")
          dbconn.execute("""INSERT INTO solde (solde) VALUES (?)""", (solde,))
          dbconn.commit()
          dbconn.close()

          pattern = r"(\d+,\d+)"
          match = re.search(pattern, solde)
          if match:
            amount_str = match.group(1)
            amount = float(amount_str.replace(',', '.'))

            if amount < 10.0:
              status = f"Only {amount} euros left on cafetaria credit"
            else:
              status = None

            if status != self.background_status['status']:
              self.background_status['ts'] = int(time.time())
              self.background_status['status'] = status

          else:
            logger.error("Could not extract cafetaria credit", module_name="cafetaria")

        resp_res_main = http_helper.get('https://webparent.paiementdp.com/aliReservation.php')

        soup2 = BeautifulSoup(resp_res_main.text, 'html.parser')

        pattern = re.compile(r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$')

        tds = soup2.find_all('td', id=pattern)

        resas = []

        for td in tds:
          day = td.get('id')
          links = td.find_all('a')
          if links:
            link = links[0].get('href')
            parsed_url = urlparse(link)
            query_params = parse_qs(parsed_url.query)

            id = query_params.get('date', [None])[0]
            path = parsed_url.path

            if path == "aliReservationCancel.php":
              reserved = True
            elif path == "aliReservationDetail.php":
              reserved = False
            else:
              reserved = None

            if reserved is not None:
              resas.append({"day": day, "id": id, "is_reserved": reserved})

        for resa in resas:
          dbconn = sqlite3.connect(self.db)
          dbconn.execute("""
            INSERT OR REPLACE INTO cafetaria (date, id, is_reserved) VALUES (?, ?, ?)
            """, (resa['day'], resa['id'].rstrip(), resa['is_reserved']))
          dbconn.commit()
          dbconn.close()

        http_helper.get('https://webparent.paiementdp.com/aliDeconnexion.php')

        self.lastUpdate = datetime.now()
        logger.info("Cafetaria updated successfully", module_name="cafetaria")
        
      except Exception as e:
        logger.error(f"Failed to update cafetaria data: {str(e)}", module_name="cafetaria")
        return



  def change_reservation(self, action, id):

    id=quote(id)
    
    data = {
      "txtLogin": self.username,
      "txtMdp": self.password,
      "y": "19"
    }

    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Referer': 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 'Origin': 'https://webparent.paiementdp.com'}

    with TomHttpHelper("cafetaria", default_timeout=30) as http_helper:
      try:
        http_helper.get('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152')
        http_helper.post('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', data=data, headers=headers)

        if action == "cancel":

          cancel_page = http_helper.get(f"https://webparent.paiementdp.com/aliReservationCancel.php?date={id}", headers=headers)

          if cancel_page.status_code != 200:
            return False

          headers['Referer'] = f"https://webparent.paiementdp.com/aliReservationCancel.php?date={id}"

          values = {
            "ref": "cancel",
            "btnOK.x": 42,
            "btnOK.y": 25,
            "valide_form": 1
          }

          cancel = http_helper.post('https://webparent.paiementdp.com/aliReservationCancel.php', headers=headers, data=values)

          if cancel.status_code != 200:
            return False

          self.update()

          return True

        if action == "add":

          add_page = http_helper.get(f"https://webparent.paiementdp.com/aliReservationDetail.php?date={id}", headers=headers)

          if add_page.status_code != 200:
            return False

          headers['Referer'] = f"https://webparent.paiementdp.com/aliReservationDetail.php?date={id}"

          values = {
            "CONS_QUANTITE": 1,
            "restaurant": 1,
            "btnOK.x": 69,
            "btnOK.y": 19,
            "valide_form": 1
          }

          add = http_helper.post('https://webparent.paiementdp.com/aliReservationDetail.php', headers=headers, data=values)

          if add.status_code != 200:
            return False

          http_helper.get('https://webparent.paiementdp.com/aliDeconnexion.php')
          
          self.update()

          return True
          
      except Exception as e:
        logger.error(f"Failed to change reservation: {str(e)}", module_name="cafetaria")
        return False



  def find_date(self, date):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("""SELECT id, is_reserved FROM cafetaria WHERE date = ?""", (date,))
    entries = cursor.fetchall()
    dbconn.close()

    return entries


  def add(self, date):

    self.update();

    resa = self.find_date(date)

    if resa:
      res = resa[0]
      id = res[0]
      is_reserved = res[1]

      if is_reserved:
        return {"status": "success", "message": "Reservation was already done"}
      else:
        ret = self.change_reservation(action="add", id=id)
        if ret == True:
          return {"status": "success", "message": "Reservation done"}
        else:
          return {"status": "failure", "message": "Could not make the reservation"}

    else:
      return False



  def cancel(self, date):

    self.update();

    resa = self.find_date(date)

    if resa:
      res = resa[0]
      id = res[0]
      is_reserved = res[1]

      if is_reserved:
        ret = self.change_reservation(action="cancel", id=id)
        if ret == True:
          return {"status": "success", "message": "Reservation canceled"}
        else:
          return {"status": "failure", "message": "Could not cancel the reservation"}
      else:
        return {"status": "success", "message": "Reservation was already canceled"}

    else:
      return False



    



  def reservations(self):
    if datetime.now() > (self.lastUpdate + timedelta(hours=12)):
      self.update();

    resas = []

    today = date.today().strftime("%Y-%m-%d")

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("""SELECT date, id, is_reserved FROM cafetaria WHERE date >= ?""", (today,))
    entries = cursor.fetchall()
    dbconn.close()

    for entry in entries:
      resas.append({"date": entry[0], "id": entry[1], "is_reserved": entry[2]})

    return resas




  def credit(self):
    if datetime.now() > (self.lastUpdate + timedelta(days=1)):
      self.update()
    
    dbconn = sqlite3.connect(self.db)
    res = dbconn.execute("""SELECT solde FROM solde""").fetchone()
    dbconn.commit()
    dbconn.close()

    if res:
      return res[0]
    
    return False
