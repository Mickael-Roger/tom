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
from tomcoremessage import TomMessage
from tomcoremorningreminder import TomCoreMorningReminder
from tomlogger import logger, set_log_context, init_logger
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

class ConfigChangeNotifier(FileSystemEventHandler):
  """Handler to log config file changes and identify modifications"""
  def __init__(self, config_path):
    self.config_path = os.path.abspath(config_path)
    self.last_modified = 0
    self.debounce_time = 2  # 2 seconds to ensure file operations are complete
    self.previous_config = None
    self._load_initial_config()
    
  def _load_initial_config(self):
    """Load the initial configuration state"""
    try:
      with open(self.config_path, 'r') as file:
        self.previous_config = yaml.safe_load(file)
      logger.debug(f"Initial config state loaded for monitoring: {self.config_path}")
    except Exception as e:
      logger.error(f"Failed to load initial config state: {e}")
      self.previous_config = {}
    
  def on_modified(self, event):
    if event.src_path == self.config_path and not event.is_directory:
      # Debounce: ignore rapid successive events
      current_time = time.time()
      if current_time - self.last_modified < self.debounce_time:
        return
      self.last_modified = current_time
      
      # Wait a bit more to ensure file is completely written and lock is released
      time.sleep(0.5)
      
      # Verify we can read the file (no lock) and analyze changes
      if self._is_file_accessible():
        self._analyze_and_log_changes()
      else:
        # File might still be locked, try again after a longer delay
        time.sleep(1.5)
        if self._is_file_accessible():
          self._analyze_and_log_changes()
        else:
          logger.warning(f"⚠️  Configuration file modification detected but file appears to be locked: {self.config_path}")
  
  def _is_file_accessible(self):
    """Check if file is accessible (not locked)"""
    try:
      with open(self.config_path, 'r') as f:
        # Try to read first few bytes to ensure file is accessible
        f.read(10)
      return True
    except (IOError, OSError):
      return False
  
  def _analyze_and_log_changes(self):
    """Analyze what changed in the configuration and log details"""
    try:
      # Load new config
      with open(self.config_path, 'r') as file:
        new_config = yaml.safe_load(file)
      
      if self.previous_config is None:
        logger.info(f"📝 Configuration file modified: {self.config_path} - Unable to determine changes (no previous state)")
        self.previous_config = new_config
        return
      
      # Analyze changes
      changes = self._detect_changes(self.previous_config, new_config)
      
      if changes:
        logger.info(f"📝 Configuration file modified: {self.config_path}")
        for change in changes:
          logger.info(f"   🔄 {change}")
        
        # Check if changes are hot-reloadable (user service enable/disable)
        hot_reload_candidates = self._get_hot_reload_candidates(changes)
        
        if hot_reload_candidates:
          logger.info("   🔥 Attempting hot reload for detected changes...")
          
          # Update global config first
          global global_config
          global_config = new_config
          
          # Hot reload affected users
          for username in hot_reload_candidates:
            success = reload_user_configuration(username)
            if success:
              logger.info(f"   ✅ Hot reload successful for user: {username}")
            else:
              logger.error(f"   ❌ Hot reload failed for user: {username}")
          
          logger.info("   🎯 Hot reload completed - No restart required!")
        else:
          logger.info("   ⚠️  Manual restart required to apply changes")
      else:
        logger.info(f"📝 Configuration file modified: {self.config_path} - No structural changes detected")
      
      # Update previous config for next comparison
      self.previous_config = new_config
      
    except Exception as e:
      logger.error(f"Error analyzing config changes: {e}")
      logger.info(f"📝 Configuration file modified: {self.config_path} - Manual restart required to apply changes")
  
  def _get_hot_reload_candidates(self, changes):
    """Identify users that can be hot reloaded based on changes"""
    hot_reload_users = set()
    
    for change in changes:
      # Look for user service enable/disable changes
      if "service" in change and ("enabled" in change or "disabled" in change):
        # Extract username from change message
        # Format: "User 'username': service 'servicename' enabled/disabled"
        if "User '" in change:
          start = change.find("User '") + 6
          end = change.find("'", start)
          if start < end:
            username = change[start:end]
            hot_reload_users.add(username)
            logger.debug(f"   🎯 User '{username}' candidate for hot reload due to: {change}")
      
      # Look for user service additions/removals  
      elif "service" in change and ("added" in change or "removed" in change):
        if "User '" in change:
          start = change.find("User '") + 6
          end = change.find("'", start)
          if start < end:
            username = change[start:end]
            hot_reload_users.add(username)
            logger.debug(f"   🎯 User '{username}' candidate for hot reload due to: {change}")
    
    return list(hot_reload_users)
  
  def _detect_changes(self, old_config, new_config):
    """Detect and describe changes between old and new configuration"""
    changes = []
    
    # Check global config changes
    old_global = old_config.get('global', {})
    new_global = new_config.get('global', {})
    
    if old_global != new_global:
      global_changes = self._compare_dicts(old_global, new_global, "global")
      changes.extend(global_changes)
    
    # Check services changes
    old_services = old_config.get('services', {})
    new_services = new_config.get('services', {})
    
    if old_services != new_services:
      service_changes = self._compare_dicts(old_services, new_services, "services")
      changes.extend(service_changes)
    
    # Check users changes
    old_users = {user.get('username', 'unknown'): user for user in old_config.get('users', [])}
    new_users = {user.get('username', 'unknown'): user for user in new_config.get('users', [])}
    
    # Detect user additions/removals
    added_users = set(new_users.keys()) - set(old_users.keys())
    removed_users = set(old_users.keys()) - set(new_users.keys())
    
    for username in added_users:
      changes.append(f"User added: '{username}'")
    
    for username in removed_users:
      changes.append(f"User removed: '{username}'")
    
    # Check changes in existing users
    for username in set(old_users.keys()) & set(new_users.keys()):
      old_user = old_users[username]
      new_user = new_users[username]
      
      if old_user != new_user:
        user_changes = self._compare_user_config(old_user, new_user, username)
        changes.extend(user_changes)
    
    return changes
  
  def _compare_dicts(self, old_dict, new_dict, section_name):
    """Compare two dictionaries and return list of changes"""
    changes = []
    
    # Check for added/removed keys
    old_keys = set(old_dict.keys())
    new_keys = set(new_dict.keys())
    
    added_keys = new_keys - old_keys
    removed_keys = old_keys - new_keys
    
    for key in added_keys:
      changes.append(f"Added to {section_name}: '{key}'")
    
    for key in removed_keys:
      changes.append(f"Removed from {section_name}: '{key}'")
    
    # Check for modified values
    for key in old_keys & new_keys:
      if old_dict[key] != new_dict[key]:
        changes.append(f"Modified in {section_name}: '{key}' changed")
    
    return changes
  
  def _compare_user_config(self, old_user, new_user, username):
    """Compare user configurations and detect changes"""
    changes = []
    
    # Check basic user properties
    for key in ['password', 'admin', 'memory']:
      old_val = old_user.get(key)
      new_val = new_user.get(key)
      if old_val != new_val:
        if key == 'password':
          changes.append(f"User '{username}': password changed")
        else:
          changes.append(f"User '{username}': {key} changed from {old_val} to {new_val}")
    
    # Check services changes
    old_services = old_user.get('services', {})
    new_services = new_user.get('services', {})
    
    if old_services != new_services:
      # Detect added/removed/modified services for this user
      old_service_keys = set(old_services.keys())
      new_service_keys = set(new_services.keys())
      
      added_services = new_service_keys - old_service_keys
      removed_services = old_service_keys - new_service_keys
      
      for service in added_services:
        changes.append(f"User '{username}': service '{service}' added")
      
      for service in removed_services:
        changes.append(f"User '{username}': service '{service}' removed")
      
      # Check for modifications in existing services
      for service in old_service_keys & new_service_keys:
        old_service_config = old_services[service]
        new_service_config = new_services[service]
        
        if old_service_config != new_service_config:
          # Check if it's just an enable/disable change
          if (isinstance(old_service_config, dict) and isinstance(new_service_config, dict) and
              old_service_config.get('enable') != new_service_config.get('enable')):
            old_enable = old_service_config.get('enable', True)
            new_enable = new_service_config.get('enable', True)
            status = "enabled" if new_enable else "disabled"
            changes.append(f"User '{username}': service '{service}' {status}")
          else:
            changes.append(f"User '{username}': service '{service}' configuration changed")
    
    return changes


