# Core
import cherrypy
import yaml
import os
import json
import sys
import time
from datetime import datetime, timedelta
import uuid
import tempfile
import base64
import subprocess
#import requests
import torch
from TTS.api import TTS


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
from idfm import Idfm
from groceries import Groceries



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
#                                       TTS Capabilities                                       #
#                                                                                              #
################################################################################################
class TomTTS:

  def __init__(self, config):

    self.models = {}
    for lang in config['tts']['langs'].keys():
      self.models[lang] = TTS(config['tts']['langs'][lang], progress_bar=False).to("cpu")


  def infere(self, input, lang):
  
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wavFile:
      wavFileName = wavFile.name
      self.models[lang].tts_to_file(text=input, file_path=wavFileName)
  
      base64_result = self.ConvertToMp3(wavFileName)
  
      os.remove(wavFileName)
  
    return base64_result
  
  
  
  
  def ConvertToMp3(self, wavfile):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3File:
      mp3FileName = mp3File.name
  
      subprocess.run(['ffmpeg', '-y', '-i', wavfile, '-c:a', 'mp3', mp3FileName], check=True)
  
      with open(mp3FileName, 'rb') as temp_file2:
        output_data = temp_file2.read()
  
      base64_data = base64.b64encode(output_data).decode('utf-8')
  
      os.remove(mp3FileName)
  
      return base64_data






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

    session_id = self.get_session_id()
    if session_id not in self.sessions:
      self.sessions[session_id] = {"history": []}
    
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):

    session_id = self.get_session_id()
    if session_id not in self.sessions:
      self.sessions[session_id] = {"history": []}
    
    input_json = cherrypy.request.json
    
    user = input_json.get('request')
    lang = input_json.get('lang')
    position = input_json.get('position')

    response = processRequest(input=user, session=self.sessions[session_id], lang=lang, position=position)

    voice = tts.infere(response, lang)

    return {"response": response, "voice": voice} 


  def get_session_id(self):

    session_id = cherrypy.request.cookie.get('session_id')
    
    if session_id is not None:
      if session_id.value:
        return session_id.value

    session_id = str(uuid.uuid4())
    cherrypy.response.cookie['session_id'] = session_id
    cherrypy.response.cookie['session_id']['path'] = '/'
    cherrypy.response.cookie['session_id']['max-age'] = 86400
    
    return session_id



startNewConversationTools = [
  {
    "type": "function",
    "description": "This function must be called to start a new conversation with the user. Must be called when the user say: 'Hey', 'Hi', 'Hi Tom', 'Hey Tom' or 'Change of topic' or 'Let\'s change the subject'",
    "function": {
        "name": "start_new_conversation",
        "parameters": {
        },
    },
  },
]


def processRequest(input, session, lang, position):

  tools = startNewConversationTools + calendar.tools + todo.tools + anki.tools + weather.tools + kwyk.tools + idfm.tools + groceries.tools

  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

  if len(session['history']) == 0: 
    session['history'].append({"role": "system", "content": f"Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'. Today is {today}" +"\n\n" + "Important: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'" + "\n\n" + config['personalContext'] + "\n\n" + calendar.systemContext + "\n\n" + todo.systemContext + "\n\n" + anki.systemContext + "\n\n" + idfm.systemContext + "\n\n" + groceries.systemContext })

  if position is not None:
    session['history'].append({"role": "system", "content": f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}"})

  session['history'].append({"role": "user", "content": input})

  functions = {
    'anki_status': functools.partial(anki.status),
    'anki_add': functools.partial(anki.add),
    'calendar_add': functools.partial(calendar.addEvent),
    'weather_get_by_gps_position': functools.partial(weather.getGps),
    'weather_get_by_city_name': functools.partial(weather.getCity),
    'kwyk_get': functools.partial(kwyk.get),
    'get_train_schedule': functools.partial(idfm.schedule),
    'get_train_disruption': functools.partial(idfm.disruption),
#    'calendar_remove': functools.partial(calendar.deleteEvents),
    'calendar_search': functools.partial(calendar.search),
    'grocery_list_content': functools.partial(groceries.listProducts),
    'grocery_list_add': functools.partial(groceries.add),
    'grocery_list_remove': functools.partial(groceries.remove),
    'todo_list_all': functools.partial(todo.listTasks),
    'todo_close_task': functools.partial(todo.close),
    'todo_create_task': functools.partial(todo.create),
  }

  mistralmodel = "mistral-large-latest"
  openaimodel = "gpt-4o-mini"

  print("==================== START ============================")
  print(session['history'])
  print("================================================")
  
  if config['llm'] == "mistral":
    response = mistralClient.chat.complete(
      model = mistralmodel,
      messages = session['history'],
      tools = tools,
      tool_choice = "auto",
    )
  elif config['llm'] == "openai":
    response = openaiClient.chat.completions.create(
      model = openaimodel,
      messages = session['history'],
      tools = tools,
    )
  else:
    print("LLM not defined")
    return False

  print(response)

  if response is not None:
    if response.choices is not None:

      if response.choices[0].message.content is not None:
        session['history'].append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})

      if response.choices[0].message.tool_calls is not None:

        tool_call = response.choices[0].message.tool_calls[0]

        function_name = tool_call.function.name
        function_params = json.loads(tool_call.function.arguments)

        if function_name == "start_new_conversation":
          session['history'] = None
          return {"Response": "Hi"} 

        res, function_result = functions[function_name](**function_params)

        print(function_name)
        print(function_params)

        session['history'].append({"role": response.choices[0].message.role, "name":function_name, "content": json.dumps(function_result), "tool_call_id":tool_call.id})

        if config['llm'] == "mistral":
          response = mistralClient.chat.complete(
            model = mistralmodel,
            messages = session['history'],
          )
        elif config['llm'] == "openai":
          response = openaiClient.chat.completions.create(
            model = openaimodel,
            messages = session['history'],
          )
        else:
          print("LLM not defined")
          return False

        print(response.choices[0])

        if response.choices[0].message.content is not None:
          session['history'].append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})

      return response.choices[0].message.content



################################################################################################
#                                                                                              #
#                                         Main                                                 #
#                                                                                              #
################################################################################################

config = {}
mods = []

config = initConf()

tts = TomTTS(config)

groceries = Groceries(config)
calendar = NextCloudCalendar(config)
todo = NextCloudTodo(config)
anki = Anki(config)
weather = Weather(config)
kwyk = Kwyk(config)
pronote = Pronote(config)
idfm = Idfm(config)





mistralClient = Mistral(api_key=config["mistral"]["api"])
openaiClient = OpenAI(api_key=config["openai"]["api"])

if __name__ == "__main__":    

  cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 8082})
  cherrypy.quickstart(TomWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

