import requests


################################################################################################
#                                                                                              #
#                                         Weather                                              #
#                                                                                              #
################################################################################################
class Weather:

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
              },
              "required": ["gps_latitude", "gps_longitude"],
              "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "weather_get_by_city_name",
          "description": "Get the weather forecast by a city name. Call this function when user ask information about the weather or anything related to it. For example when a user aks 'What's the weather like', 'How should I dress', 'Will it rain', 'What will the temparature be', 'Will I need an umbrella'. This function when you do not have the GPS position but you have the name of the city you want the weather forecast for. Don't make assumptions about my GPS position. Ask for clarification if a user request is ambiguous.",
          "strict": True,
            "parameters": {
              "type": "object",
              "properties": {
                "city_name": {
                  "type": "string",
                  "description": f"Name of the city you are looking for weather forecast",
                },
              },
              "required": ["city_name"],
              "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = "Always indicated if it's gonna rain or not. You should mainly base your response using the weather_condition field"


  def convertWMO(self, code):
    if code in self.WMOTable:
      return self.WMOTable[code]
    else:
      return None

  def getCity(self, city_name):

    url = self.urlGeocoding + 'name=' + str(city_name) + '&count=1&language=fr&format=json'

    response = requests.get(url)
    if response.status_code == 200:
      # Convert the JSON response to a dictionary
      responseDict = response.json()

      if responseDict['results'][0] is not None:
        return self.getGps(gps_latitude=responseDict['results'][0]['latitude'], gps_longitude=responseDict['results'][0]['longitude'])

    return False, {}



  def getGps(self, gps_latitude, gps_longitude):

    url = self.url + '&latitude=' + str(gps_latitude) + '&longitude=' + str(gps_longitude)

    data = {"hourly": [], "daily": []}

    response = requests.get(url)
    # Check if the request was successful
    if response.status_code == 200:
      # Convert the JSON response to a dictionary
      responseDict = response.json()

      # Hourly data
      for i in range(len(responseDict['hourly']['time'])):
          data['hourly'].append({"timestamp": responseDict['hourly']['time'][i], "temperature": responseDict['hourly']['temperature_2m'][i], "apparent_temperature": responseDict['hourly']['apparent_temperature'][i], "weather_condition": self.convertWMO(str(responseDict['hourly']['weather_code'][i]))})

      # Daily data
      for i in range(len(responseDict['daily']['time'])):
          data['daily'].append({"timestamp": responseDict['daily']['time'][i], "temperature_min": responseDict['daily']['temperature_2m_min'][i], "temperature_max": responseDict['daily']['temperature_2m_max'][i], "apparent_temperature_min": responseDict['daily']['apparent_temperature_min'][i], "apparent_temperature_max": responseDict['daily']['apparent_temperature_max'][i], "weather_condition": self.convertWMO(str(responseDict['daily']['weather_code'][i]))})

    return True, data


