import requests
from datetime import datetime
import functools
import json
import os


################################################################################################
#                                                                                              #
#                                         Weather                                              #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "weather",
  "class_name": "TomWeather",
  "description": "This module is used for for any question about the weather forecast.",
  "type": "global",
  "complexity": 0,
  "configuration_parameters": {}
}

class TomWeather:

  def __init__(self, config, llm) -> None:
    self.url = "https://api.open-meteo.com/v1/forecast?hourly=temperature_2m,apparent_temperature,weather_code&daily=temperature_2m_min,temperature_2m_max,apparent_temperature_min,apparent_temperature_max,weather_code&forecast_days=16"

    self.urlGeocoding = "https://geocoding-api.open-meteo.com/v1/search?"
    
    # Gestion du cache GPS des villes
    all_datadir = config.get('all_datadir', './data/all/')
    os.makedirs(all_datadir, exist_ok=True)
    self.gps_cache_file = os.path.join(all_datadir, 'weather_gps_cache.json')
    self.gps_cache = self._load_gps_cache()

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

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "weather_get_by_gps_position",
          "description": "Get the weather forecast. Call this function when user ask information about the weather or anything related to it. For example when a user aks 'What's the weather like', 'How should I dress', 'Will it rain', 'What will the temparature be', 'Will I need an umbrella'. This function needs to be called with the exact GPS position.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "gps_latitude": {
                "type": "string",
                "description": f"GPS latitude",
              },
              "gps_longitude": {
                "type": "string",
                "description": f"GPS longitude",
              },
              "period_from": {
                "type": "string",
                "description": f"Must be in the form of '%Y-%m-%d'. Define the starting date to search for. Oldest starting date is '2020-01-01' and could be used when the user request are about events in the past with no more precision about the period like 'When was my last medical appointment?'.",
              },
              "period_to": {
                "type": "string",
                "description": f"Must be in the form of '%Y-%m-%d'. Define the ending date to search for. Maximum ending date is today plus 5 years and could be used when the user request are about events in the futur no more precision about the period like 'When will be my next medial appointment?'.",
              },
              },
              "required": ["gps_latitude", "gps_longitude", "period_from", "period_to"],
              "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_gps_position_by_city_name",
          "description": "Get the the GPS position for a city by its name. Call this function when you need a GPS position and you only have the City name. Use this function, only if you don't have the City GPS position.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "city_name": {
                "type": "string",
                "description": f"Name of the city you are looking for GPS position",
              },
            },
            "required": ["city_name"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "weather_get_by_gps_position": {
        "function": functools.partial(self.getGps)
      },
      "get_gps_position_by_city_name": {
        "function": functools.partial(self.getCity)
      },
    }



  def convertWMO(self, code):
    if code in self.WMOTable:
      return self.WMOTable[code]
    else:
      return None

  def _load_gps_cache(self):
    """Charge le cache GPS depuis le fichier JSON"""
    try:
      if os.path.exists(self.gps_cache_file):
        with open(self.gps_cache_file, 'r', encoding='utf-8') as f:
          return json.load(f)
    except (json.JSONDecodeError, IOError):
      pass
    return {"cities_gps_position": []}

  def _save_gps_cache(self):
    """Sauvegarde le cache GPS dans le fichier JSON"""
    try:
      with open(self.gps_cache_file, 'w', encoding='utf-8') as f:
        json.dump(self.gps_cache, f, ensure_ascii=False, indent=2)
    except IOError:
      pass

  def _get_cache_summary(self):
    """Returns a cache summary for system context"""
    if not self.gps_cache.get('cities_gps_position'):
      return "No cities are currently cached."
    
    cache_summary = "Cached cities with their GPS positions:\n"
    for city_data in self.gps_cache['cities_gps_position']:
      cache_summary += f"- {city_data['city_name']}: {city_data['country']} (lat: {city_data['gps_latitude']}, lon: {city_data['gps_longitude']})\n"
    
    return cache_summary

  @property
  def systemContext(self):
    """Dynamic system context that includes up-to-date cache information"""
    return f"""You have access to a GPS positions cache for cities to optimize weather requests.

{self._get_cache_summary()}

IMPORTANT: Before calling get_gps_position_by_city_name, first check if the city is already in the cache above. If it is, use the GPS coordinates directly from the cache to call weather_get_by_gps_position. If the GPS position of the city is not in the cache, use get_gps_position_by_city_name to get it."""

  def getCity(self, city_name):
    # Normaliser le nom de la ville pour la recherche dans le cache (minuscules, pas d'espaces en trop)
    city_key = city_name.strip().lower()
    
    # Vérifier d'abord le cache
    for cached_city in self.gps_cache.get('cities_gps_position', []):
      if cached_city['city_name'].lower() == city_key:
        return [{
          "name": cached_city['city_name'],
          "country": cached_city['country'],
          "gps_latitude": cached_city['gps_latitude'],
          "gps_longitude": cached_city['gps_longitude']
        }]

    # Si pas dans le cache, faire appel à l'API
    url = self.urlGeocoding + 'name=' + str(city_name) + '&count=10&language=fr&format=json'
    cities = []

    response = requests.get(url)
    if response.status_code == 200:
      # Convert the JSON response to a dictionary
      responseDict = response.json()

      for city in responseDict['results']:
        city_data = {
          "name": city['name'], 
          "country": city['country'], 
          "gps_latitude": city['latitude'], 
          "gps_longitude": city['longitude']
        }
        cities.append(city_data)
        
        # Mettre à jour le cache avec le premier résultat (le plus pertinent)
        if len(cities) == 1:
          new_cache_entry = {
            "city_name": city['name'],
            "country": city['country'],
            "gps_latitude": city['latitude'],
            "gps_longitude": city['longitude']
          }
          self.gps_cache['cities_gps_position'].append(new_cache_entry)
          self._save_gps_cache()
      
      return cities

    return False



  def getGps(self, gps_latitude, gps_longitude, period_from, period_to):

    url = self.url + '&latitude=' + str(gps_latitude) + '&longitude=' + str(gps_longitude)

    data = {"hourly": [], "daily": []}

    response = requests.get(url)
    # Check if the request was successful
    if response.status_code == 200:
      # Convert the JSON response to a dictionary
      responseDict = response.json()

      search_from = datetime.strptime(period_from, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
      search_to = datetime.strptime(period_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

      # Hourly data
      for i in range(len(responseDict['hourly']['time'])):
        if datetime.strptime(responseDict['hourly']['time'][i], "%Y-%m-%dT%H:%M") >= search_from and datetime.strptime(responseDict['hourly']['time'][i], "%Y-%m-%dT%H:%M") <= search_to: 
          data['hourly'].append({"timestamp": responseDict['hourly']['time'][i], "temperature": responseDict['hourly']['temperature_2m'][i], "apparent_temperature": responseDict['hourly']['apparent_temperature'][i], "weather_condition": self.convertWMO(str(responseDict['hourly']['weather_code'][i]))})

      # Daily data
      for i in range(len(responseDict['daily']['time'])):
        if datetime.strptime(responseDict['daily']['time'][i], "%Y-%m-%d") >= search_from and datetime.strptime(responseDict['daily']['time'][i], "%Y-%m-%d") <= search_to: 
          data['daily'].append({"timestamp": responseDict['daily']['time'][i], "temperature_min": responseDict['daily']['temperature_2m_min'][i], "temperature_max": responseDict['daily']['temperature_2m_max'][i], "apparent_temperature_min": responseDict['daily']['apparent_temperature_min'][i], "apparent_temperature_max": responseDict['daily']['apparent_temperature_max'][i], "weather_condition": self.convertWMO(str(responseDict['daily']['weather_code'][i]))})

    return data
