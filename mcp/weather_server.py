#!/usr/bin/env python3
"""
Weather MCP Server
Provides weather forecast functionality via MCP protocol
Based on the original tomweather.py module
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

import requests
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
    tomlogger.info(f"🚀 Weather MCP Server starting with log level: {log_level}", module_name="weather")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for for any question about the weather forecast."

# Initialize FastMCP server
server = FastMCP(name="weather-server", stateless_http=True, host="0.0.0.0", port=80)


class WeatherService:
    """Weather service class based on original TomWeather"""
    
    def __init__(self):
        self.url = "https://api.open-meteo.com/v1/forecast?hourly=temperature_2m,apparent_temperature,weather_code&daily=temperature_2m_min,temperature_2m_max,apparent_temperature_min,apparent_temperature_max,weather_code&forecast_days=16"
        self.urlGeocoding = "https://geocoding-api.open-meteo.com/v1/search?"
        
        # GPS cache management
        data_dir = '/data'
        os.makedirs(data_dir, exist_ok=True)
        self.gps_cache_file = os.path.join(data_dir, 'weather_gps_cache.json')
        self.gps_cache = self._load_gps_cache()
        
        if tomlogger:
            tomlogger.info(f"Weather service initialized with cache file: {self.gps_cache_file}", module_name="weather")
            tomlogger.info(f"GPS cache loaded with {len(self.gps_cache.get('cities_gps_position', []))} cities", module_name="weather")
        
        # WMO weather codes mapping
        self.WMOTable = {
            "0": "Clear sky",
            "1": "Mainly clear sky",
            "2": "Sky partly cloudy",
            "3": "Sky overcast",
            "45": "Fog",
            "48": "Depositing rime fog",
            "51": "Light drizzle",
            "53": "Moderate drizzle",
            "55": "Dense drizzle",
            "56": "Freezing drizzle light intensity",
            "57": "Freezing drizzle dense intensity",
            "61": "Slight rain",
            "63": "Moderate rain",
            "65": "Heavy rain",
            "66": "Light freezing rain",
            "67": "Heavy freezing rain",
            "71": "Slight snow fall",
            "73": "Moderate snow fall",
            "75": "Heavy snow fall",
            "77": "Snow grains",
            "80": "Slight rain showers",
            "81": "Moderate rain showers",
            "82": "Violent rain showers",
            "85": "Slight snow showers",
            "86": "Heavy snow showers",
            "95": "Slight or moderate thunderstorm",
            "96": "Thunderstorm with slight hail",
            "99": "Thunderstorm with heavy hail",
        }
    
    def _load_gps_cache(self):
        """Load GPS cache from JSON file"""
        try:
            if os.path.exists(self.gps_cache_file):
                with open(self.gps_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
        return {"cities_gps_position": []}
    
    def _save_gps_cache(self):
        """Save GPS cache to JSON file"""
        try:
            with open(self.gps_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.gps_cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass
    
    def convert_wmo(self, code):
        """Convert WMO weather code to human readable description"""
        if code in self.WMOTable:
            return self.WMOTable[code]
        else:
            return f"Unknown weather code: {code}"
    
    def get_city_gps(self, city_name):
        """Get GPS coordinates for a city by name"""
        # Normalize city name for cache search
        city_key = city_name.strip().lower()
        
        # Check cache first
        for cached_city in self.gps_cache.get('cities_gps_position', []):
            if cached_city['city_name'].lower() == city_key:
                if tomlogger:
                    tomlogger.debug(f"City '{city_name}' found in cache", module_name="weather")
                return [{
                    "name": cached_city['city_name'],
                    "country": cached_city['country'],
                    "gps_latitude": cached_city['gps_latitude'],
                    "gps_longitude": cached_city['gps_longitude']
                }]
        
        # If not in cache, call API
        url = self.urlGeocoding + 'name=' + str(city_name) + '&count=10&language=en&format=json'
        cities = []
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                response_dict = response.json()
                
                if 'results' in response_dict:
                    for city in response_dict['results']:
                        city_data = {
                            "name": city['name'],
                            "country": city['country'],
                            "gps_latitude": city['latitude'],
                            "gps_longitude": city['longitude']
                        }
                        cities.append(city_data)
                        
                        # Update cache with first result (most relevant)
                        if len(cities) == 1:
                            new_cache_entry = {
                                "city_name": city['name'],
                                "country": city['country'],
                                "gps_latitude": city['latitude'],
                                "gps_longitude": city['longitude']
                            }
                            self.gps_cache['cities_gps_position'].append(new_cache_entry)
                            self._save_gps_cache()
                            if tomlogger:
                                tomlogger.info(f"Added '{city['name']}' to GPS cache", module_name="weather")
                
                return cities
        except requests.RequestException as e:
            if tomlogger:
                tomlogger.error(f"Error fetching city data: {e}", module_name="weather")
            else:
                print(f"Error fetching city data: {e}")
            return []
        
        return []
    
    def get_weather_by_gps(self, gps_latitude, gps_longitude, period_from, period_to):
        """Get weather forecast by GPS coordinates"""
        url = self.url + '&latitude=' + str(gps_latitude) + '&longitude=' + str(gps_longitude)
        
        data = {"hourly": [], "daily": []}
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                response_dict = response.json()
                
                search_from = datetime.strptime(period_from, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
                search_to = datetime.strptime(period_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                
                # Hourly data
                if 'hourly' in response_dict:
                    for i in range(len(response_dict['hourly']['time'])):
                        timestamp = datetime.strptime(response_dict['hourly']['time'][i], "%Y-%m-%dT%H:%M")
                        if search_from <= timestamp <= search_to:
                            data['hourly'].append({
                                "timestamp": response_dict['hourly']['time'][i],
                                "temperature": response_dict['hourly']['temperature_2m'][i],
                                "apparent_temperature": response_dict['hourly']['apparent_temperature'][i],
                                "weather_condition": self.convert_wmo(str(response_dict['hourly']['weather_code'][i]))
                            })
                
                # Daily data
                if 'daily' in response_dict:
                    for i in range(len(response_dict['daily']['time'])):
                        timestamp = datetime.strptime(response_dict['daily']['time'][i], "%Y-%m-%d")
                        if search_from <= timestamp <= search_to:
                            data['daily'].append({
                                "timestamp": response_dict['daily']['time'][i],
                                "temperature_min": response_dict['daily']['temperature_2m_min'][i],
                                "temperature_max": response_dict['daily']['temperature_2m_max'][i],
                                "apparent_temperature_min": response_dict['daily']['apparent_temperature_min'][i],
                                "apparent_temperature_max": response_dict['daily']['apparent_temperature_max'][i],
                                "weather_condition": self.convert_wmo(str(response_dict['daily']['weather_code'][i]))
                            })
        except requests.RequestException as e:
            if tomlogger:
                tomlogger.error(f"Error fetching weather data: {e}", module_name="weather")
            else:
                print(f"Error fetching weather data: {e}")
            return {"error": f"Failed to fetch weather data: {str(e)}"}
        
        return data


# Initialize weather service
weather_service = WeatherService()


@server.tool()
def weather_get_by_gps_position(
    gps_latitude: str,
    gps_longitude: str, 
    period_from: str,
    period_to: str
) -> str:
    """Get the weather forecast. Call this function when user asks information about the weather or anything related to it. For example when a user asks 'What's the weather like', 'How should I dress', 'Will it rain', 'What will the temperature be', 'Will I need an umbrella'. This function needs to be called with the exact GPS position.
    
    Args:
        gps_latitude: GPS latitude
        gps_longitude: GPS longitude
        period_from: Must be in the form of '%Y-%m-%d'. Define the starting date to search for. Oldest starting date is '2020-01-01' and could be used when the user request are about events in the past with no more precision about the period like 'When was my last medical appointment?'.
        period_to: Must be in the form of '%Y-%m-%d'. Define the ending date to search for. Maximum ending date is today plus 5 years and could be used when the user request are about events in the future no more precision about the period like 'When will be my next medical appointment?'.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: weather_get_by_gps_position with lat={gps_latitude}, lon={gps_longitude}, from={period_from}, to={period_to}", module_name="weather")
    
    result = weather_service.get_weather_by_gps(gps_latitude, gps_longitude, period_from, period_to)
    return json.dumps(result, ensure_ascii=False, indent=2)


@server.tool()
def get_gps_position_by_city_name(city_name: str) -> str:
    """Get the GPS position for a city by its name. Call this function when you need a GPS position and you only have the City name. Use this function, only if you don't have the City GPS position.
    
    Args:
        city_name: Name of the city you are looking for GPS position
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_gps_position_by_city_name with city={city_name}", module_name="weather")
    
    result = weather_service.get_city_gps(city_name)
    return json.dumps(result, ensure_ascii=False, indent=2)




def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Weather MCP Server on port 80", module_name="weather")
    else:
        print("Starting Weather MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


@server.resource("description://weather")
def description() -> str:
    """Renvoie la description du serveur."""
    return SERVER_DESCRIPTION

if __name__ == "__main__":
    main()
