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
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import core modules
core_module_dir = './core_modules'
if core_module_dir not in sys.path:
    sys.path.append(core_module_dir)

from tomcoremodules import TomCoreModules
from tomllm import TomLLM
from tomcorebehavior import TomBehavior
from tomcorememory import TomMemory
from tomcorereminder import TomReminder
from tomlogger import logger, set_log_context
#from tomcoreremember import TomRemember
#from tomcoremorningroutine import TomMorning
from tomcorebackground import TomBackground


################################################################################################
#                                                                                              #
#                              Tom configuration management                                    #
#                                                                                              #
################################################################################################
config = {}

def initConf(config_path='/data/config.yml'):
  # Load config
  with open(config_path, 'r') as file:
    try:
      conf = yaml.safe_load(file)
    except yaml.YAMLError as exc:
      logger.critical(f"Error reading YAML file: {exc}")
      exit(1)

  return conf


################################################################################################
#                                                                                              #
#                                Configuration File Watcher                                   #
#                                                                                              #
################################################################################################

class ConfigFileHandler(FileSystemEventHandler):
  """Handler for config file changes"""
  def __init__(self, config_path, user_modules_dict, global_config, userList):
    self.config_path = config_path
    self.user_modules_dict = user_modules_dict
    self.global_config = global_config
    self.userList = userList
    self.last_modified = 0
    
  def on_modified(self, event):
    if event.src_path == self.config_path:
      # Debounce: ignore rapid successive events
      current_time = time.time()
      if current_time - self.last_modified < 1:
        return
      self.last_modified = current_time
      
      logger.info(f"📝 Configuration file changed: {self.config_path}")
      self._reload_config()
  
  def _reload_config(self):
    """Reload configuration and update modules"""
    try:
      with open(self.config_path, 'r') as file:
        new_config = yaml.safe_load(file)
      
      # Update global config
      self.global_config.clear()
      self.global_config.update(new_config)
      
      # Update user modules
      new_users = {user['username']: user for user in new_config.get('users', [])}
      
      for username, module_manager in self.user_modules_dict.items():
        if username in new_users:
          module_manager.update_modules_config(new_users[username])
        else:
          logger.warning(f"⚠️  User {username} removed from configuration")
      
      # Handle new users (not implemented in this version)
      for username in new_users:
        if username not in self.user_modules_dict:
          logger.warning(f"⚠️  New user {username} found in configuration (restart required)")
      
      logger.config_reload(success=True)
      
    except Exception as e:
      logger.config_reload(success=False)
      logger.error(f"Error reloading configuration: {e}")


class ConfigWatcher:
  """Watches config file for changes"""
  def __init__(self, config_path, user_modules_dict, global_config, userList):
    self.config_path = os.path.abspath(config_path)
    self.config_dir = os.path.dirname(self.config_path)
    self.user_modules_dict = user_modules_dict
    self.global_config = global_config
    self.userList = userList
    self.observer = None
    self.handler = None
    
  def start(self):
    """Start watching the config file"""
    self.handler = ConfigFileHandler(self.config_path, self.user_modules_dict, self.global_config, self.userList)
    self.observer = Observer()
    self.observer.schedule(self.handler, self.config_dir, recursive=False)
    self.observer.start()
    logger.file_watcher(f"📁 Watching config file: {self.config_path}")
    
  def stop(self):
    """Stop watching the config file"""
    if self.observer:
      self.observer.stop()
      self.observer.join()
      logger.file_watcher("⏹️  Stopped watching config file")




        








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

    logger.debug(f"Notifications retrieved: {len(notifications)} items", username)

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
    session_instance = self.get_session_instance()
    if session_instance.reset():
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

    # Set logging context for this request
    set_log_context(username, client_type)
    
    logger.user_request(user_input, username, client_type)

    session_instance = self.get_session_instance()
    response = session_instance.processRequest(input=user_input, lang=lang, position=position, client_type=client_type)

    if response:
      logger.user_response(response, username, client_type)
      return {"response": response} 
    else:
      logger.error(f"Failed to process request: {user_input}", username, client_type)
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


    username = cherrypy.session['username']
    response = userList[username].tasks.tasks
    message = userList[username].tasks.msg
    id = userList[username].tasks.status_id

    logger.debug(f"Tasks retrieved: {len(response) if response else 0} items", username)

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
        logger.auth_event("login", username, "web", success=True)
        logger.info(f"History cleaning for user {username}", username)
        # Clean session-specific history, not user-wide history
        session_instance = self.get_session_instance()
        session_instance.reset()

        raise cherrypy.HTTPRedirect("/index")

    logger.auth_event("login", username, "web", success=False)
    return "Invalid credentials. <a href='/auth'>Try again</a>"



  def check_auth(self):
    if cherrypy.session.get('username', None) is not None:
      return True
      
    raise cherrypy.HTTPRedirect("/auth")
  
  def get_session_instance(self):
    """Get or create a session-specific TomLLM instance"""
    username = cherrypy.session['username']
    session_id = cherrypy.session.id
    
    # Create unique key for this session
    session_key = f"{username}_{session_id}"
    
    if session_key not in session_instances:
      # Create a new instance based on the user's base configuration
      base_instance = userList[username]
      
      # Create user config from global config
      user_config = None
      for user in global_config['users']:
        if user['username'] == username:
          user_config = user
          break
      
      # Create new session-specific instance
      session_instance = TomLLM(user_config, global_config)
      session_instance.admin = base_instance.admin
      session_instance.services = base_instance.services
      session_instance.functions = base_instance.functions
      session_instance.tasks = base_instance.tasks
      
      session_instances[session_key] = session_instance
    
    return session_instances[session_key]
  
  def cleanup_session_on_logout(self):
    """Clean up session-specific instance when user logs out"""
    username = cherrypy.session.get('username')
    session_id = cherrypy.session.id
    
    if username:
      session_key = f"{username}_{session_id}"
      if session_key in session_instances:
        del session_instances[session_key]
        logger.info(f"Cleaned up session instance for {session_key}", username)

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

