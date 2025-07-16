# Core
import cherrypy
import yaml
import os
import json
import sys
import importlib.util
import inspect
import functools
import sqlite3

# Import core modules
core_module_dir = './core_modules'
if core_module_dir not in sys.path:
    sys.path.append(core_module_dir)

from tomcoremodules import TomCoreModules
from tomllm import TomLLM
from tomcorebehavior import TomBehavior
from tomcorememory import TomMemory
from tomcorereminder import TomReminder
#from tomcoreremember import TomRemember
#from tomcoremorningroutine import TomMorning
from tomcorebackground import TomBackground


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

  ####
  #
  # Index: /
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  def index(self):
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")
    
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()


  ####
  #
  # /notifications
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST', 'GET'])
  @cherrypy.tools.json_out()
  def notifications(self):

    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")

    username = cherrypy.session['username']

    notifications = []
    
    res, reminders = userList[username].functions['tom_list_reminders']['function']() 

    if res:
      for reminder in reminders:
        notifications.append({"datetime": reminder['reminder_datetime'], "message": reminder['reminder_message']})

    print(notifications)

    return notifications


  ####
  #
  # /reset
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_out()
  def reset(self):
    if userList[cherrypy.session['username']].reset():
      return {"success": True}
    else:
      raise cherrypy.HTTPError(500, "Could not reset and save the session")


  ####
  #
  # /process
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):
    
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")

    input_json = cherrypy.request.json

    user_input = input_json.get('request')
    lang = input_json.get('lang')
    position = input_json.get('position')
    localTTS = input_json.get('tts')
    client_type = input_json.get('client_type', 'pwa')
    username = cherrypy.session['username']


    response = userList[username].processRequest(input=user_input, lang=lang, position=position, client_type=client_type)


    print(response)

    if response:

      return {"response": response} 

    else:
      raise cherrypy.HTTPError(500, response)

  ####
  #
  # /tasks
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  @cherrypy.tools.json_out()
  def tasks(self):
    
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")


    response = userList[cherrypy.session['username']].tasks.tasks
    message = userList[cherrypy.session['username']].tasks.msg
    id = userList[cherrypy.session['username']].tasks.status_id

    print(response)

    if response:
      return {"background_tasks": response, "message": message, "id": id} 

    else:
      return {"background_tasks": [], "message": "", "id": 0} 




  ####
  #
  # /auth
  #
  ####
  @cherrypy.expose
  def auth(self):
    with open(os.path.join('static', 'auth.html'), 'r') as file:
      return file.read()


  ####
  #
  # /login
  #
  ####
  @cherrypy.expose
  def login(self, username, password):

    for user in global_config['users']:
      if user['username'] == username and user['password'] == password:
        cherrypy.session['username'] = username
        print(f"History cleaning for user {username}")
        userList[cherrypy.session['username']].reset()

        raise cherrypy.HTTPRedirect("/index")

    return "Invalid credentials. <a href='/auth'>Try again</a>"



  def check_auth(self):
    if cherrypy.session.get('username', None) is not None:
      return True
      
    raise cherrypy.HTTPRedirect("/auth")

  ####
  #
  # /notifications.js
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  @cherrypy.tools.json_out()
  def notificationconfig(self):

    apiKey = global_config['global']['firebase']['apiKey']
    authDomain = global_config['global']['firebase']['authDomain']
    projectId = global_config['global']['firebase']['projectId']
    storageBucket = global_config['global']['firebase']['storageBucket']
    messagingSenderId = global_config['global']['firebase']['messagingSenderId']
    appId = global_config['global']['firebase']['appId']
    vapidkey = global_config['global']['firebase']['vapidkey']

    config = {
      "firebaseConfig": {
        "apiKey": apiKey,
        "authDomain": authDomain,
        "projectId": projectId,
        "storageBucket": storageBucket,
        "messagingSenderId": messagingSenderId,
        "appId": appId,
      },
      "vapidKey": vapidkey
    }
    return config


  @cherrypy.expose
  def firebase_messaging_sw_js(self):
      # Path to your JavaScript file
      js_file_path = './static/firebase-messaging-sw.js'

      apiKey = global_config['global']['firebase']['apiKey']
      authDomain = global_config['global']['firebase']['authDomain']
      projectId = global_config['global']['firebase']['projectId']
      storageBucket = global_config['global']['firebase']['storageBucket']
      messagingSenderId = global_config['global']['firebase']['messagingSenderId']
      appId = global_config['global']['firebase']['appId']

      config = f"""firebaseConfig={{"apiKey": "{apiKey}", "authDomain": "{authDomain}", "projectId": "{projectId}", "storageBucket": "{storageBucket}", "messagingSenderId": "{messagingSenderId}", "appId": "{appId}"}};"""

      try:
        with open(js_file_path, 'rb') as js_file:
          js_content = js_file.read().replace('firebaseConfig = {};'.encode(), config.encode())

        # Set the Content-Type header to application/javascript
        cherrypy.response.headers['Content-Type'] = 'application/javascript'

        return js_content
      except FileNotFoundError:
        cherrypy.response.status = 404
        return "File not found"
      except Exception as e:
        cherrypy.response.status = 500
        return f"An error occurred: {str(e)}"


  ####
  #
  # /fcmtoken
  #
  ####
  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  def fcmtoken(self):
    
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")

    input_json = cherrypy.request.json

    token = input_json.get('token')
    platform = input_json.get('platform')
    username = cherrypy.session['username']

    # Add or Update user token

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], "all")
    db_notifs = os.path.join(db_path, "reminders.sqlite")

    dbconn = sqlite3.connect(db_notifs)
    cursor = dbconn.cursor()
    cursor.execute('DELETE FROM fcm_tokens WHERE token = ?', (token,))
    cursor.execute('INSERT INTO fcm_tokens (token, username, platform) VALUES (?, ?, ?)', (token, username, platform))
    dbconn.commit()
    dbconn.close()

    return 