class ConfigWatcher:
  """Watches config file for changes and logs them"""
  def __init__(self, config_path):
    self.config_path = os.path.abspath(config_path)
    self.config_dir = os.path.dirname(self.config_path)
    self.observer = None
    self.handler = None
    
  def start(self):
    """Start watching the config file"""
    self.handler = ConfigChangeNotifier(self.config_path)
    self.observer = Observer()
    self.observer.schedule(self.handler, self.config_dir, recursive=False)
    self.observer.start()
    logger.file_watcher(f"👀 Watching config file for changes: {self.config_path}")
    
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
    position = input_json.get('position')
    client_type = input_json.get('client_type', 'pwa')
    sound_enabled = input_json.get('sound_enabled', False)
    username = cherrypy.session['username']

    # Set logging context for this request
    set_log_context(username, client_type)
    
    logger.user_request(user_input, username, client_type)

    session_instance = self.get_session_instance()
    response = session_instance.processRequest(input=user_input, position=position, client_type=client_type, sound_enabled=sound_enabled)

    if response:
      # Handle both old format (string) and new format (dict with text_display/text_tts)
      if isinstance(response, dict) and "text_display" in response and "text_tts" in response:
        logger.user_response(response["text_display"], username, client_type)
        return {
          "response": response["text_display"],
          "response_tts": response["text_tts"]
        }
      else:
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
    id = userList[username].tasks.status_id

    logger.debug(f"Tasks retrieved: {len(response) if response else 0} items", username)

    if response:
      return {"background_tasks": response, "id": id} 
    else:
      return {"background_tasks": [], "id": 0} 




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
      # Check if user exists in userList (may have been hot reloaded)
      if username not in userList:
        logger.error(f"User {username} not found in userList during session creation")
        raise cherrypy.HTTPError(500, f"User {username} not available")
      
      # Create a new instance based on the user's base configuration
      base_instance = userList[username]
      
      # Verify the base instance is properly initialized
      if not hasattr(base_instance, 'services') or not hasattr(base_instance, 'functions'):
        logger.error(f"Base instance for {username} is not properly initialized")
        raise cherrypy.HTTPError(500, f"User {username} configuration incomplete")
      
      # Create user config from global config
      user_config = None
      for user in global_config['users']:
        if user['username'] == username:
          user_config = user
          break
      
      if not user_config:
        logger.error(f"User config not found for {username}")
        raise cherrypy.HTTPError(500, f"User {username} configuration not found")
      
      # Create new session-specific instance
      session_instance = TomLLM(user_config, global_config)
      session_instance.admin = base_instance.admin
      session_instance.services = base_instance.services
      session_instance.functions = base_instance.functions
      # Only set tasks if it exists (may not exist during hot reload)
      if hasattr(base_instance, 'tasks'):
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

    db_path = global_config['global']['all_datadir']
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

