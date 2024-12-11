import requests
import json
import os

from datetime import datetime, timedelta


################################################################################################
#                                                                                              #
#                                         Weather                                              #
#                                                                                              #
################################################################################################
class Weather:

  def __init__(self, config) -> None:
    self.url = "https://api.open-meteo.com/v1/forecast?latitude=48.82&longitude=2.00&hourly=temperature_2m,apparent_temperature,weather_code&daily=temperature_2m_min,temperature_2m_max,apparent_temperature_min,apparent_temperature_max,weather_code&forecast_days=16"

    dateUpdate = datetime.now() - timedelta(hours=24)
    self.lastUpdate = dateUpdate.strftime('%Y-%m-%d %H:%M:%S')
    self.data = None

    self.data_file = config['weather']['cache']

    if os.path.exists(self.data_file):
      try:
        with open(self.data_file, 'r') as file:
          weatherdata = json.load(file)
          self.data = weatherdata["data"]
          self.lastUpdate = weatherdata["lastUpdate"]
          print("Weather cache loaded")
      except:
        print("Exception while loading weather cache")
        pass


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

    self.update()


    self.tools = [
      {
        "type": "function",
        "description": "Get the weather forecast. Call this function when user ask information about the weather or anything related to it. For example when a user aks 'What's the weather like', 'How should I dress', 'Will it rain', 'What will the temparature be', 'Will I need an umbrella'. This function does not take any parameter.",
        "function": {
          "name": "weather_get",
            "parameters": {
#              "type": "object",
#              "properties": {
#                "interval": {
#                  "type": "string",
#                  "enum": ['hourly', 'daily'],
#                  "description": f"",
#                },
#              },
#              "required": ["interval"],
#              "additionalProperties": False,
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



  def update(self):

    dateUpdate = datetime.strptime(self.lastUpdate, '%Y-%m-%d %H:%M:%S')

    if datetime.now() > (dateUpdate + timedelta(hours=4)):
      response = requests.get(self.url)
      # Check if the request was successful
      if response.status_code == 200:

        self.data = {"hourly": [], "daily": []}
        # Convert the JSON response to a dictionary
        responseDict = response.json()

        # Hourly data
        for i in range(len(responseDict['hourly']['time'])):
            self.data['hourly'].append({"timestamp": responseDict['hourly']['time'][i], "temperature": responseDict['hourly']['temperature_2m'][i], "apparent_temperature": responseDict['hourly']['apparent_temperature'][i], "weather_condition": self.convertWMO(str(responseDict['hourly']['weather_code'][i]))})
          

        # Daily data
        for i in range(len(responseDict['daily']['time'])):
            self.data['daily'].append({"timestamp": responseDict['daily']['time'][i], "temperature_min": responseDict['daily']['temperature_2m_min'][i], "temperature_max": responseDict['daily']['temperature_2m_max'][i], "apparent_temperature_min": responseDict['daily']['apparent_temperature_min'][i], "apparent_temperature_max": responseDict['daily']['apparent_temperature_max'][i], "weather_condition": self.convertWMO(str(responseDict['daily']['weather_code'][i]))})
          

        self.lastUpdate = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
          json_data = json.dumps({"data": self.data, "lastUpdate": self.lastUpdate})
          with open(self.data_file, 'w') as file:
            file.write(json_data)
            print("Weather cache saved")
        except Exception as e:
          print("Exception while saving weather cache")
          pass


  def get(self, *args, **kwargs):
    self.update()
    return True, self.data


