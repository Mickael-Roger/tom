from mistralai import Mistral
import yaml
import importlib
import os
import sys

import json
import time
from datetime import datetime



LOAD_MODULE = [ "nextcloud-calendar", 
                "anki", 
                #"obsidian", 
                "default", 
              ]


config = {}
mods = []

def load_modules(module_names, module_dir='modules'):
    # Add the module directory to the Python path
    module_path = os.path.join(os.getcwd(), module_dir)
    if module_path not in sys.path:
        sys.path.append(module_path)

    modules = []

    for feature_name in module_names:
        try:
            # Dynamically import the module
            module = importlib.import_module(feature_name)

            # Get the JarMick class from the module
            JarMick = getattr(module, 'JarMick')

            # Instantiate the JarMick class
            feature_instance = JarMick(config, mistralRequest)

            # Append the instance to the list
            modules.append(feature_instance)
        except ImportError as e:
            print(f"Error importing module {feature_name}: {e}")
        except AttributeError as e:
            print(f"Error accessing JarMick class in module {feature_name}: {e}")

    return modules



def mistralRequest(model, system, user, conf):
  client = Mistral(api_key=conf["mistral"]["api"])
  
  chat_response = client.chat.complete(
    model = model,
    response_format = {
      "type": "json_object",
    },
    messages = [
      {
        "role": "system",
        "content": system,
      },
      {
        "role": "user",
        "content": user,
      },
    ]
  )
  
  time.sleep(1.5)
  
  return json.loads(chat_response.choices[0].message.content)


def initConf():
  # Load config
  with open('config.yml', 'r') as file:
    try:
      conf = yaml.safe_load(file)
    except yaml.YAMLError as exc:
      print(f"Error reading YAML file: {exc}")
      exit(1)

  return conf

def generateTriagePrompt():
  description = ""
  consigne = 'You must answer a json that contains two values: "service" and "request". The "request" field will always contains the initial user prompt. '

  # Generate the system prompt
  for mod in mods:
    description = description + mod.triage['description'] + " "
    consigne = consigne + mod.triage['consigne'] + " "

  return description + "\n" + consigne


def redirectAfterTriage(triage):
  # Find the appropriate module
  for mod in mods:
    if mod.triage["name"] == triage["service"]:
      module = mod
      response = module.request(triage["request"])
      return response
  
  return "Failure"



    

if __name__ == "__main__":    
  config = initConf()

  mods = load_modules(LOAD_MODULE)

  systemPrompt = generateTriagePrompt() 

  print(systemPrompt)

  user = sys.argv[1]

  triage = mistralRequest("mistral-small-latest", systemPrompt, user, config)

  response = redirectAfterTriage(triage)
  print(response)

# Later Start an API server

# Init all modules and generate the triage prompt, and list of entrypoint function for each module

# On a request:
#   - Start triage
#   - According to the result, use the appropriate object
#   - In the service, if multiple calls are needed, the module is reponsible to trigger LLM API calls



##############

#if triage['service'] == "calendar":
#
#  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")
#
#  # Prompt for requesting the Calendar data through API
#  chat_response = client.chat.complete(
#      model = "mistral-large-latest",
#      response_format = {
#          "type": "json_object",
#      },
#      messages = [
#          {
#              "role": "system",
#              "content": f"""
#              The user prompt is a about information that is containt in its calendar.
#              Today is {today}.
#              A week starts on monday and ends on sunday.
#              You must answer a json that contains three values: "action" "start" and "end". 
#              The json "start" values and "end" values must correspond to the starting and ending date that must be used to answer the user request.
#              If you have no information that you can use to define the period of search, the default period of search will be one year.
#              If the request is about information from the past, the "end" value is today.
#              Returned date msut be in the form: YYYY-MM-DD HH:MM:SS
#              """,
#          },
#  
#          {
#              "role": "user",
#              "content": triage['request'],
#          },
#      ]
#  )
#  date_range = json.loads(chat_response.choices[0].message.content)
#
#



