import cherrypy
import uuid

from mistralai import Mistral
import yaml
import importlib
import os
import sys

import json
import time
from datetime import datetime



LOAD_MODULE = [ "nextcloud-calendar", 
                #"anki", 
                #"nextcloud-todo", 
                "obsidian", 
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
  description = 'You are JarMick, my personal assistant. If the user request is or start with "Reset" or "Hi JarMick" or "Hello JarMick" or "Hi" or "Hello" the value for the "service" field must be set to "reset".'
  consigne = 'You must answer a json that contains two values: "service" and "request". The "request" field will always contains the initial user prompt. '

  # Generate the system prompt
  for mod in mods:
    description = description + mod.triage['description'] + " "
    consigne = consigne + mod.triage['consigne'] + " "

  return description + "\n" + consigne


def redirectAfterTriage(context, triage):
  # Find the appropriate module
  for mod in mods:
    if mod.triage["name"] == triage["service"]:
      module = mod
      response = module.request(context + "\n\n" + triage["request"])
      return response
  
  return "Failure"



class MyWebService:


  def __init__(self, config):
    self.sessions = {}
    self.systemPrompt = generateTriagePrompt() 
    self.config = config



  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  def index(self):
    session_id = self.get_session_id()
    if session_id not in self.sessions:
      self.sessions[session_id] = {"history": ""}
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):
    session_id = self.get_session_id()
    if session_id not in self.sessions:
      self.sessions[session_id] = {"history": ""}
    input_json = cherrypy.request.json
    user = input_json.get('request')

    triage = mistralRequest("mistral-medium-latest", self.systemPrompt, self.sessions[session_id]["history"] + "\n\n" + user, config)
    print(triage)
    if triage["service"] == "reset":
      self.sessions[session_id]["history"] = ""
      response = {"response": f"History cleared"}
    else:
      response = redirectAfterTriage(self.sessions[session_id]["history"], triage)

      resp = response.get('response')
      # Store the interaction in the session
      self.sessions[session_id]["history"] = self.sessions[session_id]["history"] + "\n\n" + "me: " + user + "\n\n" + "JarMick: " + str(resp) + "\n\n"
      print(self.sessions[session_id]["history"])

    return response


  def get_session_id(self):
    session_id = cherrypy.request.cookie.get('session_id')
    if session_id.value:
      session_id = session_id.value
    else:
      session_id = str(uuid.uuid4())
      cherrypy.response.cookie['session_id'] = session_id
      cherrypy.response.cookie['session_id']['path'] = '/'
      cherrypy.response.cookie['session_id']['max-age'] = 86400
    return session_id




if __name__ == "__main__":    
  config = initConf()

  mods = load_modules(LOAD_MODULE)

  cherrypy.config.update({'server.socket_port': 8444})
  cherrypy.quickstart(MyWebService(config), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

