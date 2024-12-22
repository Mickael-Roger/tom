import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, quote
import re
import sqlite3

from datetime import datetime, timedelta, date


################################################################################################
#                                                                                              #
#                                         Cafetariat                                           #
#                                                                                              #
################################################################################################
class TomCafetaria:

  def __init__(self, config) -> None:

    self.url = 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152'
    self.username = config['username']
    self.password = config['password']
    self.db = config['cache_db']

    self.lastUpdate = datetime.now() - timedelta(hours=48)

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
    self.answerContext = {
      "get_cafetaria_credit": "",
      "list_cafetaria_reservations": "",
      "make_a_cafetaria_reservation": "",
      "cancel_a_cafetaria_reservation": "",
    }

  def update(self):

    session = requests.Session()
    
    data = {
      "txtLogin": self.username,
      "txtMdp": self.password,
      "y": "19"
    }


    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Referer': 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 'Origin': 'https://webparent.paiementdp.com'}


    session.get('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152')
    resp_main = session.post('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', data=data, headers=headers)

    if resp_main.status_code == 200:
      soup = BeautifulSoup(resp_main.text, 'html.parser')
      solde = soup.find('label', {'for': 'CLI_ID'}).get_text()

      dbconn = sqlite3.connect(self.db)
      dbconn.execute("""DELETE FROM solde""")
      dbconn.execute("""INSERT INTO solde (solde) VALUES (?)""", (solde,))
      dbconn.commit()
      dbconn.close()


    resp_res_main = session.get('https://webparent.paiementdp.com/aliReservation.php')

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

    session.get('https://webparent.paiementdp.com/aliDeconnexion.php')



  def change_reservation(self, action, id):


    id=quote(id)

    print("========")
    print(action)
    print("========")
    print(id)
    print("========")
    

    session = requests.Session()
    
    data = {
      "txtLogin": self.username,
      "txtMdp": self.password,
      "y": "19"
    }


    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Referer': 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 'Origin': 'https://webparent.paiementdp.com'}


    session.get('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152')
    session.post('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', data=data, headers=headers)

    if action == "cancel":

      cancel_page = session.get(f"https://webparent.paiementdp.com/aliReservationCancel.php?date={id}", headers=headers)

      if cancel_page.status_code != 200:
        return False, "Cannot update reservation"

      headers['Referer'] = f"https://webparent.paiementdp.com/aliReservationCancel.php?date={id}"

      values = {
        "ref": "cancel",
        "btnOK.x": 42,
        "btnOK.y": 25,
        "valide_form": 1
      }

      cancel = session.post('https://webparent.paiementdp.com/aliReservationCancel.php', headers=headers, data=values)

      if cancel.status_code != 200:
        return False, "Cannot update reservation"

      self.update()

      return True, "Reservation canceled"


    if action == "add":

      add_page = session.get(f"https://webparent.paiementdp.com/aliReservationDetail.php?date={id}", headers=headers)

      print("========")
      print(add_page.text)
      print("========")

      if add_page.status_code != 200:
        return False, "Cannot update reservation"

      headers['Referer'] = f"https://webparent.paiementdp.com/aliReservationDetail.php?date={id}"

      values = {
        "CONS_QUANTITE": 1,
        "restaurant": 1,
        "btnOK.x": 69,
        "btnOK.y": 19,
        "valide_form": 1
      }

      add = session.post('https://webparent.paiementdp.com/aliReservationDetail.php', headers=headers, data=values)

      if add.status_code != 200:
        return False, "Cannot update reservation"

      print("========")
      print(add_page.text)
      print("========")

      session.get('https://webparent.paiementdp.com/aliDeconnexion.php')
      
      self.update()

      return True, "Reservation created"



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
        return True, f"{date} already reserved"
      else:
        return self.change_reservation(action="add", id=id)

    else:
      return False, "Could not find ID"



  def cancel(self, date):

    self.update();

    resa = self.find_date(date)

    if resa:
      res = resa[0]
      id = res[0]
      is_reserved = res[1]

      if is_reserved:
        return self.change_reservation(action="cancel", id=id)
      else:
        return True, f"{date} was not reserved"

    else:
      return False, "Could not find ID"



    



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

    return True, resas




  def credit(self):
    if datetime.now() > (self.lastUpdate + timedelta(days=1)):
      self.update()
    
    dbconn = sqlite3.connect(self.db)
    res = dbconn.execute("""SELECT solde FROM solde""").fetchone()
    dbconn.commit()
    dbconn.close()

    if res:
      return True, res[0]
    
    return False, "Could not get the credit left"
    




