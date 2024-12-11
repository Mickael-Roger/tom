# Core
import cherrypy
import yaml
import os
import json
import sys
import time
from datetime import datetime, timedelta


# OpenAI
from openai import OpenAI

# Mistral
from mistralai import Mistral
import functools

# Import all modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules')))
from anki import Anki
from nextcloudtodo import NextCloudTodo
from nextcloudcalendar import NextCloudCalendar
from weather import Weather
from kwyk import Kwyk
from pronote import Pronote



################################################################################################
#                                                                                              #
#                              Tom configuration management                                    #
#                                                                                              #
################################################################################################
config = {}

def initConf():
  # Load config
  with open('config.yml', 'r') as file:
    try:
      conf = yaml.safe_load(file)
    except yaml.YAMLError as exc:
      print(f"Error reading YAML file: {exc}")
      exit(1)

  return conf








################################################################################################
#                                                                                              #
#                                    CherryPy API endpoint                                     #
#                                                                                              #
################################################################################################
class TomWebService:

  def __init__(self):
    self.sessions = {}


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  def index(self):

#    session_id = self.get_session_id()
#    if session_id not in self.sessions:
#      self.sessions[session_id] = {"history": ""}
    
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):

#    session_id = self.get_session_id()
#    if session_id not in self.sessions:
#      self.sessions[session_id] = {"history": ""}
#    
    input_json = cherrypy.request.json
    
    user = input_json.get('request')

    response = processRequest(input=user)

    return {"response": response}


#  def get_session_id(self):
#
#    session_id = cherrypy.request.cookie.get('session_id')
#    
#    if session_id.value:
#      session_id = session_id.value
#    else:
#      session_id = str(uuid.uuid4())
#      cherrypy.response.cookie['session_id'] = session_id
#      cherrypy.response.cookie['session_id']['path'] = '/'
#      cherrypy.response.cookie['session_id']['max-age'] = 86400
#    
#    return session_id


def processRequest(input):

  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")
  systemContext = f"Your name is Tom and you are my personal life assistant. Whan your answer contains a date, it must be in the form 'Weekday day month'.Today is {today}" + "\n" + config['personalContext'] + "\n" + calendar.systemContext + "\n" + todo.systemContext + "\n" + anki.systemContext

  messages = [
    {
      "role": "system",
      "content": systemContext
    },
    {
      "role": "user",
      "content": input,
    }
  ]

  functions = {
    'anki_status': functools.partial(anki.status),
    'anki_add': functools.partial(anki.add),
    'calendar_add': functools.partial(calendar.addEvent),
    'weather_get': functools.partial(weather.get),
    'kwyk_get': functools.partial(kwyk.get),
#    'calendar_remove': functools.partial(calendar.deleteEvents),
    'calendar_search': functools.partial(calendar.search),
    'todo_listAll': functools.partial(todo.listAll),
    'todo_closeTask': functools.partial(todo.closeTask),
    'todo_createTask': functools.partial(todo.createTask),
  }

  model = "mistral-large-latest"
  
  response = mistralClient.chat.complete(
    model = model,
    messages = messages,
    tools = tools,
    tool_choice = "auto",
  )

  messages.append(response.choices[0].message)


  if response is not None:
    if response.choices is not None:

      print(response.choices[0].message)

      tool_call = response.choices[0].message.tool_calls[0]
      function_name = tool_call.function.name
      function_params = json.loads(tool_call.function.arguments)

      print(function_name)
      print(function_params)

      res, function_result = functions[function_name](**function_params)


      messages.append({"role":"tool", "name":function_name, "content": json.dumps(function_result), "tool_call_id":tool_call.id})

      time.sleep(1.5)

      response = mistralClient.chat.complete(
        model = model, 
        messages = messages
      )

      print(response)

      return response.choices[0].message.content



################################################################################################
#                                                                                              #
#                                         Main                                                 #
#                                                                                              #
################################################################################################

config = {}
mods = []

config = initConf()
calendar = NextCloudCalendar(config)
todo = NextCloudTodo(config)
anki = Anki(config)
weather = Weather(config)
kwyk = Kwyk(config)
pronote = Pronote(config)


tools = calendar.tools + todo.tools + anki.tools + weather.tools + kwyk.tools

mistralClient = Mistral(api_key=config["mistral"]["api"])

if __name__ == "__main__":    

  cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 8444})
  cherrypy.quickstart(TomWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

