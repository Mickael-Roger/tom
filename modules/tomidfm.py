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

      self.journeys = []

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
          "name": "search_station",
          "description": "Search for a metro, train, or tram station by name. Return a list of stations with the station identifier 'station_id,' the station name, the city the station is, and the metro, tram and train lines serving that station.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "search_name": {
                "type": "string",
                "description": f"String used to search for a station. Most of the time a name of a station.",
              },
            },
            "required": ["search_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "search_place_gps",
          "description": "Search for the GPS coordinates of a place, poi, address, or location. These GPS coordinates may be necessary to find a route.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "search_string": {
                "type": "string",
                "description": f"String used to search a position GPS for a place, a poi, address or lacation.",
              },
            },
            "required": ["search_string"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "plan_a_journey",
          "description": "Calculate a route using public transportation in Île-de-France (whether by train, metro, bus, or tram). GPS coordinates should only be used when the departure or arrival location is not a station.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "date": {
                "type": "string",
                "description": f"Departure date of the route. Must be in the form: 'YYYY-MM-DD hh:mm:ss'.",
              },
              "departure": {
                "type": "string",
                "description": f"Departure place of the journey to plan. Could be a station_id (That can be retreive using search_station) or a gps position (in the form of 'longitude;latitude'). By default, when a user says 'station x', you must use a 'station_id' value that can be retrieved via the 'search_station' function.",
              },
              "arrival": {
                "type": "string",
                "description": f"Arrival place of the journey to plan. Could be a station_id (That can be retreive using search_station) or a gps position (in the form of 'longitude;latitude'). By default, when a user says 'station x', you must use a 'station_id' value that can be retrieved via the 'search_station' function.",
              },
            },
            "required": ["date", "departure", "arrival"],
            "additionalProperties": False,
          },
        },
      },
