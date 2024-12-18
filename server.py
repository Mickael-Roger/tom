# Core
import cherrypy
import yaml
import os
import json
import sys
import importlib.util
from datetime import datetime, timedelta
import tempfile
import base64
import subprocess
import copy
from TTS.api import TTS
import functools


# OpenAI
from openai import OpenAI

# Mistral
from mistralai import Mistral

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
#                                     Modules loading                                          #
#                                                                                              #
################################################################################################
#mod_dir = "./modules"
#
#mods = {}
#
#for mod_file in os.listdir(mod_dir):
#
#  if mod_file.endswith(".py") and mod_file != "__init__.py":
#    mod_name = mod_file[:-3]
#
#    # Is the module already imported?
#    if mod_name not in sys.modules:
#      mod_path = os.path.join(mod_dir, mod_file)
#      
#      mod_spec = importlib.util.spec_from_file_location(mod_name, mod_path)
#      module = importlib.util.module_from_spec(mod_spec)
#  
#      sys.modules[mod_name] = module
#
#      toto = mod_spec.loader.exec_module(module)
#      print(toto)
#
#      print(f"{mod_name} loaded")

        # Import module classe
        #classes = [attr for attr in dir(module) if isinstance(getattr(module, attr), type)]
        #
        #if classes:
        #    class_name = classes[0]
        #    class_mod = getattr(module, class_name)
        #    print(class_mod)

        #    mods[class_name] = class_mod

        #    # Créer une instance de la classe
        #    print(f"{class_name} loaded")


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
  @cherrypy.tools.json_out()
  def reset(self):
    if resetAndSave(username=cherrypy.session['username']):
      return {"success": True}
    else:
      raise cherrypy.HTTPError(500, "Could not reset and save the session")


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):
    
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")

    input_json = cherrypy.request.json

    print("+++++++")
    print(input_json)
    print("+++++++")
    
    user = input_json.get('request')
    lang = input_json.get('lang')
    position = input_json.get('position')
    localTTS = input_json.get('tts')

    print(cherrypy.session['username'])

    response = processRequest(input=user, username=cherrypy.session['username'], lang=lang, position=position)

    voice= None
    if not localTTS:
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
        print(f"History cleaning for user {username}")
        userList[username]['history'] = []

        raise cherrypy.HTTPRedirect("/index")

    return "Invalid credentials. <a href='/auth'>Try again</a>"



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


def processLLM(messages, tools):


  mistralmodel = "mistral-large-latest"
  openaimodel = "gpt-4o-mini"

  print("-------- EXECUTE ---------", flush=True)
  print(messages, flush=True)
  print("--------------", flush=True)

  
  if config['global']['llm'] == "mistral":
    response = mistralClient.chat.complete(
      model = mistralmodel,
      messages = messages,
      tools = tools,
      tool_choice = "auto",
    )
  elif config['global']['llm'] == "openai":
    response = openaiClient.chat.completions.create(
      model = openaimodel,
      messages = messages,
      tools = tools,
    )
  else:
    print("LLM not defined")
    return False, "LLM not defined"

  print("-------- RESPONSE ---------", flush=True)
  print(response, flush=True)
  print("--------------", flush=True)

  return True, response


def resetAndSave(username):

  print("History cleaning")
  userList[username]['history'] = []
  return True


def generateContextPrompt(input, username, lang, position):

  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")
  todayMsg = {"role": "system", "content": f"Today is {today}.\n\n"}

  if userList[username]['history']: 
    userList[username]['history'][0] = todayMsg
  else:
    userList[username]['history'].append(todayMsg)

  if len(userList[username]['history']) == 1: 
    userList[username]['history'].append({"role": "system", "content": "Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'." +"\n\n" + "Important: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'" + "\n\n" + userList[username]['systemContext']})

  if position is not None:
    userList[username]['history'].append({"role": "system", "content": f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}"})

  userList[username]['history'].append({"role": "user", "content": input})



def processRequest(input, username, lang, position):

  tools = userList[username]['tools']

  generateContextPrompt(input, username, lang, position)

  while True:
    
    ret, response = processLLM(userList[username]['history'], tools)

    if not ret:
      return f"Error: {response}"
    elif response is None:
      return f"Error: No response from LLM"


    if response.choices is not None:

      if response.choices[0].message.content is not None:
        userList[username]['history'].append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})

      if response.choices[0].message.tool_calls is not None:

        userList[username]['history'].append(response.choices[0].message)

        print("\n\n\n*******************************************************")
        print(userList[username]['history'])
        print("********************************************************\n\n\n")

        responseContext = {"functions": [], "rules": []}

        for tool_call in response.choices[0].message.tool_calls:

          #tool_call = response.choices[0].message.tool_calls[0]

          function_name = tool_call.function.name
          function_params = json.loads(tool_call.function.arguments)

          print("Call: " + str(function_name) + " with " + str(function_params))

          if function_name == "start_new_conversation":
            if resetAndSave(username=cherrypy.session['username']):
              return f"Hi {username}"
            else:
              return "Error while saving your history"


          res, function_result = userList[username]['functions'][function_name]['function'](**function_params)

          print(res)
          print(function_result)

          if res is False:
            return "Error execution the function"

          userList[username]['history'].append({"role": 'tool', "content": json.dumps(function_result), "tool_call_id": tool_call.id})
          
          # TODODODODODDODODO
          if function_name not in responseContext['functions']:
            responseContext['functions'].append(function_name)
            responseContext['rules'].append({"role": "system", "content": userList[username]['functions'][function_name]['responseContext']})

        userList[username]['history'] = userList[username]['history'] + responseContext['rules']

        print("\n\n\n********************** 2 *********************************")
        print(userList[username]['history'])
        print("********************************************************\n\n\n")


      else:

        print("\n\n\n********************** 3 *********************************")
        print(response.choices[0].message.content)
        print("********************************************************\n\n\n")

        return response.choices[0].message.content

    else:
      return "Error: Response choices is None"



################################################################################################
#                                                                                              #
#                                         Main                                                 #
#                                                                                              #
################################################################################################

config = {}

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

  cherrypy.config.update({
    'server.socket_host': '0.0.0.0', 
    'server.socket_port': 8082, 
    'tools.sessions.on': True, 
    'tools.sessions.timeout': 3600 * 24 * 30,
    'tools.sessions.storage_type': 'file',
    'tools.sessions.storage_path': config['global']['sessions'] 
  })
  cherrypy.quickstart(TomWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

