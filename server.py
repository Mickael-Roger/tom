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
import copy
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
    for lang in config['global']['tts']['langs'].keys():
      self.models[lang] = TTS(config['global']['tts']['langs'][lang]['model'], progress_bar=False).to("cpu")


  def infere(self, input, lang):
  
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wavFile:
      wavFileName = wavFile.name
      self.models[lang].tts_to_file(text=input, language=config['global']['tts']['langs'][lang]['language'], speaker=config['global']['tts']['langs'][lang]['speaker'], file_path=wavFileName)
  
      base64_result = self.ConvertToMp3(wavFileName)
  
      os.remove(wavFileName)
  
    return base64_result
  
  
  
  
  def ConvertToMp3(self, wavfile):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3File:
      mp3FileName = mp3File.name
  
      subprocess.run(['ffmpeg', '-y', '-i', wavfile, '-c:a', 'mp3', mp3FileName], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  
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

  #  def __init__(self):
  #    self.sessions = {}


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  def index(self):
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")
    
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):
    
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")

    input_json = cherrypy.request.json
    
    user = input_json.get('request')
    lang = input_json.get('lang')
    position = input_json.get('position')

    print(cherrypy.session['username'])

    response = processRequest(input=user, username=cherrypy.session['username'], lang=lang, position=position)

    voice = userList[username]['tts'].infere(response, lang)

    return {"response": response, "voice": voice} 

  @cherrypy.expose
  def auth(self):
    with open(os.path.join('static', 'auth.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  def login(self, username, password):

    for user in config['users']:
      if user['username'] == username and user['password'] == password:
        cherrypy.session['username'] = username
        raise cherrypy.HTTPRedirect("/index")

    return "Invalid credentials. <a href='/auth'>Try again</a>"



    #  def get_session_id(self):
    #
    #    session_id = cherrypy.request.cookie.get('session_id')
    #    
    #    if session_id is not None:
    #      if session_id.value:
    #        return session_id.value
    #
    #    session_id = str(uuid.uuid4())
    #    
    #    return session_id


  def check_auth(self):
    if cherrypy.session.get('username', None) is not None:
      return True
      
    raise cherrypy.HTTPRedirect("/auth")
    



startNewConversationTools = [
  {
    "type": "function",
    "function": {
        "description": "This function must be called to start a new conversation with the user. Must be called when the user say: 'Hey', 'Hi', 'Hi Tom', 'Hey Tom' or 'Change of topic' or 'Let\'s change the subject'",
        "name": "start_new_conversation",
        "parameters": {
        },
    },
  },
]


def processRequest(input, username, lang, position):

  tools = userList[username]['tools']

  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

  if len(userList[username]['history']) == 0: 
    userList[username]['history'].append({"role": "system", "content": f"Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'. Today is {today}" +"\n\n" + "Important: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'" + "\n\n" + userList[username]['systemContext']})

  if position is not None:
    userList[username]['history'].append({"role": "system", "content": f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}"})

  userList[username]['history'].append({"role": "user", "content": input})


  mistralmodel = "mistral-large-latest"
  openaimodel = "gpt-4o-mini"

  
  if config['global']['llm'] == "mistral":
    response = mistralClient.chat.complete(
      model = mistralmodel,
      messages = userList[username]['history'],
      tools = tools,
      tool_choice = "auto",
    )
  elif config['global']['llm'] == "openai":
    response = openaiClient.chat.completions.create(
      model = openaimodel,
      messages = userList[username]['history'],
      tools = tools,
    )
  else:
    print("LLM not defined")
    return False

  print("--------------")
  print(response)
  print("--------------")
  print(userList[username]['history'])
  print("--------------")

  if response is not None:
    if response.choices is not None:

      if response.choices[0].message.content is not None:
        userList[username]['history'].append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})

      if response.choices[0].message.tool_calls is not None:

        tool_call = response.choices[0].message.tool_calls[0]

        function_name = tool_call.function.name
        function_params = json.loads(tool_call.function.arguments)

        print(function_name)
        print(function_params)

        if function_name == "start_new_conversation":
          print("History cleaning")
          userList[username]['history'] = []
          return f"Hi {username}" 


        res, function_result = userList[username]['functions'][function_name]['function'](**function_params)

        userList[username]['history'].append({"role": response.choices[0].message.role, "name":function_name, "content": json.dumps(function_result), "tool_call_id":tool_call.id})

        message = copy.deepcopy(userList[username]['history'])
        message.append({"role": "system", "content": userList[username]['functions'][function_name]['responseContext']})
  
        if config['global']['llm'] == "mistral":
          response = mistralClient.chat.complete(
            model = mistralmodel,
            messages = message,
          )
        elif config['global']['llm'] == "openai":
          response = openaiClient.chat.completions.create(
            model = openaimodel,
            messages = message,
          )
        else:
          print("LLM not defined")
          return False

        if response.choices[0].message.content is not None:
          userList[username]['history'].append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})

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

userList = {}