#      {
#        "type": "function",
#        "function": {
#          "name": "list_train_lines",
#          "description": "List all train, metro and tram lines. For each line, this function returns the line_id, the line name and a the line type (metro, train or tram).",
#          "parameters": {
#          },
#        },
#      },
#      {
#        "type": "function",
#        "function": {
#          "name": "list_train_station_lines",
#          "description": "List all available lines in a station",
#          "strict": True,
#          "parameters": {
#            "type": "object",
#            "properties": {
#              "station_id": {
#                "type": "string",
#                "description": f"ID of the train station. It's a station_id value that could be retreive using list_train_stations function.",
#              },
#            },
#            "required": ["station_id"],
#            "additionalProperties": False,
#          },
#        },
#      },
#      {
#        "type": "function",
#        "function": {
#          "name": "get_train_schedule",
#          "description": "Get the train, tramway or subway schedule. For a departure station, this function will return a list of all scheduling trains, metro and trams per line with all stops. Use this function when the user prompt ask for train, tramway or subway scheduling information. For example when a user ask 'What are the next train from x to y', 'When are the train from x to y on monday'",
#          "strict": True,
#          "parameters": {
#            "type": "object",
#            "properties": {
#              "date": {
#                "type": "string",
#                "description": f"Scheduling starting date in the form 'YYYY-MM-DD hh:mm:ss'",
#              },
#              "departure_station_id": {
#                "type": "string",
#                "description": f"Departure train station_id. It's a station_id value that could be retreive using list_train_stations function.",
#              },
#            },
#            "required": ["date", "departure_station_id"],
#            "additionalProperties": False,
#          },
#        }
#      },
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
    self.complexity = 1

    self.functions = {
      "search_station": {
        "function": functools.partial(self.search_station), 
        "responseContext": "" 
      },
      "search_place_gps": {
        "function": functools.partial(self.search_place_gps), 
        "responseContext": "" 
      },
      "plan_a_journey": {
        "function": functools.partial(self.journey), 
        "responseContext": "" 
      },
#      "list_train_station_lines": {
#        "function": functools.partial(self.get_station_lines), 
#        "responseContext": "" 
#      },
#      "get_train_schedule": {
#        "function": functools.partial(self.schedule), 
#        "responseContext": "" 
#      },
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


  def search_station(self, search_name):

    params = {
      "q": search_name,
      "type": "stop_area",
      "disable_geojson": True
    }
    
    results = self.apiCall(f"/places", params=params)

    if results == False:
      return False

    list_stations = {}

    search_stations=[]
    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()

    # Get all station IDs
    cursor.execute('SELECT id, city from stations')
    
    stations = cursor.fetchall()
    dbconn.close()


    for station in stations:
      list_stations[station[0]] = station[1]

    for place in results['places']:
      id=place['id'].replace("stop_area:IDFM:", "")
      # Just get the train, tram and metro stations
      if id in list_stations.keys():
        current_lines = []

        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        cursor.execute('SELECT lines.id, lines.commercial_name FROM lines, station_line WHERE line_id=lines.id AND station_id=?', (id,))
        lines = cursor.fetchall()
        dbconn.close()

        for line in lines:
          current_lines.append({"line_id": line[0], "line_name": line[1]})

        search_stations.append({"station_id": id, "station_name": place['stop_area']['name'], "lines": current_lines})

    return search_stations



  def search_place_gps(self, search_string):

    params = {
      "q": search_string,
      "disable_geojson": True
    }
    
    results = self.apiCall(f"/places", params=params)

    if results == False:
      return False

    places = []

    for place in results['places']:
      if place['embedded_type'] in ['address', 'poi']:
        if place['embedded_type'] == 'poi':
          ref = place['poi']
          place_type = place['poi']['poi_type']['name']
        elif place['embedded_type'] == 'stop_area': 
          ref = place['stop_area']
          place_type = "Station"
        else:
          ref = place['address']
          place_type = 'address'

        gps_lon = ref['coord']['lon']
        gps_lat = ref['coord']['lat']

        city = ""

        for reg in ref['administrative_regions']:
          if reg["level"] == 8:
            city = reg["name"]
            break


        places.append({"place_name": place['name'], "city": city, "place_type": place_type, "gps_lat": gps_lat, "gps_lon": gps_lon })

    return places





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



  def journey(self, date, departure, arrival):

    if ';' not in departure:
      departure = f"stop_area:IDFM:{departure}"
    if ';' not in arrival:
      arrival = f"stop_area:IDFM:{arrival}"

    params = {
      "from": departure,
      "to": arrival,
      "datetime": self.date_to_idfm(date),
      "datetime_represents": "departure"
    }


    result = self.apiCall("/journeys", params=params)

    self.journeys = []
    i = 0

    if result == False:
      return False

    for journey in result['journeys']:
      duration = journey["duration"]
      nb_transfers = journey["nb_transfers"]
      departure_date_time = self.date_from_idfm(journey["departure_date_time"])
      arrival_date_time = self.date_from_idfm(journey["arrival_date_time"])

      sections = []
      
      for section in journey['sections']:
        if section['type'] == 'waiting':
          section_duration = section['duration']
          sections.append({"section_type": "waiting", "section_duration_in_seconds": section_duration})
        else:
          section_duration = section['duration']
          section_departure_date_time = self.date_from_idfm(section["departure_date_time"])
          section_arrival_date_time = self.date_from_idfm(section["arrival_date_time"])
          section_from = section["from"]["name"] 
          section_to = section["to"]["name"] 
          section_type = ""
          if 'mode' in section.keys():
            section_type = section["mode"] 
          if 'display_informations' in section.keys():
            section_type = section['display_informations']['physical_mode'] + " " + section['display_informations']['label']
          if section_duration > 0:
            sections.append({"section_type": section_type, "section_duration_in_seconds": section_duration, "section_from": section_from, "section_to": section_to, "section_departure_datetime": section_departure_date_time, "section_arrival_datetime": section_arrival_date_time})

      self.journeys.append({"id": i, "departure_datetime": departure_date_time, "arrival_datetime": arrival_date_time, "duration_in_seconds": duration, "nb_transfers": nb_transfers, "sections": sections})
      i = i+1

    print(self.journeys)

    return self.journeys




  def apiCall(self, url, params=None):

    uri = self.url + url
    headers = { "apiKey": self.apiKey, "accept": "application/json" }
    resp = requests.get(uri, headers=headers, params=params)
    
    if resp.status_code == 200:
      return resp.json()
    else:
      print(resp.status_code)
      print(resp.text)
      return False



  def date_to_idfm(self, date):
    return datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M%S")


  def date_from_idfm(self, date):
    return datetime.strptime(date, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M:%S")








  def disruption(self, line):
    trainid = self.lines[line]['id']
    val = self.apiCall(f"/lines/line:IDFM:{trainid}")

    if val:
      print(val['disruptions'])
      return val['disruptions']
    else:
      print("Error while calling line info: " + str(val))
      return False





















  #def schedule(self, date, departure_station_id):

  #  schedules = []

  #  # Get all lines of a station

  #  dbconn = sqlite3.connect(self.db)
  #  cursor = dbconn.cursor()
  #  cursor.execute('SELECT lines.id, lines.commercial_name, station_id FROM lines, station_line, stations WHERE line_id=lines.id AND station_id=stations.id AND (station_id=? OR stations.name=?)', (departure_station_id, departure_station_id,))
  #  
  #  lines = cursor.fetchall()
  #  dbconn.close()


  #  for line in lines:
  #    line_id = line[0]
  #    line_name = line[1]
  #    departure_station_id = line[2]


  #    params = {
  #      "from_datetime": self.date_to_idfm(date), 
  #      "count": 50,
  #      "filter": f"line.id=line:IDFM:{line_id}",
  #      "duration": 3600 * 2
  #    }

  #    departures = self.apiCall(f"/stop_areas/stop_area:IDFM:{departure_station_id}/departures", params=params)

  #    if departures == False:
  #      return False

  #    for departure in departures.get("departures", []):
  #      route_id = departure["route"]["id"] if "route" in departure else "Unknown"
  #      departure_station_name = departure["stop_point"].get("name", "Unknown")
  #      departure_station_id = departure["stop_point"]["stop_area"].get("id", "Unknown")
  #      departure_datetime = self.date_from_idfm(departure['stop_date_time']['departure_date_time'])


  #      # Endpoint et paramètres
  #      params = {
  #        "from_datetime": self.date_to_idfm(date), 
  #      }

  #      
  #      # Requête API
  #      route_schedules = self.apiCall(f"/routes/{route_id}/route_schedules", params=params)

  #      if route_schedules == False:
  #        return False

  #      stops = []

  #      store=0
  #      for schedule in route_schedules.get("route_schedules", []):
  #        for stop in schedule.get("table", {}).get("rows", []):
  #          if store == 1:
  #            if stop['date_times'][0]['date_time']:
  #              stop_datetime = self.date_from_idfm(stop['date_times'][0]['date_time'])
  #            else:
  #              stop_datetime = None
  #            stops.append({"station_name": stop['stop_point']['name'], "stop_datetime": stop_datetime})
  #                                    
  #          if departure_station_name == stop['stop_point']['name']:
  #            store = 1
  #            
  #      schedules.append({"line_id": line_id, "line_name": line_name, "departure_datetime": departure_datetime, "stops": stops})

  #  print(schedules)

  #  return schedules