# Get config file path from command line argument or use default
config_file_path = sys.argv[1] if len(sys.argv) > 1 else '/data/config.yml'
logger.startup(f"Using config file: {config_file_path}")

global_config = initConf(config_file_path)
# Add config file path to global config for use in modules
global_config['config_path'] = config_file_path



userList = {}
module_managers = {}
# Session-specific user instances
session_instances = {}

# First pass: create all module managers
for user in global_config['users']:
  username = user['username']
  llm_instance = TomLLM(user, global_config)
  userList[username] = llm_instance
  
  # Set admin status (default: False if not specified)
  userList[username].admin = user.get('admin', False)
  
  # Load modules using TomCoreModules (without module_managers reference initially)
  module_manager = TomCoreModules(global_config, user, llm_instance)
  userList[username].services = module_manager.services
  userList[username].functions = module_manager.functions
  module_managers[username] = module_manager

# Second pass: add module_managers reference to each module manager and register services
for username, module_manager in module_managers.items():
  module_manager.module_managers = module_managers
  
  # Register tomcoremodules as a service for user queries
  userList[username].services['modules'] = {
    "obj": module_manager,
    "description": "This module manages the status and loading of of Tom's extension modules. Use this when the user asks about it's own or someone else Tom's module status, available modules, or wants to know what modules are currently active.",
    "systemContext": module_manager.systemContext,
    "tools": module_manager.tools,
    "complexity": module_manager.complexity,
    "functions": module_manager.functions
  }
  # Update functions with module metadata for extension modules
  for func_name, func_data in module_manager.functions.items():
    if isinstance(func_data, dict) and 'module_name' in func_data:
      userList[username].functions[func_name] = func_data
    else:
      # Handle legacy format - add module metadata
      userList[username].functions[func_name] = {
        "function": func_data['function'] if isinstance(func_data, dict) else func_data,
        "module_name": "modules" if isinstance(func_data, dict) else "modules"
      }
    
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
  # Update functions with module metadata for behavior module
  for func_name, func_data in userList[username].services['behavior']['obj'].functions.items():
    userList[username].functions[func_name] = {
      "function": func_data['function'] if isinstance(func_data, dict) else func_data,
      "module_name": "behavior"
    }

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
  # Update functions with module metadata for memory module
  for func_name, func_data in userList[username].services['memory']['obj'].functions.items():
    userList[username].functions[func_name] = {
      "function": func_data['function'] if isinstance(func_data, dict) else func_data,
      "module_name": "memory"
    }
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
  # Update functions with module metadata for reminder module
  for func_name, func_data in userList[username].services['reminder']['obj'].functions.items():
    userList[username].functions[func_name] = {
      "function": func_data['function'] if isinstance(func_data, dict) else func_data,
      "module_name": "reminder"
    }

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

# Start config file watcher
config_watcher = ConfigWatcher(config_file_path, module_managers, global_config, userList)
config_watcher.start()








if __name__ == "__main__":    

  cherrypy.config.update({
    'server.socket_host': '0.0.0.0', 
    'server.socket_port': 8082, 
    'tools.sessions.on': True, 
    'tools.sessions.timeout': 3600 * 24 * 30,
    'tools.sessions.storage_type': 'file',
    'tools.sessions.storage_path': global_config['global']['sessions'] 
  })
  try:
    cherrypy.quickstart(TomWebService(), '/', config={
        '/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.abspath('static')
        }
    })
  except KeyboardInterrupt:
    logger.shutdown("Shutting down...")
    config_watcher.stop()

