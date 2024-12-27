import requests
import json
import sqlite3

from datetime import datetime, timedelta, date
import functools

################################################################################################
#                                                                                              #
#                                           IDFM                                               #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "idfm",
  "class_name": "TomIdfm",
  "description": "This module is used for getting public transportation information."
}

class TomIdfm:

  _already_updated = False

  def __init__(self, config) -> None:

    self.url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    self.apiKey = config['token']
    self.db =  config['cache_db']

    if not TomIdfm._already_updated:
      TomIdfm._already_updated = True
    
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute('''
      create table if not exists stations (
          id TEXT PRIMARY KEY,
          name TEXT,
          latitude NUMERIC,
          longitude NUMERIC,
          city TEXT        
      )
      ''')
      cursor.execute('''
      create table if not exists lines (
          id TEXT PRIMARY KEY,
          name TEXT,
          commercial_name TEXT,
          type TEXT
      )
      ''')
      cursor.execute('''
      create table if not exists station_line (
          line_id TEXT NOT NULL,
          station_id TEXT NOT NULL,
          PRIMARY KEY (line_id, station_id)
      )
      ''')
      dbconn.commit()
      dbconn.close()

      # Update data in DB
      res = requests.get('https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/emplacement-des-gares-idf/exports/json')
      if res.status_code == 200:
        
        lines = res.json()

        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        cursor.execute('SELECT id from stations')
        
        station_ids = []
        ids = cursor.fetchall()

        for id in ids:
          station_ids.append(str(id[0]))


        cursor.execute('SELECT id from lines')
        
        lines_ids = []
        ids = cursor.fetchall()

        for id in ids:
          lines_ids.append(str(id[0]))

        for line in lines:

          station_id = str(line['id_ref_zdc'])
          # Verify if station ID is already in the DB, if not, find its city and add it. Do that to minimize the geocoding number of calls
          if station_id not in station_ids:

            res, city = self.get_city(latitude=line['geo_point_2d']['lat'], longitude=line['geo_point_2d']['lon'])

            if res:
              cursor.execute('INSERT INTO stations (id, name, latitude, longitude, city) VALUES (?, ?, ?, ?, ?)', (station_id, line['nom_zdc'], line['geo_point_2d']['lat'], line['geo_point_2d']['lon'], city))
              dbconn.commit()
              station_ids.append(station_id) # Avoid issue with duplicated IDs


          line_id = str(line['idrefligc'])
          # Add the line if not already in the DB
          if line_id not in lines_ids:
            mode = line['mode']
            if mode == "RER":
              mode = "TRAIN"
            elif mode == "VAL":
              mode = "METRO"

            cursor.execute('INSERT INTO lines (id, name, commercial_name, type) VALUES (?, ?, ?, ?)', (line_id, str(line['indice_lig']), line['res_com'], mode))
            dbconn.commit()
            lines_ids.append(line_id) # Avoid issue with duplicated IDs


          # Add the relation station-line if not already
          cursor.execute('INSERT OR REPLACE INTO station_line (line_id, station_id) VALUES (?, ?)', (line_id, station_id))
          dbconn.commit()

        dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "list_train_stations",
          "description": "List all train, metro and tram stations. For each station, this function returns the station_id, the station name and a list of all the metro, train, and tram lines for this station.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_train_station_information",
          "description": "Get information about a train station. For a train, subway or tram station, this function returns its ID, name, city and all the lines of the station",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "station_id": {
                "type": "string",
                "description": f"ID of the station.",
              },
            },
            "required": ["station_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_train_schedule",
          "description": "Get the train, tramway or subway schedule. Use this function when the user prompt ask for train, tramway or subway scheduling information. For example when a user ask 'What are the next train from x to y', 'When are the train from x to y on monday'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Scheduling starting date in the form 'YYYY-MM-DD hh:mm:ss'",
              },
              "line_id": {
                "type": "string",
                "description": f"ID of the train, subway or tram line.",
              },
              "departure_station_id": {
                "type": "string",
                "description": f"Departure train station ID.",
              },
              "arrival_station_id": {
                "type": "string",
                "description": f"Arrival train station ID.",
              },
            },
            "required": ["date", "line_id", "departure_station_id", "arrival_station_id"],
            "additionalProperties": False,
          },
        }
      },
