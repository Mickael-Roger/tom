#!/usr/bin/env python3
"""
IDFM MCP Server
Provides Île-de-France Mobilités public transportation information via MCP protocol
Based on the original tomidfm.py module
"""

import json
import os
import sys
import yaml
import sqlite3
import copy
import requests
import functools
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional, List

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 IDFM MCP Server starting with log level: {log_level}", module_name="idfm")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for getting public transportation information in Île-de-France (metro, train, bus, tram)."

# Initialize FastMCP server
server = FastMCP(name="idfm-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = '/data/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration from {config_path}", module_name="idfm")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="idfm")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="idfm")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class IdfmService:
    """IDFM service class based on original TomIdfm"""
    
    _already_updated = False
    
    def __init__(self, config: Dict[str, Any]):
        # Load idfm configuration from config
        idfm_config = config.get('idfm', {})
        
        # Validate required config fields
        if 'token' not in idfm_config:
            raise KeyError("Missing required idfm config field: token")
        
        self.url = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
        self.apiKey = idfm_config['token']
        
        # Store database in /data/ directory
        self.db = '/data/idfm.sqlite'
        
        self.route = None
        self.routes = []
        
        # Initialize database and load data
        self._init_database()
        self._update_database()
        
        # Load station cache
        self.station_cache = self._load_station_cache()
        
        if tomlogger:
            tomlogger.info("✅ IDFM service initialized successfully", module_name="idfm")
    
    def _init_database(self):
        """Initialize the SQLite database"""
        try:
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
            
            cursor.execute('''
            create table if not exists station_cache (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                city TEXT
            )
            ''')
            
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info("Database initialized successfully", module_name="idfm")
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing database: {str(e)}", module_name="idfm")
            raise
    
    def _update_database(self):
        """Update database with station and line data"""
        if IdfmService._already_updated:
            return
        
        IdfmService._already_updated = True
        
        try:
            if tomlogger:
                tomlogger.info("Updating IDFM database with station and line data", module_name="idfm")
            
            # Get station data from Île-de-France open data
            res = requests.get('https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/emplacement-des-gares-idf/exports/json')
            if res.status_code != 200:
                if tomlogger:
                    tomlogger.warning(f"Failed to fetch station data: HTTP {res.status_code}", module_name="idfm")
                return
            
            lines = res.json()
            
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            
            # Get existing station and line IDs
            cursor.execute('SELECT id from stations')
            station_ids = set(str(row[0]) for row in cursor.fetchall())
            
            cursor.execute('SELECT id from lines')
            lines_ids = set(str(row[0]) for row in cursor.fetchall())
            
            for line in lines:
                station_id = str(line['id_ref_zdc'])
                
                # Add station if not exists
                if station_id not in station_ids:
                    city = self._get_city(latitude=line['geo_point_2d']['lat'], longitude=line['geo_point_2d']['lon'])
                    
                    if city:
                        cursor.execute('INSERT INTO stations (id, name, latitude, longitude, city) VALUES (?, ?, ?, ?, ?)', 
                                     (station_id, line['nom_zdc'], line['geo_point_2d']['lat'], line['geo_point_2d']['lon'], city))
                        dbconn.commit()
                        station_ids.add(station_id)
                
                line_id = str(line['idrefligc'])
                
                # Add line if not exists
                if line_id not in lines_ids:
                    mode = line['mode']
                    if mode == "RER":
                        mode = "TRAIN"
                    elif mode == "VAL":
                        mode = "METRO"
                    
                    cursor.execute('INSERT INTO lines (id, name, commercial_name, type) VALUES (?, ?, ?, ?)', 
                                 (line_id, str(line['indice_lig']), line['res_com'], mode))
                    dbconn.commit()
                    lines_ids.add(line_id)
                
                # Add station-line relation
                cursor.execute('INSERT OR REPLACE INTO station_line (line_id, station_id) VALUES (?, ?)', 
                             (line_id, station_id))
                dbconn.commit()
            
            dbconn.close()
            
            if tomlogger:
                tomlogger.info("✅ IDFM database updated successfully", module_name="idfm")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating IDFM database: {str(e)}", module_name="idfm")
    
    def _get_city(self, latitude, longitude):
        """Get city name from GPS coordinates"""
        try:
            latitude = str(latitude)
            longitude = str(longitude)
            resp = requests.get(f"https://api-adresse.data.gouv.fr/reverse/?lon={longitude}&lat={latitude}&limit=1")
            
            if resp.status_code == 200:
                result = resp.json()
                if result['features']:
                    return result['features'][0]['properties']['city']
                return ""
            return ""
        except Exception:
            return ""
    
    def _load_station_cache(self):
        """Load station cache from database"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute('SELECT station_id, station_name, city FROM station_cache')
            rows = cursor.fetchall()
            dbconn.close()
            
            cache = {}
            for row in rows:
                cache[row[1].lower()] = {
                    "station_id": row[0],
                    "station_name": row[1],
                    "city": row[2] or ""
                }
            return cache
        except Exception:
            return {}
    
    def _save_station_to_cache(self, station_id, station_name, city=""):
        """Save a station to cache"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute('INSERT OR REPLACE INTO station_cache (station_id, station_name, city) VALUES (?, ?, ?)', 
                          (station_id, station_name, city))
            dbconn.commit()
            dbconn.close()
            
            # Update in-memory cache
            self.station_cache[station_name.lower()] = {
                "station_id": station_id,
                "station_name": station_name,
                "city": city
            }
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error saving station to cache: {e}", module_name="idfm")
    
    def _api_call(self, url, params=None):
        """Make API call to IDFM"""
        uri = self.url + url
        headers = {"apiKey": self.apiKey, "accept": "application/json"}
        
        try:
            resp = requests.get(uri, headers=headers, params=params)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                if tomlogger:
                    tomlogger.error(f"IDFM API error: {resp.status_code} - {resp.text}", module_name="idfm")
                return None
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"IDFM API call failed: {str(e)}", module_name="idfm")
            return None
    
    def _date_to_idfm(self, date_str):
        """Convert date string to IDFM format"""
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M%S")
    
    def _date_from_idfm(self, date_str):
        """Convert IDFM date format to standard format"""
        return datetime.strptime(date_str, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    
    def search_station(self, search_name: str) -> List[Dict[str, Any]]:
        """Search for a metro, train, or tram station by name"""
        if tomlogger:
            tomlogger.info(f"Searching for station: {search_name}", module_name="idfm")
        
        params = {
            "q": search_name,
            "type": "stop_area",
            "disable_geojson": True
        }
        
        results = self._api_call("/places", params=params)
        if not results:
            return []
        
        # Get station data from database
        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        cursor.execute('SELECT id, city from stations')
        stations = cursor.fetchall()
        dbconn.close()
        
        list_stations = {station[0]: station[1] for station in stations}
        search_stations = []
        
        for place in results['places']:
            station_id = place['id'].replace("stop_area:IDFM:", "")
            
            # Only include known stations
            if station_id in list_stations:
                # Get lines for this station
                dbconn = sqlite3.connect(self.db)
                cursor = dbconn.cursor()
                cursor.execute('SELECT lines.id, lines.commercial_name FROM lines, station_line WHERE line_id=lines.id AND station_id=?', (station_id,))
                lines = cursor.fetchall()
                dbconn.close()
                
                current_lines = [{"line_id": line[0], "line_name": line[1]} for line in lines]
                
                city = list_stations.get(station_id, "")
                station_name = place['stop_area']['name']
                
                # Save to cache
                cache_key = station_name.lower()
                if cache_key not in self.station_cache:
                    self._save_station_to_cache(station_id, station_name, city)
                
                search_stations.append({
                    "station_id": station_id,
                    "station_name": station_name,
                    "city": city,
                    "lines": current_lines
                })
        
        return search_stations
    
    def search_place_gps(self, search_string: str) -> List[Dict[str, Any]]:
        """Search for GPS coordinates of a place, poi, address, or location"""
        if tomlogger:
            tomlogger.info(f"Searching GPS for place: {search_string}", module_name="idfm")
        
        params = {
            "q": search_string,
            "disable_geojson": True
        }
        
        results = self._api_call("/places", params=params)
        if not results:
            return []
        
        places = []
        
        for place in results['places']:
            if place['embedded_type'] in ['address', 'poi', 'stop_area']:
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
                for reg in ref.get('administrative_regions', []):
                    if reg.get("level") == 8:
                        city = reg["name"]
                        break
                
                places.append({
                    "place_name": place['name'],
                    "city": city,
                    "place_type": place_type,
                    "gps_lat": gps_lat,
                    "gps_lon": gps_lon
                })
        
        return places
    
    def plan_journey(self, date: str, departure: str, arrival: str) -> List[Dict[str, Any]]:
        """Calculate a route using public transportation"""
        if tomlogger:
            tomlogger.info(f"Planning journey from {departure} to {arrival} on {date}", module_name="idfm")
        
        # Format departure and arrival
        if ';' not in departure:
            departure = f"stop_area:IDFM:{departure}"
        if ';' not in arrival:
            arrival = f"stop_area:IDFM:{arrival}"
        
        params = {
            "from": departure,
            "to": arrival,
            "datetime": self._date_to_idfm(date),
            "datetime_represents": "departure"
        }
        
        result = self._api_call("/journeys", params=params)
        if not result:
            return []
        
        self.routes = []
        
        for i, journey in enumerate(result['journeys']):
            duration = journey["duration"]
            nb_transfers = journey["nb_transfers"]
            departure_date_time = self._date_from_idfm(journey["departure_date_time"])
            arrival_date_time = self._date_from_idfm(journey["arrival_date_time"])
            
            sections = []
            
            for section in journey['sections']:
                if section['type'] == 'waiting':
                    section_duration = section['duration']
                    sections.append({
                        "section_type": "waiting",
                        "section_duration_in_seconds": section_duration
                    })
                else:
                    section_duration = section['duration']
                    section_departure_date_time = self._date_from_idfm(section["departure_date_time"])
                    section_arrival_date_time = self._date_from_idfm(section["arrival_date_time"])
                    section_from = section["from"]["name"]
                    section_to = section["to"]["name"]
                    section_type = ""
                    section_best_boarding = None
                    
                    if 'mode' in section:
                        section_type = section["mode"]
                    if 'display_informations' in section:
                        section_type = section['display_informations']['physical_mode'] + " " + section['display_informations']['label']
                    if 'best_boarding_positions' in section and section['best_boarding_positions']:
                        section_best_boarding = section['best_boarding_positions'][0]
                    
                    if section_duration > 0:
                        sections.append({
                            "section_type": section_type,
                            "section_duration_in_seconds": section_duration,
                            "section_from": section_from,
                            "section_to": section_to,
                            "section_departure_datetime": section_departure_date_time,
                            "section_arrival_datetime": section_arrival_date_time,
                            "section_best_boarding_position": section_best_boarding
                        })
            
            self.routes.append({
                "route_id": i,
                "departure_datetime": departure_date_time,
                "arrival_datetime": arrival_date_time,
                "duration_in_seconds": duration,
                "nb_transfers": nb_transfers,
                "sections": sections
            })
        
        return self.routes
    
    def select_route(self, route_id: int) -> Dict[str, str]:
        """Select a route from the planned journey"""
        if tomlogger:
            tomlogger.info(f"Selecting route {route_id}", module_name="idfm")
        
        if 0 <= route_id < len(self.routes):
            self.route = copy.deepcopy(self.routes[route_id])
            return {"status": "success", "message": "Route selected successfully"}
        else:
            return {"status": "error", "message": f"Invalid route_id: {route_id}"}
    
    def get_selected_route(self) -> Optional[Dict[str, Any]]:
        """Retrieve the currently selected route"""
        return self.route


# Load configuration and initialize idfm service
config = load_config()
idfm_service = IdfmService(config)


@server.tool()
def search_station(search_name: str) -> str:
    """Search for a metro, train, or tram station by name. Return a list of stations with the station identifier 'station_id,' the station name, the city the station is, and the metro, tram and train lines serving that station.
    
    Args:
        search_name: String used to search for a station. Most of the time a name of a station.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: search_station with search_name={search_name}", module_name="idfm")
    
    result = idfm_service.search_station(search_name)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def search_place_gps(search_string: str) -> str:
    """Search for the GPS coordinates of a place, poi, address, or location. These GPS coordinates may be necessary to find a route.
    
    Args:
        search_string: String used to search a position GPS for a place, a poi, address or location.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: search_place_gps with search_string={search_string}", module_name="idfm")
    
    result = idfm_service.search_place_gps(search_string)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def plan_a_journey(date: str, departure: str, arrival: str) -> str:
    """Calculate a route using public transportation in Île-de-France (whether by train, metro, bus, or tram). GPS coordinates should only be used when the departure or arrival location is not a station.
    
    Args:
        date: Departure date of the route. Must be in the form: 'YYYY-MM-DD hh:mm:ss'.
        departure: Departure place of the journey to plan. Could be a station_id (That can be retrieved using search_station) or a gps position (in the form of 'longitude;latitude'). By default, when a user says 'station x', you must use a 'station_id' value that can be retrieved via the 'search_station' function.
        arrival: Arrival place of the journey to plan. Could be a station_id (That can be retrieved using search_station) or a gps position (in the form of 'longitude;latitude'). By default, when a user says 'station x', you must use a 'station_id' value that can be retrieved via the 'search_station' function.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: plan_a_journey with date={date}, departure={departure}, arrival={arrival}", module_name="idfm")
    
    result = idfm_service.plan_journey(date, departure, arrival)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def select_a_route(route_id: int) -> str:
    """Used only after calling the 'plan_a_journey' function. If the user is interested in taking one of the suggested routes, this function allows the desired route to be stored in the current route. The stored route can then be used to guide the user during their journey. For example, this is used after a journey calculation request (via the 'plan_a_journey' function) when the user indicates they want to take the proposed route. For instance: 'OK, I will take this route' or 'Alright, I will go with this one, guide me.'
    
    Args:
        route_id: ID of the route to keep. The 'route_id' come from a result of 'plan_a_journey' function call.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: select_a_route with route_id={route_id}", module_name="idfm")
    
    result = idfm_service.select_route(route_id)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def retrieve_current_selected_route() -> str:
    """Retrieve detailed information about the current journey. This allows you to get the information of the journey chosen by the user, for instance, if it's not in the prompt history. It can be used in situations like: 'I am here, what's the next step of my journey?' or 'Okay, resume the guidance of my route.'
    """
    if tomlogger:
        tomlogger.info("Tool call: retrieve_current_selected_route", module_name="idfm")
    
    result = idfm_service.get_selected_route()
    return json.dumps(result, ensure_ascii=False) if result else json.dumps({"error": "No route selected"})


@server.resource("description://idfm")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting IDFM MCP Server on port 80", module_name="idfm")
    else:
        print("Starting IDFM MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()