# Initialize logger with default level first for startup messages
logger = init_logger('INFO')
logger.startup(f"Using config file: {config_file_path}")

global_config = initConf(config_file_path)
# Add config file path to global config for use in modules
global_config['config_path'] = config_file_path

# Re-initialize logger with log_level from config (default to 'INFO' if not specified)
log_level = global_config.get('global', {}).get('log_level', 'INFO')
logger = init_logger(log_level)
logger.startup(f"Log level set to: {log_level}")



def create_user_instance(user_config, target_username=None):
  """Create or recreate a user instance with all modules and services"""
  username = user_config['username']
  
  if target_username and username != target_username:
    return  # Skip users we're not targeting
  
  logger.info(f"🏗️  Creating user instance for: {username}")
  
  # Create the base LLM instance
  llm_instance = TomLLM(user_config, global_config)
  userList[username] = llm_instance
  
  # Set admin status (default: False if not specified)
  userList[username].admin = user_config.get('admin', False)
  
  # Load modules using TomCoreModules
  module_manager = TomCoreModules(global_config, user_config, llm_instance)
  userList[username].services = module_manager.services
  userList[username].functions = module_manager.functions
  module_managers[username] = module_manager
  
  # Add module_managers reference to this module manager
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

  memory_obj = TomMemory(global_config, username, userList[username])
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

  message_obj = TomMessage(global_config, username)
  userList[username].services['message'] = {
    "obj": message_obj,
    "description": message_obj.tom_config["description"], 
    "systemContext": "",
    "tools": [],
    "complexity": 0,
    "functions": {}, 
  }
  userList[username].services['message']['tools'] = userList[username].services['message']['obj'].tools
  userList[username].services['message']['complexity'] = userList[username].services['message']['obj'].complexity
  userList[username].services['message']['systemContext'] = userList[username].services['message']['obj'].systemContext
  # Update functions with module metadata for message module
  for func_name, func_data in userList[username].services['message']['obj'].functions.items():
    userList[username].functions[func_name] = {
      "function": func_data['function'] if isinstance(func_data, dict) else func_data,
      "module_name": "message"
    }

  morning_reminder_obj = TomCoreMorningReminder(global_config, username)
  # Set LLM reference after creation
  morning_reminder_obj.llm = userList[username]
  userList[username].services['morningreminder'] = {
    "obj": morning_reminder_obj,
    "description": morning_reminder_obj.tom_config["description"], 
    "systemContext": "",
    "tools": [],
    "complexity": 0,
    "functions": {}, 
  }
  userList[username].services['morningreminder']['tools'] = userList[username].services['morningreminder']['obj'].tools
  userList[username].services['morningreminder']['complexity'] = userList[username].services['morningreminder']['obj'].complexity
  userList[username].services['morningreminder']['systemContext'] = userList[username].services['morningreminder']['obj'].systemContext
  # Update functions with module metadata for morning reminder module
  for func_name, func_data in userList[username].services['morningreminder']['obj'].functions.items():
    userList[username].functions[func_name] = {
      "function": func_data['function'] if isinstance(func_data, dict) else func_data,
      "module_name": "morningreminder"
    }

  userList[username].tasks = TomBackground(global_config, username, userList[username].services, userList[username])
  
  logger.info(f"✅ User instance created for {username} with {len(userList[username].services)} services and {len(userList[username].functions)} functions")


