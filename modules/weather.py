import requests
import json

from datetime import datetime, timedelta


################################################################################################
#                                                                                              #
#                                         Weather                                              #
#                                                                                              #
################################################################################################
class Weather:

  def __init__(self, config) -> None:
    self.url = "https://api.open-meteo.com/v1/forecast?latitude=48.82&longitude=2.00&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,precipitation_probability,precipitation,rain,showers,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility"

    self.lastUpdate = datetime.now() - timedelta(hours=24)
    self.data = None

    self.update()

    self.tools = [
      {
        "type": "function",
        "description": "Get the weather forecast. Call this function when user ask information about the weather or anything related to it. For example when a user aks 'What's the weather like', 'How should I dress', 'Will it rain', 'What will the temparature be', 'Will I need an umbrella'. This function does not take any parameter.",
        "function": {
            "name": "weather_get",
            "parameters": {},
        },
      },
    ]

    self.systemContext = ""


  def update(self):

    if datetime.now() > (self.lastUpdate + timedelta(hours=4)):
      response = requests.get(self.url)
      # Check if the request was successful
      if response.status_code == 200:
          # Convert the JSON response to a dictionary
          self.data = response.json()
          self.lastUpdate = datetime.now()


  def get(self, *args, **kwargs):
    self.update()
    return True, self.data