################################################################################################
#                                                                                              #
#                                         Main                                                 #
#                                                                                              #
################################################################################################

global_config = {}

global_config = initConf()



userList = {}
module_managers = {}

for user in global_config['users']:

  username = user['username']
  llm_instance = TomLLM(user, global_config)
  userList[username] = llm_instance
  
  # Set admin status (default: False if not specified)
  userList[username].admin = user.get('admin', False)
  
  # Load modules using TomCoreModules
  module_manager = TomCoreModules(global_config, user, llm_instance)
  userList[username].services = module_manager.services
  userList[username].functions = module_manager.functions
  module_managers[username] = module_manager
    
  behavior_obj = TomBehavior(global_config, username)
  userList[username].services['behavior'] = {
    "obj": behavior_obj,
    "description": behavior_obj.tom_config["description"],
    "systemContext": "",
    "tools": [],
    "complexity": 0,
    "functions": {}, 
  }
  userList[username].services['behavior']['tools'] = userList[username].services['behavior']['obj'].tools
  userList[username].services['behavior']['complexity'] = userList[username].services['behavior']['obj'].complexity
  userList[username].services['behavior']['systemContext'] = userList[username].services['behavior']['obj'].systemContext
  userList[username].functions = userList[username].functions | userList[username].services['behavior']['obj'].functions

  memory_obj = TomMemory(global_config, username)
  userList[username].services['memory'] = {
    "obj": memory_obj,
    "description": memory_obj.tom_config["description"], 
    "systemContext": "",
    "tools": [],
    "complexity": 0,
    "functions": {}, 
  }
  userList[username].services['memory']['tools'] = userList[username].services['memory']['obj'].tools
  userList[username].services['memory']['complexity'] = userList[username].services['memory']['obj'].complexity
  userList[username].services['memory']['systemContext'] = userList[username].services['memory']['obj'].systemContext
  userList[username].functions = userList[username].functions | userList[username].services['memory']['obj'].functions
  userList[username].services['memory']['obj'].llm = userList[username].llm

  reminder_obj = TomReminder(global_config, username)
  userList[username].services['reminder'] = {
    "obj": reminder_obj,
    "description": reminder_obj.tom_config["description"], 
    "systemContext": "",
    "tools": [],
    "complexity": 0,
    "functions": {}, 
  }
  userList[username].services['reminder']['tools'] = userList[username].services['reminder']['obj'].tools
  userList[username].services['reminder']['complexity'] = userList[username].services['reminder']['obj'].complexity
  userList[username].services['reminder']['systemContext'] = userList[username].services['memory']['obj'].systemContext
  userList[username].functions = userList[username].functions | userList[username].services['reminder']['obj'].functions

  userList[username].tasks = TomBackground(global_config, username, userList[username].services, userList[username])
#  userList[username].services['remember'] = {
#    "obj": TomRemember(global_config, username),
#    "description": "This module is used to manage store user-provided information permanently, indefinitely or enven temporarly. It is about to retain, list or delete facts, data, or context provided by the user for future reference. This is not tied to any specific time but serves as a knowledge repository. You may use these functions to store both permanent information, such as a credit card code, and temporary information that will be useful to the user later, such as remembering where the car was parked or where the keys were placed. This module is used for example when user request is: 'Remember that I parked my car here', 'I left my keys here', 'Where are my keys?', 'Remember my PIN Code is', 'Remember today ...' or even 'Where is my car parked?'", 
#    "tools": [],
#    "complexity": 0,
#    "service_context": "",
#    "functions": {}, 
#  }
#  userList[username].services['remember']['tools'] = userList[username].services['remember']['obj'].tools
#  userList[username].services['remember']['complexity'] = userList[username].services['remember']['obj'].complexity
#  userList[username].services['remember']['service_context'] = userList[username].services['remember']['obj'].systemContext
#  userList[username].functions = userList[username].functions | userList[username].services['remember']['obj'].functions


  #userList[username].services['morningroutine'] = {
  #  "obj": TomMorning(global_config, username),
  #  "description": "", 
  #  "tools": [],
  #  "complexity": 0,
  #  "functions": {}, 
  #}
  #userList[username].services['morningroutine']['tools'] = userList[username].services['morningroutine']['obj'].tools
  #userList[username].services['morningroutine']['complexity'] = userList[username].services['morningroutine']['obj'].complexity
  #userList[username].services['morningroutine']['description'] = userList[username].services['morningroutine']['obj'].systemContext
  #userList[username].functions = userList[username].functions | userList[username].services['morningroutine']['obj'].functions

# Print module loading status summary
TomCoreModules.print_modules_status_summary(module_managers)








if __name__ == "__main__":    

  cherrypy.config.update({
    'server.socket_host': '0.0.0.0', 
    'server.socket_port': 8082, 
    'tools.sessions.on': True, 
    'tools.sessions.timeout': 3600 * 24 * 30,
    'tools.sessions.storage_type': 'file',
    'tools.sessions.storage_path': global_config['global']['sessions'] 
  })
  cherrypy.quickstart(TomWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