def reload_user_configuration(username):
  """Hot reload a specific user's configuration and modules"""
  logger.info(f"🔄 Hot reloading configuration for user: {username}")
  
  # Find the user config in global_config
  user_config = None
  for user in global_config['users']:
    if user['username'] == username:
      user_config = user
      break
      
  if not user_config:
    logger.error(f"❌ User {username} not found in configuration")
    return False
  
  # Clean up existing session instances for this user
  session_keys_to_remove = [key for key in session_instances.keys() if key.startswith(f"{username}_")]
  for session_key in session_keys_to_remove:
    del session_instances[session_key]
    logger.info(f"🧹 Cleaned up session instance: {session_key}")
  
  # Remove existing user instance
  if username in userList:
    logger.info(f"🗑️  Removing existing user instance for: {username}")
    del userList[username]
  
  if username in module_managers:
    del module_managers[username]
  
  # Recreate the user instance
  create_user_instance(user_config, target_username=username)
  
  logger.info(f"✅ Hot reload completed for user: {username}")
  return True


userList = {}
module_managers = {}
# Session-specific user instances
session_instances = {}

# Create all user instances
for user in global_config['users']:
  create_user_instance(user)

# Print module loading status summary
TomCoreModules.print_modules_status_summary(module_managers)

# Start config file change notifier (logs changes only, no reload)
config_watcher = ConfigWatcher(config_file_path)
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