#      {
#        "type": "function",
#        "description": "Public transportation journey planner (train, subway, tramway and buses). Use this function when the user prompt ask for a public transportation journey plannification. For example when a user ask 'I\'d like to go to x from y', 'What is the best path for going to x by train'",
#        "function": {
#          "name": "get_train_planner",
#          "parameters": {
#            "type": "object",
#            "properties": {
#              "date": {
#                "type": "string",
#                "description": f"Scheduling date in the form 'yyyy-mm-dd'",
#              },
#              "origin": {
#                "type": "string",
#                "enum": self.listStations,
#                "description": f"Departure station.",
#              },
#              "destination": {
#                "type": "string",
#                "enum": self.listStations,
#                "description": f"Arrival station",
#              },
#            },
#            "required": ["date", "origin", "destination"],
#            "additionalProperties": False,
#          },
#        }
#      },
#      {
#        "type": "function",
#        "description": "Get the train, tramway or subway disturbance. Use this function when the user prompt ask for train, tramway or subway disturbance information. For example 'Is there any incident in line X', 'Is there any disturbance on train line A', 'Is the any disturbance at the train station y'",
#        "function": {
#          "name": "get_train_disruption",
#          "parameters": {
#            "type": "object",
#            "properties": {
#              "line": {
#                "type": "string",
#                "enum": self.listLines, 
#                "description": f"Name of the line. 1,2,3,4,5,6,7,7bis,8,9,10,11,12,13,14 are subway lines. T1,T2,T3a,T3b,T4,T5,T6,T7,T8,T9,T10,T11,T12,T13 are tramway lines. A,B,C,D,E,H,J,K,L,N,P,R,U,V are train lines.",
#              },
#            },
#            "required": ["line"],
#            "additionalProperties": False,
#          },
#        },
#      },
    ]