for user in config['users']:
  username = user['username']
  userList[username] = {}
  userList[username]['history'] = []
  userList[username]['services'] = {}

  userList[username]['systemContext'] = user['personalContext'] + "\n\n"

  userList[username]['functions'] = {}


  userList[username]['tools'] = startNewConversationTools

  for service_name in user['services'].keys():

    if service_name == "calendar":
      userList[username]['services']['calendar'] = NextCloudCalendar(user['services']['calendar'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['calendar'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['calendar'].systemContext + "\n\n"
      userList[username]['functions']['calendar_add'] = {"function": functools.partial(userList[username]['services']['calendar'].addEvent), "responseContext": userList[username]['services']['calendar'].answerContext['calendar_add']}
      userList[username]['functions']['calendar_search'] = {"function": functools.partial(userList[username]['services']['calendar'].search), "responseContext": userList[username]['services']['calendar'].answerContext['calendar_search']}

    if service_name == "groceries":
      userList[username]['services']['groceries'] = Groceries(user['services']['groceries'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['groceries'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['groceries'].systemContext + "\n\n"
      userList[username]['functions']['grocery_list_content'] = {"function": functools.partial(userList[username]['services']['groceries'].listProducts), "responseContext": userList[username]['services']['groceries'].answerContext['grocery_list_content']}
      userList[username]['functions']['grocery_list_add'] = {"function": functools.partial(userList[username]['services']['groceries'].add), "responseContext": userList[username]['services']['groceries'].answerContext['grocery_list_add']}
      userList[username]['functions']['grocery_list_remove'] = {"function": functools.partial(userList[username]['services']['groceries'].remove), "responseContext": userList[username]['services']['groceries'].answerContext['grocery_list_remove']}

    if service_name == "todo":
      userList[username]['services']['todo'] = NextCloudTodo(user['services']['todo'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['todo'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['todo'].systemContext + "\n\n"
      userList[username]['functions']['todo_list_all'] = {"function": functools.partial(userList[username]['services']['todo'].listTasks), "responseContext": userList[username]['services']['todo'].answerContext['todo_list_all']}
      userList[username]['functions']['todo_close_task'] = {"function": functools.partial(userList[username]['services']['todo'].close), "responseContext": userList[username]['services']['todo'].answerContext['todo_close_task']}
      userList[username]['functions']['todo_create_task'] = {"function": functools.partial(userList[username]['services']['todo'].create), "responseContext": userList[username]['services']['todo'].answerContext['todo_create_task']}

    if service_name == "anki":
      userList[username]['services']['anki'] = Anki(user['services']['anki'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['anki'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['anki'].systemContext + "\n\n"
      userList[username]['functions']['anki_status'] = {"function": functools.partial(userList[username]['services']['anki'].status), "responseContext": userList[username]['services']['anki'].answerContext['anki_status']}
      userList[username]['functions']['anki_add'] = {"function": functools.partial(userList[username]['services']['anki'].add), "responseContext": userList[username]['services']['anki'].answerContext['anki_add']}

    if service_name == "kwyk":
      userList[username]['services']['kwyk'] = Kwyk(user['services']['kwyk'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['kwyk'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['kwyk'].systemContext + "\n\n"
      userList[username]['functions']['kwyk_get'] = {"function": functools.partial(userList[username]['services']['kwyk'].get), "responseContext": userList[username]['services']['kwyk'].answerContext['kwyk_get']}

    if service_name == "pronote":
      userList[username]['services']['pronote'] = Pronote(user['services']['pronote'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['pronote'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['pronote'].systemContext + "\n\n"

    userList[username]['services']['weather'] = Weather()
    userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['weather'].tools
    userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['weather'].systemContext + "\n\n"
    userList[username]['functions']['weather_get_by_gps_position'] = {"function": functools.partial(userList[username]['services']['weather'].getGps), "responseContext": userList[username]['services']['weather'].answerContext['weather_get_by_gps_position']}
    userList[username]['functions']['weather_get_by_city_name'] = {"function": functools.partial(userList[username]['services']['weather'].getCity), "responseContext": userList[username]['services']['weather'].answerContext['weather_get_by_city_name']}

    #userList[username]['services']['idfm'] = Idfm(config['global']['idfm'])
    #userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['idfm'].tools
    #userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['idfm'].systemContext + "\n\n"
    #userList[username]['functions']['get_train_schedule'] = {"function": functools.partial(userList[username]['services']['idfm'].schedule), "responseContext": userList[username]['services']['idfm'].answerContext['get_train_schedule']}
    #userList[username]['functions']['get_train_disruption'] = {"function": functools.partial(userList[username]['services']['idfm'].disruption), "responseContext": userList[username]['services']['idfm'].answerContext['get_train_disruption']}
    
    userList[username]['tts'] = tts


mistralClient = Mistral(api_key=config['global']["mistral"]["api"])
openaiClient = OpenAI(api_key=config['global']["openai"]["api"])


if __name__ == "__main__":    

  cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 8082, 'tools.sessions.on': True})
  cherrypy.quickstart(TomWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

