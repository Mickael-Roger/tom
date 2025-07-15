import requests
import json
import sqlite3

from datetime import datetime, timedelta, date
import functools
import copy

################################################################################################
#                                                                                              #
#                                           IDFM                                               #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "idfm",
  "class_name": "TomIdfm",
  "description": "This module is used for getting public transportation information.",
  "type": "global"
}

class TomIdfm:

  _already_updated = False

  def __init__(self, config, llm) -> None:

    self.url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    self.apiKey = config['token']
    self.db =  config['cache_db']

    self.route = None
    self.routes = []

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
      {
        "type": "function",
        "function": {
          "name": "select_a_route",
          "description": "Used only after calling the 'plan_a_journey' function. If the user is interested in taking one of the suggested routes, this function allows the desired route to be stored in the current route. The stored route can then be used to guide the user during their journey. For example, this is used after a journey calculation request (via the 'plan_a_journey' function) when the user indicates they want to take the proposed route. For instance: 'OK, I willl take this route' or 'Alright, I will go with this one, guide me.'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "route_id": {
                "type": "integer",
                "description": f"ID of the route to keep. The 'route_id' come from a result of 'plan_a_journey' function call.",
              },
            },
            "required": ["route_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "retreived_current_selected_route",
          "description": "Retrieve detailed information about the current journey. This allows you to get the information of the journey chosen by the user, for instance, if it's not in the prompt history. It can be used in situations like: 'I am here, what's the next step of my journey?' or 'Okay, resume the guidance of my route.'",
          "parameters": {
            "type": "object",
            "properties": {
            },
            "additionalProperties": False,
          },
        },
      },
    ]



    self.systemContext = ""
    self.complexity = 1

    self.functions = {
      "search_station": {
        "function": functools.partial(self.search_station)
      },
      "search_place_gps": {
        "function": functools.partial(self.search_place_gps)
      },
      "plan_a_journey": {
        "function": functools.partial(self.journey)
      },
      "select_a_route": {
        "function": functools.partial(self.keep_route)
      },
      "retreived_current_selected_route": {
        "function": functools.partial(self.retreive_keeped_route)
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
          section_best_boarding = None
          if 'mode' in section.keys():
            section_type = section["mode"] 
          if 'display_informations' in section.keys():
            section_type = section['display_informations']['physical_mode'] + " " + section['display_informations']['label']
          if 'best_boarding_positions' in section.keys():
            section_best_boarding = section['best_boarding_positions'][0]
          if section_duration > 0:
            sections.append({"section_type": section_type, "section_duration_in_seconds": section_duration, "section_from": section_from, "section_to": section_to, "section_departure_datetime": section_departure_date_time, "section_arrival_datetime": section_arrival_date_time, "section_best_boarding_position": section_best_boarding})

      self.routes.append({"route_id": i, "departure_datetime": departure_date_time, "arrival_datetime": arrival_date_time, "duration_in_seconds": duration, "nb_transfers": nb_transfers, "sections": sections})
      i = i+1

    print(self.routes)

    return self.routes



  def keep_route(self, route_id):
    self.route = copy.deepcopy(self.routes[route_id])
    print(self.route)
    return {"status": "success", "message": "Route kept"}


  def retreive_keeped_route(self):
    return self.route




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