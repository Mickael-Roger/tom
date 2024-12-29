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

            city = self.get_city(latitude=line['geo_point_2d']['lat'], longitude=line['geo_point_2d']['lon'])

            if city != False:
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
          "name": "list_train_lines",
          "description": "List all train, metro and tram lines. For each line, this function returns the line_id, the line name and a the line type (metro, train or tram).",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "list_train_station_lines",
          "description": "List all available lines in a station",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "station_id": {
                "type": "string",
                "description": f"ID of the train station. It's a station_id value that could be retreive using list_train_stations function.",
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
          "description": "Get the train, tramway or subway schedule. For a departure station, this function will return a list of all scheduling trains, metro and trams per line with all stops. Use this function when the user prompt ask for train, tramway or subway scheduling information. For example when a user ask 'What are the next train from x to y', 'When are the train from x to y on monday'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Scheduling starting date in the form 'YYYY-MM-DD hh:mm:ss'",
              },
              "departure_station_id": {
                "type": "string",
                "description": f"Departure train station_id. It's a station_id value that could be retreive using list_train_stations function.",
              },
            },
            "required": ["date", "departure_station_id"],
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
      "list_train_lines": {
        "function": functools.partial(self.list_lines), 
        "responseContext": "" 
      },
      "list_train_station_lines": {
        "function": functools.partial(self.get_station_lines), 
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

      return city
    else:
      return False



  def list_stations(self):

    try:

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

      return list_stations
    except:
      return False


  def list_lines(self):

    try:

      list_lines = []

      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute('SELECT id, commercial_name, type FROM lines')
      lines = cursor.fetchall()
      dbconn.close()


      for line in lines:
        line_id = line[0]
        line_name = line[1]
        line_type = line[2]

        list_lines.append({"line_id": line_id, "line_name": line_name, "line_type": line_type})

      return lines
    except:
      return False




  def get_station_lines(self, station_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT lines.id, lines.commercial_name, station_id FROM lines, station_line, stations WHERE line_id=lines.id AND station_id=stations.id AND (station_id=? OR stations.name=?)', (station_id, station_id,))
    
    lines = cursor.fetchall()
    dbconn.close()


    if lines:
      station_lines = []
      for line in lines:
        station_lines.append({"line_id": line[0], "line_name": line[1]})

      print(station_lines)
      print("************")
      return station_lines
    else:
      return False




  def apiCall(self, url, params=None):

    uri = self.url + url
    headers = { "apiKey": self.apiKey, "accept": "application/json" }
    resp = requests.get(uri, headers=headers, params=params)
    
    if resp.status_code == 200:
      return resp.json()
    else:
      return False



  def date_to_idfm(self, date):
    return datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M%S")


  def date_from_idfm(self, date):
    return datetime.strptime(date, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M:%S")



  def schedule(self, date, departure_station_id):

    schedules = []

    # Get all lines of a station

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT lines.id, lines.commercial_name, station_id FROM lines, station_line, stations WHERE line_id=lines.id AND station_id=stations.id AND (station_id=? OR stations.name=?)', (departure_station_id, departure_station_id,))
    
    lines = cursor.fetchall()
    dbconn.close()


    for line in lines:
      line_id = line[0]
      line_name = line[1]
      departure_station_id = line[2]


      params = {
        "from_datetime": self.date_to_idfm(date), 
        "count": 50,
        "filter": f"line.id=line:IDFM:{line_id}",
        "duration": 3600 * 2
      }

      departures = self.apiCall(f"/stop_areas/stop_area:IDFM:{departure_station_id}/departures", params=params)

      if departures == False:
        return False

      for departure in departures.get("departures", []):
        route_id = departure["route"]["id"] if "route" in departure else "Unknown"
        departure_station_name = departure["stop_point"].get("name", "Unknown")
        departure_station_id = departure["stop_point"]["stop_area"].get("id", "Unknown")
        departure_datetime = self.date_from_idfm(departure['stop_date_time']['departure_date_time'])


        # Endpoint et paramètres
        params = {
          "from_datetime": self.date_to_idfm(date), 
        }

        
        # Requête API
        route_schedules = self.apiCall(f"/routes/{route_id}/route_schedules", params=params)

        if route_schedules == False:
          return False

        stops = []

        store=0
        for schedule in route_schedules.get("route_schedules", []):
          for stop in schedule.get("table", {}).get("rows", []):
            if store == 1:
              if stop['date_times'][0]['date_time']:
                stop_datetime = self.date_from_idfm(stop['date_times'][0]['date_time'])
              else:
                stop_datetime = None
              stops.append({"station_name": stop['stop_point']['name'], "stop_datetime": stop_datetime})
                                      
            if departure_station_name == stop['stop_point']['name']:
              store = 1
              
        schedules.append({"line_id": line_id, "line_name": line_name, "departure_datetime": departure_datetime, "stops": stops})

    print(schedules)

    return schedules


  def journey(self, departure, arrival, journey_datetime):

    params = {
      "from": departure,
      "to": arrival,
      "date_time": journey_datetime,
      "max_nb_journeys": 3,
      "results": 5
    }

    # Requête API
    journeys = self.apiCall(f"/journeys", params=params)

    if journeys == False:
      return False

    print("Journey options:")
    for journey in journeys.get("journeys", []):
      print(f"Journey {journey['duration']} seconds")
      for section in journey.get("sections", []):
        print(section.keys())
        print(f"  - {section['from']['name']} to {section['to']['name']}")


























  def disruption(self, line):
    trainid = self.lines[line]['id']
    val = self.apiCall(f"/lines/line:IDFM:{trainid}")

    if val:
      print(val['disruptions'])
      return val['disruptions']
    else:
      print("Error while calling line info: " + str(val))
      return False



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