#    self.journey(departure='stop_area:IDFM:73731', arrival='2.3051858276889905;48.846734773306885', journey_datetime='20241226T110000')

    self.systemContext = ""

    self.functions = {
      "list_train_stations": {
        "function": functools.partial(self.list_stations), 
        "responseContext": "" 
      },
      "get_train_station_information": {
        "function": functools.partial(self.get_station), 
        "responseContext": "" 
      },
      "get_train_schedule": {
        "function": functools.partial(self.schedule), 
        "responseContext": "" 
      },
    }




  def get_city(self, latitude, longitude):
    latitude = str(latitude)
    longitude = str(longitude)
    resp = requests.get(f"https://api-adresse.data.gouv.fr/reverse/?lon={longitude}&lat={latitude}&limit=1")
    
    if resp.status_code == 200:
      result = resp.json()
      if result['features']:
        city = result['features'][0]['properties']['city']
      else:
        city = ""

      return True, city
    else:
      return False, resp.status_code



  def list_stations(self):

    list_stations = []

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT id, name, city from stations')
    
    stations = cursor.fetchall()

    dbconn.close()

    for station in stations:
      station_id = station[0]
      station_name = station[1]
      station_city = station[2]
      list_stations.append({"station_id": station_id, "station_name": station_name, "station_city": station_city})

    return True, list_stations



  def get_station(self, station_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT id, name, city from stations WHERE id = ?', (station_id,))
    
    station = cursor.fetchone()
    station_id = station[0]
    station_name = station[1]
    station_city = station[2]

    cursor.execute('SELECT lines.id, lines.name, lines.commercial_name, lines.type FROM lines, station_line WHERE lines.id=station_line.line_id AND station_line.station_id = ?', (station_id, ))
    lines = cursor.fetchall()

    dbconn.close()


    stations_lines = []
    for line in lines:
      stations_lines.append({"line_id": line[0], "line_name": line[1], "line_commercial_name": line[2], "line_type": line[3]})

    return True, {"station_id": station_id, "station_name": station_name, "station_city": station_city, "lines": stations_lines}


  def apiCall(self, url, params=None):

    uri = self.url + url
    headers = { "apiKey": self.apiKey, "accept": "application/json" }
    resp = requests.get(uri, headers=headers, params=params)
    
    if resp.status_code == 200:
      return True, resp.json()
    else:
      return False, resp.status_code

  def date_to_idfm(self, date):
    return datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M%S")


  def date_from_idfm(self, date):
    return datetime.strptime(date, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M:%S")



  def schedule(self, date, line_id, departure_station_id, arrival_station_id):

    params = {
      "from_datetime": self.date_to_idfm(date), 
      "count": 50,
      "filter": f"line.id=line:IDFM:{line_id}",
      "duration": 3600 * 3
    }

    ret, departures = self.apiCall(f"/stop_areas/stop_area:IDFM:{departure_station_id}/departures", params=params)

    if ret == False:
      return False, "Could not get departures"


    schedules = []

    for departure in departures.get("departures", []):
      route_id = departure["route"]["id"] if "route" in departure else "Unknown"
      departure_station_name = departure["stop_point"].get("name", "Unknown")
      departure_station_id = departure["stop_point"]["stop_area"].get("id", "Unknown")
      final_destination_station_name = departure["route"]["direction"]["stop_area"].get("name", "Unknown")
      departure_datetime = self.date_from_idfm(departure['stop_date_time']['departure_date_time'])
      line_name = departure['display_informations']['label']


      # Endpoint et paramètres
      params = {
        "from_datetime": self.date_to_idfm(date), 
      }

      
      # Requête API
      ret, route_schedules = self.apiCall(f"/routes/{route_id}/route_schedules", params=params)

      if ret == False:
        return False, "Could not get routes"

      stops = []

      good_direction=0

      store=0
      for schedule in route_schedules.get("route_schedules", []):
        for stop in schedule.get("table", {}).get("rows", []):
          if store == 1:
            if stop['date_times'][0]['date_time']:
              stop_datetime = self.date_from_idfm(stop['date_times'][0]['date_time'])
            else:
              stop_datetime = None
            stops.append({"station_name": stop['stop_point']['name'], "stop_datetime": stop_datetime})
            if stop['stop_point']['stop_area']['id'] == f"stop_area:IDFM:{arrival_station_id}":
              store=0
              good_direction=1
                                    
          if departure_station_name == stop['stop_point']['name']:
            store = 1
            
      if good_direction == 1:
        schedules.append({"departure_station_id": departure_station_id, "departure_station_name": departure_station_name, "final_destination_station_name": final_destination_station_name, "line_id": line_id, "line_name": line_name, "departure_datetime": departure_datetime,"stops": stops})

    return True, schedules


  def journey(self, departure, arrival, journey_datetime):

    params = {
      "from": departure,
      "to": arrival,
      "date_time": journey_datetime,
      "max_nb_journeys": 3,
      "results": 5
    }

    # Requête API
    ret, journeys = self.apiCall(f"/journeys", params=params)

    if ret == False:
      return False, f"Could not get routes: {journeys.status_code}"

    print("Journey options:")
    for journey in journeys.get("journeys", []):
      print(f"Journey {journey['duration']} seconds")
      for section in journey.get("sections", []):
        print(section.keys())
        print(f"  - {section['from']['name']} to {section['to']['name']}")


























  def disruption(self, line):
    trainid = self.lines[line]['id']
    ret, val = self.apiCall(f"/lines/line:IDFM:{trainid}")

    if ret:
      print(val['disruptions'])
      return True, val['disruptions']
    else:
      print("Error while calling line info: " + str(val))
      return False, "Error while calling line info: " + str(val)



#  def schedule(self, date, line, origin, destination):
#
#    lineid = self.lines[line]['id']
#    originid = self.stations[origin]['id']
#    destinationid = self.stations[destination]['id']
#    ret, val = self.apiCall(f"/lines/line:IDFM:{lineid}/stop_schedules")
#
#    print("==================")
#    print(val)
#    print("==================")
#
#    print(date, line, origin, destination)
#    print("Date: " + str(date))
#    print("Line: " + str(line) + " - " + str(self.lines[line]['id']))
#    print("From: " + str(origin) + " - " + str(self.stations[origin]['id']))
#    print("To: " + str(destination) + " - " + str(self.stations[destination]['id']))


  def planner(self, date, origin, destination):
    print(date, origin, destination)
    print("Date: " + str(date))
    print("From: " + str(origin) + " - " + str(self.stations[origin]['id']))
    print("To: " + str(destination) + " - " + str(self.stations[destination]['id']))



