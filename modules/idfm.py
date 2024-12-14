from more_itertools import one
import requests
import json
import os

from datetime import datetime, timedelta, date

################################################################################################
#                                                                                              #
#                                           IDFM                                               #
#                                                                                              #
################################################################################################
class Idfm:

  def __init__(self, config) -> None:


    self.url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    self.apiKey = config['token']

    self.listLines = ["1", "2", "3", "4", "5", "6", "7", "7bis", "8", "9", "10", "11", "12", "13", "14", "T1", "T2", "T3a", "T3b", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13", "A", "B", "C", "D", "E", "H", "J", "K", "L", "N", "P", "R", "U", "V"]

    self.lines = {}

    res = requests.get('https://data.iledefrance-mobilites.fr/explore/dataset/referentiel-des-lignes/download/?format=json&timezone=Europe/Berlin&lang=fr')
    if res.status_code == 200:
      lines = res.json()
      for line in lines:
        if line['fields']['transportmode'] in ("metro", "rail", "tram"):
          if line['fields']['name_line'] in self.listLines:
            self.lines[line['fields']['name_line']] = { "id":line['fields']['id_line'], "type": line['fields']['transportmode'] }


    # Instanciate a list of station ID
    self.stations = {}
    self.listStations = []

    res = requests.get('https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/emplacement-des-gares-idf-data-generalisee/exports/json?lang=fr&timezone=Europe%2FBerlin')
    if res.status_code == 200:
      stations = res.json()
      for station in stations:
        self.stations[station['nom_zdc']] = { "id": station['id_ref_zdc'] }

    for station in self.stations:
      self.listStations.append(station)



    self.tools = [
      {
        "type": "function",
        "description": "Get the train, tramway or subway schedule. Use this function when the user prompt ask for train, tramway or subway scheduling information. For example when a user ask 'What are the next train from x to y', 'When are the train from x to y on monday'",
        "function": {
          "name": "get_train_schedule",
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Scheduling date in the form 'yyyy-mm-dd'",
              },
              "line": {
                "type": "string",
                "enum": self.listLines, 
                "description": f"Name of the line. 1,2,3,4,5,6,7,7bis,8,9,10,11,12,13,14 are subway lines. T1,T2,T3a,T3b,T4,T5,T6,T7,T8,T9,T10,T11,T12,T13 are tramway lines. A,B,C,D,E,H,J,K,L,N,P,R,U,V are train lines.",
              },
              "origin": {
                "type": "string",
                "enum": self.listStations,
                "description": f"Departure station.",
              },
              "destination": {
                "type": "string",
                "enum": self.listStations,
                "description": f"Arrival station",
              },
            },
            "required": ["date", "line", "origin", "destination"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "description": "Public transportation journey planner (train, subway, tramway and buses). Use this function when the user prompt ask for a public transportation journey plannification. For example when a user ask 'I\'d like to go to x from y', 'What is the best path for going to x by train'",
        "function": {
          "name": "get_train_planner",
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Scheduling date in the form 'yyyy-mm-dd'",
              },
              "origin": {
                "type": "string",
                "enum": self.listStations,
                "description": f"Departure station.",
              },
              "destination": {
                "type": "string",
                "enum": self.listStations,
                "description": f"Arrival station",
              },
            },
            "required": ["date", "origin", "destination"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "description": "Get the train, tramway or subway disturbance. Use this function when the user prompt ask for train, tramway or subway disturbance information. For example 'Is there any incident in line X', 'Is there any disturbance on train line A', 'Is the any disturbance at the train station y'",
        "function": {
          "name": "get_train_disruption",
          "parameters": {
            "type": "object",
            "properties": {
              "line": {
                "type": "string",
                "enum": self.listLines, 
                "description": f"Name of the line. 1,2,3,4,5,6,7,7bis,8,9,10,11,12,13,14 are subway lines. T1,T2,T3a,T3b,T4,T5,T6,T7,T8,T9,T10,T11,T12,T13 are tramway lines. A,B,C,D,E,H,J,K,L,N,P,R,U,V are train lines.",
              },
            },
            "required": ["line"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""


  def apiCall(self, url):

    uri = self.url + url
    headers = { "apiKey": self.apiKey, "accept": "application/json" }
    resp = requests.get(uri, headers=headers)
    
    if resp.status_code == 200:
      return True, resp.json()
    else:
      return False, resp.status_code



  def disruption(self, line):
    trainid = self.lines[line]['id']
    ret, val = self.apiCall(f"/lines/line:IDFM:{trainid}")

    if ret:
      print(val['disruptions'])
      return True, val['disruptions']
    else:
      print("Error while calling line info: " + str(val))
      return False, "Error while calling line info: " + str(val)



  def schedule(self, date, line, origin, destination):

    lineid = self.lines[line]['id']
    originid = self.stations[origin]['id']
    destinationid = self.stations[destination]['id']
    ret, val = self.apiCall(f"/lines/line:IDFM:{lineid}/stop_schedules")

    print("==================")
    print(val)
    print("==================")

    print(date, line, origin, destination)
    print("Date: " + str(date))
    print("Line: " + str(line) + " - " + str(self.lines[line]['id']))
    print("From: " + str(origin) + " - " + str(self.stations[origin]['id']))
    print("To: " + str(destination) + " - " + str(self.stations[destination]['id']))


  def planner(self, date, origin, destination):
    print(date, origin, destination)
    print("Date: " + str(date))
    print("From: " + str(origin) + " - " + str(self.stations[origin]['id']))
    print("To: " + str(destination) + " - " + str(self.stations[destination]['id']))



