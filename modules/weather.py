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
    self.url = "https://api.open-meteo.com/v1/forecast?latitude=48.82&longitude=2.00&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,precipitation_probability,precipitation,rain,showers,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility"

    dateUpdate = datetime.now() - timedelta(hours=24)
    self.lastUpdate = dateUpdate.strftime('%Y-%m-%d %H:%M:%S')
    self.data = None

    self.data_file = config['data'] + 'weather.data'

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

    dateUpdate = datetime.strptime(self.lastUpdate, '%Y-%m-%d %H:%M:%S')

    if datetime.now() > (dateUpdate + timedelta(hours=4)):
      response = requests.get(self.url)
      # Check if the request was successful
      if response.status_code == 200:
        # Convert the JSON response to a dictionary
        self.data = response.json()
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




