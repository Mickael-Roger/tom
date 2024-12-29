import requests
from datetime import datetime
import functools


################################################################################################
#                                                                                              #
#                                         Weather                                              #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "weather",
  "class_name": "TomWeather",
  "description": "This module is used for for any question about the weather forecast."
}

class TomWeather:

  def __init__(self, config) -> None:
    self.url = "https://api.open-meteo.com/v1/forecast?hourly=temperature_2m,apparent_temperature,weather_code&daily=temperature_2m_min,temperature_2m_max,apparent_temperature_min,apparent_temperature_max,weather_code&forecast_days=16"

    self.urlGeocoding = "https://geocoding-api.open-meteo.com/v1/search?"

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
          "description": "Get the the GPS position for a city by its name. Call this function when you need a GPS position and you only have the City name.",
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

    self.systemContext = ""
    self.functions = {
      "weather_get_by_gps_position": {
        "function": functools.partial(self.getGps), 
        "responseContext": """When you are asked about the weather, you always must be consise. For example, when the user asked "What will the weather be like tommorrow?", your answer should be like "Tommorrow, saturday december the 1st, temperature will be from 2°C to 7°C and it will have moderate rain in the afternoon" or "Tommorrow, saturday december the 1st, temperature will be from 2°C to 7°C and it's not gonna rain" or if the user asks "Will it rain tommorrow?" your answer should be like "No, it's not gonna rain tommorrow". """ 
      },
      "get_gps_position_by_city_name": {
        "function": functools.partial(self.getCity), 
        "responseContext": "" 
      },
    }



  def convertWMO(self, code):
    if code in self.WMOTable:
      return self.WMOTable[code]
    else:
      return None

  def getCity(self, city_name):

    url = self.urlGeocoding + 'name=' + str(city_name) + '&count=10&language=fr&format=json'

    cities = []

    response = requests.get(url)
    if response.status_code == 200:
      # Convert the JSON response to a dictionary
      responseDict = response.json()

      for city in responseDict['results']:
        cities.append({"name": city['name'], "country": city['country'], "gps_latitude": city['latitude'], "gps_longitude": city['longitude']})
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


