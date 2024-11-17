import time
import json


class JarMick():

  def __init__(self, config, callLLM) -> None:

    self.triage = {
      "name": "other",
      "description": "",
      "consigne": 'Otherwise if you are not able to determine the appropriate value for the "service" field, it must be set to "other".'
    }

    self.conf = config
    self.callLLM = callLLM


  def request(self, user):

    response = self.callLLM("mistral-large-latest", "return a json that only contains one field called 'response' and that contains your answer to the user prompt", user, self.conf)
    
    time.sleep(1.5)
    
    return json.loads(response.choices[0].message.content)



