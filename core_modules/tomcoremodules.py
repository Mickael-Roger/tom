import os
import importlib.util
import inspect
import functools
import yaml
import shutil
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tomlogger

class ModuleFileHandler(FileSystemEventHandler):
  """Handler for file system events on module files"""
  def __init__(self, module_manager):
    self.module_manager = module_manager
    self.last_modified = {}
    self.debounce_time = 1  # 1 second debounce to avoid multiple reloads
    self.sync_in_progress = False  # Flag to ignore events during sync
    
  def on_modified(self, event):
    if event.is_directory:
      return
      
    # Ignore events during sync operations
    if self.sync_in_progress:
      return
      
    if event.src_path.endswith('.py') and not event.src_path.endswith('__init__.py'):
      # Debounce: ignore if file was modified recently
      current_time = time.time()
      if (event.src_path in self.last_modified and 
          current_time - self.last_modified[event.src_path] < self.debounce_time):
        return
        
      self.last_modified[event.src_path] = current_time
      
      # Extract module name from filename
      filename = os.path.basename(event.src_path)
      module_name = filename[:-3]  # Remove .py extension
      
      tomlogger.info(f"🔄 Module file changed: {filename}")
      
      # Trigger hot reload in a separate thread to avoid blocking the file watcher
      threading.Thread(target=self._hot_reload_module, args=(module_name,), daemon=True).start()
      
  def _hot_reload_module(self, module_name):
    """Reload a module for all users who have it loaded"""
    try:
      # First, reload the module definition in the module_list
      self.module_manager._reload_module_definition(module_name)
      
      # Then reload the module for all users who have it loaded
      if self.module_manager.module_managers:
        for username, user_module_manager in self.module_manager.module_managers.items():
          if module_name in user_module_manager.services:
            (tomlogger.logger.module_reload if tomlogger.logger else lambda *args, **kwargs: None)(module_name, username, success=True)
            user_module_manager._hot_reload_single_module(module_name)
      
      # Also reload for the current module manager if it has the module loaded
      if module_name in self.module_manager.services:
        (tomlogger.logger.module_reload if tomlogger.logger else lambda *args, **kwargs: None)(module_name, success=True)
        self.module_manager._hot_reload_single_module(module_name)
        
    except Exception as e:
      (tomlogger.logger.module_reload if tomlogger.logger else lambda *args, **kwargs: None)(module_name, success=False)
      tomlogger.error(f"Error during hot reload of module '{module_name}': {e}")

class TomCoreModules:
  # Class variables to handle global state
  _sync_done = False
  _file_observer = None
  _event_handler = None
  _module_list_global = {}  # Global module list shared across instances
  
  def __init__(self, global_config, user_config, llm_instance, module_managers=None):
    self.global_config = global_config
    self.user_config = user_config
    self.llm_instance = llm_instance
    self.module_managers = module_managers  # Reference to all user module managers
    self.services = {}
    self.functions = {}
    self.module_list = {}
    self.module_status = {}  # Track module loading status
    
    # Only sync once across all instances
    if not TomCoreModules._sync_done:
      self._sync_modules_directory()
      TomCoreModules._sync_done = True
    
    self._load_module_list()
    self._load_user_modules()
    
    # Start file watcher only once, globally
    if TomCoreModules._file_observer is None:
      self._start_file_watcher()
    
    # Initialize tools and functions for module status functionality
    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "list_modules_status",
          "description": "List the status of Tom's modules. Use this when the user asks about module status, available modules, or wants to know what modules are currently active.",
          "parameters": {
            "type": "object",
            "properties": {
              "username": {
                "type": "string",
                "description": "Optional: specific username to get status for. Th user itself by default. Must not be used unless another user is explicitly specified by the user."
              }
            },
            "required": [],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "toggle_module_status",
          "description": "Enable or disable a module for a specific user (admin only). This modifies the config.yml file to change the enable status of a module.",
          "parameters": {
            "type": "object",
            "properties": {
              "username": {
                "type": "string",
                "description": "Username for which to toggle the module status"
              },
              "module_name": {
                "type": "string",
                "description": "Name of the module to enable/disable"
              },
              "enable": {
                "type": "boolean",
                "description": "True to enable the module, False to disable it"
              }
            },
            "required": ["username", "module_name", "enable"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "restart_module",
          "description": "Restart a module that is in error state.",
          "parameters": {
            "type": "object",
            "properties": {
              "module_name": {
                "type": "string",
                "description": "Name of the module to restart"
              }
            },
            "required": ["module_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "get_module_configuration_parameters",
          "description": "Get the configuration parameters expected by a specific module. This shows what parameters can be configured for the module in config.yml.",
          "parameters": {
            "type": "object",
            "properties": {
              "module_name": {
                "type": "string",
                "description": "Name of the module to get configuration parameters for"
              }
            },
            "required": ["module_name"],
            "additionalProperties": False,
          },
        }
      }
    ]
    
    self.systemContext = "This module manages the loading and status of extension modules. It can provide information about which modules are currently loaded, disabled, or have errors."
    self.complexity = 0
    
    # Add core module functions AFTER user modules are loaded
    self.functions.update({
      "list_modules_status": {
        "function": functools.partial(self.list_modules_status)
      },
      "toggle_module_status": {
        "function": functools.partial(self.toggle_module_status)
      },
      "restart_module": {
        "function": functools.partial(self.restart_module)
      },
      "get_module_configuration_parameters": {
        "function": functools.partial(self.get_module_configuration_parameters)
      }
    })

  def _load_module_list(self):
    # Use global module list if already loaded and contains filename info
    if TomCoreModules._module_list_global:
      # Check if the first module has filename info, if not, force reload
      first_module_key = next(iter(TomCoreModules._module_list_global), None)
      if first_module_key and 'filename' in TomCoreModules._module_list_global[first_module_key]:
        self.module_list = TomCoreModules._module_list_global.copy()
        return
      else:
        # Force reload to add filename information
        TomCoreModules._module_list_global = {}
    
    # Load modules from /data/modules
    mod_dir = '/data/modules'
    for filename in os.listdir(mod_dir):
      if filename.endswith('.py') and filename != '__init__.py':
        module_name = filename[:-3]
        file_path = os.path.join(mod_dir, filename)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec:
          module = importlib.util.module_from_spec(spec)
          if spec.loader:
            spec.loader.exec_module(module)
            for name, obj in inspect.getmembers(module, inspect.isclass):
              globals()[name] = obj
            if hasattr(module, 'tom_config'):
              tom_mod_config = getattr(module, 'tom_config')
              self.module_list[tom_mod_config['module_name']] = {
                "class": tom_mod_config['class_name'],
                "description": tom_mod_config['description'],
                "type": tom_mod_config.get('type', 'global'),
                "filename": filename  # Store the actual filename
              }
    
    # Store in global module list
    TomCoreModules._module_list_global = self.module_list.copy()

  def _sync_modules_directory(self):
    """Create /data/modules directory if it doesn't exist and sync with ./modules"""
    data_modules_dir = '/data/modules'
    source_modules_dir = './modules'
    
    tomlogger.info("📋 Starting modules synchronization...")
    
    # Create /data/modules directory if it doesn't exist
    os.makedirs(data_modules_dir, exist_ok=True)
    
    # Copy all files from ./modules to /data/modules
    # This will overwrite existing files but preserve files that don't exist in ./modules
    if os.path.exists(source_modules_dir):
      for filename in os.listdir(source_modules_dir):
        if filename.endswith('.py'):
          source_file = os.path.join(source_modules_dir, filename)
          dest_file = os.path.join(data_modules_dir, filename)
          try:
            shutil.copy2(source_file, dest_file)
            (tomlogger.logger.file_sync if tomlogger.logger else lambda *args, **kwargs: None)(filename, success=True)
          except Exception as e:
            (tomlogger.logger.file_sync if tomlogger.logger else lambda *args, **kwargs: None)(filename, success=False)
            tomlogger.error(f"Error copying module {filename}: {e}")
    else:
      tomlogger.warning(f"Source modules directory {source_modules_dir} does not exist")
    
    tomlogger.info("✅ Modules synchronization complete!")

  def _start_file_watcher(self):
    """Start watching the /data/modules directory for file changes"""
    try:
      modules_dir = '/data/modules'
      if not os.path.exists(modules_dir):
        tomlogger.warning(f"Modules directory {modules_dir} does not exist, file watching disabled")
        return
        
      TomCoreModules._file_observer = Observer()
      TomCoreModules._event_handler = ModuleFileHandler(self)
      TomCoreModules._file_observer.schedule(TomCoreModules._event_handler, modules_dir, recursive=False)
      TomCoreModules._file_observer.start()
      tomlogger.logger.file_watcher(f"Started file watcher for {modules_dir}")
      
    except Exception as e:
      tomlogger.error(f"Error starting file watcher: {e}")
      
  @classmethod
  def _stop_file_watcher(cls):
    """Stop the file watcher"""
    if cls._file_observer:
      cls._file_observer.stop()
      cls._file_observer.join()
      cls._file_observer = None
      cls._event_handler = None
      tomlogger.logger.file_watcher("File watcher stopped")
      
  def _reload_module_definition(self, module_name):
    """Reload a module definition from file"""
    try:
      modules_dir = '/data/modules'
      filename = f"{module_name}.py"
      file_path = os.path.join(modules_dir, filename)
      
      if not os.path.exists(file_path):
        tomlogger.error(f"Module file not found: {file_path}")
        return False
        
      # Clear the module from globals if it exists
      # This is necessary to force Python to reload the module
      if module_name in globals():
        del globals()[module_name]
        
      # Load the module
      spec = importlib.util.spec_from_file_location(module_name, file_path)
      if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Update globals with new classes
        for name, obj in inspect.getmembers(module, inspect.isclass):
          globals()[name] = obj
          
        # Update module_list if the module has tom_config
        if hasattr(module, 'tom_config'):
          tom_mod_config = getattr(module, 'tom_config')
          module_info = {
            "class": tom_mod_config['class_name'],
            "description": tom_mod_config['description'],
            "type": tom_mod_config.get('type', 'global'),
            "filename": f"{module_name}.py"  # Store the actual filename
          }
          self.module_list[tom_mod_config['module_name']] = module_info
          # Update global module list
          TomCoreModules._module_list_global[tom_mod_config['module_name']] = module_info
          tomlogger.info(f"✅ Module definition reloaded: {module_name}")
          return True
      
      return False
      
    except Exception as e:
      tomlogger.error(f"Error reloading module definition for {module_name}: {e}")
      return False
      
  def _hot_reload_single_module(self, module_name):
    """Hot reload a single module for this user"""
    try:
      if module_name not in self.services:
        tomlogger.logger.debug(f"Module '{module_name}' not loaded for user {self.user_config['username']}", self.user_config['username'])
        return False
        
      # Get the current module config
      service_config = self.user_config['services'][module_name]
      
      # Unload the current module
      self._unload_single_module(module_name)
      
      # Reload the module
      success = self._load_single_module(module_name)
      
      if success:
        # Synchronize functions to the main user instance in userList
        self._sync_functions_to_user_instance()
        
        tomlogger.info(f"✅ Hot reload successful for module '{module_name}'", self.user_config['username'])
        return True
      else:
        tomlogger.error(f"❌ Hot reload failed for module '{module_name}'", self.user_config['username'])
        return False
        
    except Exception as e:
      tomlogger.error(f"Error during hot reload of module '{module_name}': {e}", self.user_config['username'])
      return False
      
  def _sync_functions_to_user_instance(self):
    """Sync functions and tools to the main user instance in userList"""
    try:
      # We need to access the global userList to update the functions and tools
      # This is a bit of a hack, but necessary for the current architecture
      import __main__
      if hasattr(__main__, 'userList'):
        username = self.user_config['username']
        if username in __main__.userList:
          # Update the userList functions with our current functions
          __main__.userList[username].functions.clear()
          __main__.userList[username].functions.update(self.functions)
          
          # Update the userList tools with our current tools
          # Collect all tools from all loaded services
          all_tools = []
          for service_name, service_info in self.services.items():
            if 'tools' in service_info:
              all_tools.extend(service_info['tools'])
          
          # Update the tools in userList
          if hasattr(__main__.userList[username], 'tools'):
            __main__.userList[username].tools = all_tools
          
          tomlogger.logger.debug(f"Functions and tools synchronized for user {username}", username)
    except Exception as e:
      tomlogger.error(f"Error synchronizing functions to user instance: {e}", self.user_config['username'])

  def __del__(self):
    """Cleanup when the object is destroyed"""
    # Only stop file watcher if this is the last instance
    # In practice, this should be handled by the main application
    pass

  def _get_module_llm_instance(self, service_name, service_config):
    """Get the appropriate LLM instance for a module"""
    tomlogger.debug(f"🔍 Checking LLM config for module '{service_name}'", self.user_config['username'])
    
    # Always check global services first for LLM configuration
    module_llm = None
    if 'services' in self.global_config and service_name in self.global_config['services']:
      global_service_config = self.global_config['services'][service_name]
      if isinstance(global_service_config, dict):
        module_llm = global_service_config.get('llm')
        tomlogger.debug(f"📋 Found global LLM config for '{service_name}': {module_llm}", self.user_config['username'])
    
    # Fallback to module service_config if no global LLM config (for backward compatibility)
    if not module_llm:
      module_llm = service_config.get('llm')
      tomlogger.debug(f"📋 Using service config LLM for '{service_name}': {module_llm}", self.user_config['username'])
    
    tomlogger.debug(f"📋 Module '{service_name}' final LLM config: {module_llm} (default: {self.llm_instance.llm})", self.user_config['username'])
    
    if module_llm and module_llm != self.llm_instance.llm:
      # Module wants a different LLM than the default
      if module_llm in self.llm_instance.llms:
        # Create a new LLM instance with the specified LLM
        import copy
        module_llm_instance = copy.copy(self.llm_instance)
        module_llm_instance.llm = module_llm
        tomlogger.info(f"✅ Module '{service_name}' using custom LLM: {module_llm}", self.user_config['username'])
        return module_llm_instance
      else:
        tomlogger.warning(f"❌ Module '{service_name}' requested unavailable LLM '{module_llm}', using default '{self.llm_instance.llm}'. Available LLMs: {list(self.llm_instance.llms.keys())}", self.user_config['username'])
    else:
      tomlogger.debug(f"🔄 Module '{service_name}' using default LLM: {self.llm_instance.llm}", self.user_config['username'])
    
    # Use default LLM instance
    return self.llm_instance

  def _get_module_config(self, service_name):
    """Get configuration for a module based on its type (global or personal)"""
    if service_name not in self.module_list:
      tomlogger.debug(f"Module {service_name} not found in module_list", self.user_config['username'])
      return None, False
    
    module_type = self.module_list[service_name].get('type', 'global')
    tomlogger.debug(f"Module {service_name} has type: {module_type}", self.user_config['username'])
    
    if module_type == 'global':
      # Global modules: config from root services, enable from user services
      tomlogger.debug(f"Looking for global module {service_name}", self.user_config['username'])
      
      # Check if user has enabled this global module
      user_has_module = 'services' in self.user_config and service_name in self.user_config['services']
      if not user_has_module:
        tomlogger.debug(f"Global module {service_name} not enabled for user", self.user_config['username'])
        return None, False
        
      # Get enable status from user config
      user_config = self.user_config['services'][service_name]
      is_enabled = user_config.get('enable', True) if isinstance(user_config, dict) else True
      
      if not is_enabled:
        tomlogger.debug(f"Global module {service_name} disabled by user", self.user_config['username'])
        return None, False
      
      # Get actual configuration from global services
      if 'services' in self.global_config and service_name in self.global_config['services']:
        service_config = self.global_config['services'][service_name].copy()
        # Add all_datadir to global module config
        service_config['all_datadir'] = self.global_config.get('all_datadir', '/data/all/')
        tomlogger.debug(f"Global module {service_name} found and enabled", self.user_config['username'])
        return service_config, is_enabled
      else:
        # Global module not configured globally - use default config
        service_config = {
          'all_datadir': self.global_config.get('all_datadir', '/data/all/')
        }
        tomlogger.debug(f"Global module {service_name} not found in global services, using default config", self.user_config['username'])
        return service_config, is_enabled
    else:
      # Personal modules get config from user.services
      tomlogger.debug(f"Looking for personal module {service_name} in user services", self.user_config['username'])
      
      if 'services' in self.user_config and service_name in self.user_config['services']:
        service_config = self.user_config['services'][service_name]
        is_enabled = service_config.get('enable', True) if isinstance(service_config, dict) else True
        tomlogger.debug(f"Personal module {service_name} found, enabled: {is_enabled}", self.user_config['username'])
        return service_config, is_enabled
      else:
        # Personal module not configured for this user - skip
        user_services = self.user_config.get('services', {})
        tomlogger.debug(f"Personal module {service_name} not found in user services. Available user services: {list(user_services.keys())}", self.user_config['username'])
        return None, False

  def _load_user_modules(self):
    # Load all available modules (both global and personal)
    all_modules_to_load = set()
    
    # Add global modules from root-level services
    if 'services' in self.global_config:
      all_modules_to_load.update(self.global_config['services'].keys())
    
    # Add personal modules from user.services
    if 'services' in self.user_config:
      all_modules_to_load.update(self.user_config['services'].keys())
    
    for service_name in all_modules_to_load:
      try:
        # Get configuration based on module type
        service_config, is_enabled = self._get_module_config(service_name)
        
        if service_config is None:
          # Module not configured for this user/globally
          continue
          
        if not is_enabled:
          self.module_status[service_name] = 'disabled'
          continue
        
        if service_name not in self.module_list:
          self.module_status[service_name] = 'error'
          tomlogger.error(f"Module '{service_name}' not found in available modules", self.user_config['username'])
          continue
        
        self.module_status[service_name] = 'loading'
        tomlogger.logger.debug(f"Loading module '{service_name}'", self.user_config['username'])
        
        module_info = self.module_list[service_name]
        module_class_name = module_info['class']
        
        # Find the class in the loaded modules
        module_class = None
        for mod_name, mod_info in self.module_list.items():
            if mod_info['class'] == module_class_name:
                # The class should be in globals now
                if module_class_name in globals():
                    module_class = globals()[module_class_name]
                    break
        
        if module_class:
          # Check if module specifies a custom LLM
          module_llm_instance = self._get_module_llm_instance(service_name, service_config)
          module_instance = module_class(service_config, module_llm_instance)

          self.services[service_name] = {
            "obj": module_instance,
            "description": module_info['description'],
            "systemContext": getattr(module_instance, 'systemContext', ''),
            "tools": getattr(module_instance, 'tools', []),
            "complexity": getattr(module_instance, 'complexity', 0),
            "functions": getattr(module_instance, 'functions', {}),
            "type": module_info['type'],
            "llm_instance": module_llm_instance  # Store the LLM instance used for this module
          }
          # Update functions with module metadata
          for func_name, func_data in module_instance.functions.items():
            self.functions[func_name] = {
              **func_data,
              "module_name": service_name
            }
          self.module_status[service_name] = 'loaded'
          (tomlogger.logger.module_load if tomlogger.logger else lambda *args, **kwargs: None)(service_name, self.user_config['username'], success=True)
        else:
          self.module_status[service_name] = 'error'
          (tomlogger.logger.module_load if tomlogger.logger else lambda *args, **kwargs: None)(service_name, self.user_config['username'], success=False)
          tomlogger.error(f"Class {module_class_name} not found", self.user_config['username'])

      except Exception as e:
        self.module_status[service_name] = 'error'
        (tomlogger.logger.module_load if tomlogger.logger else lambda *args, **kwargs: None)(service_name, self.user_config['username'], success=False)
        tomlogger.error(f"Error loading module {service_name}: {e}", self.user_config['username'])

  def _load_single_module(self, service_name):
    """Load a single module"""
    try:
      if service_name not in self.module_list:
        self.module_status[service_name] = 'error'
        tomlogger.error(f"Module {service_name} not found in available modules", self.user_config['username'])
        return False
      
      # Get configuration based on module type
      service_config, is_enabled = self._get_module_config(service_name)
      
      if service_config is None:
        self.module_status[service_name] = 'error'
        tomlogger.error(f"Module {service_name} not configured for this user/globally", self.user_config['username'])
        return False
      
      if not is_enabled:
        self.module_status[service_name] = 'disabled'
        return False
      
      self.module_status[service_name] = 'loading'
      
      module_info = self.module_list[service_name]
      module_class_name = module_info['class']
      
      # Find the class in the loaded modules
      module_class = None
      for mod_name, mod_info in self.module_list.items():
          if mod_info['class'] == module_class_name:
              # The class should be in globals now
              if module_class_name in globals():
                  module_class = globals()[module_class_name]
                  break
      
      if module_class:
        # Check if module specifies a custom LLM
        module_llm_instance = self._get_module_llm_instance(service_name, service_config)
        module_instance = module_class(service_config, module_llm_instance)

        self.services[service_name] = {
          "obj": module_instance,
          "description": module_info['description'],
          "systemContext": getattr(module_instance, 'systemContext', ''),
          "tools": getattr(module_instance, 'tools', []),
          "complexity": getattr(module_instance, 'complexity', 0),
          "functions": getattr(module_instance, 'functions', {}),
          "type": module_info['type'],
          "llm_instance": module_llm_instance  # Store the LLM instance used for this module
        }
        # Update functions with module metadata
        for func_name, func_data in module_instance.functions.items():
          self.functions[func_name] = {
            **func_data,
            "module_name": service_name
          }
        self.module_status[service_name] = 'loaded'
        (tomlogger.logger.module_load if tomlogger.logger else lambda *args, **kwargs: None)(service_name, self.user_config['username'], success=True)
        return True
      else:
        self.module_status[service_name] = 'error'
        (tomlogger.logger.module_load if tomlogger.logger else lambda *args, **kwargs: None)(service_name, self.user_config['username'], success=False)
        tomlogger.error(f"Class {module_class_name} not found", self.user_config['username'])
        return False

    except Exception as e:
      self.module_status[service_name] = 'error'
      (tomlogger.logger.module_load if tomlogger.logger else lambda *args, **kwargs: None)(service_name, self.user_config['username'], success=False)
      tomlogger.error(f"Error loading module {service_name}: {e}", self.user_config['username'])
      return False

  def _unload_single_module(self, service_name):
    """Unload a single module"""
    try:
      if service_name in self.services:
        # Remove module functions from global functions
        module_functions = self.services[service_name].get('functions', {})
        for func_name in module_functions:
          if func_name in self.functions:
            del self.functions[func_name]
        
        # Remove service
        del self.services[service_name]
        
        self.module_status[service_name] = 'disabled'
        tomlogger.info(f"○ Module {service_name} unloaded", self.user_config['username'])
        return True
      else:
        self.module_status[service_name] = 'disabled'
        return True
    except Exception as e:
      tomlogger.error(f"Error unloading module {service_name}: {e}", self.user_config['username'])
      return False

  def update_modules_config(self, new_user_config, new_global_config=None):
    """Reload user configuration and update modules accordingly"""
    # Get all modules that could be affected
    old_personal_services = set(self.user_config.get('services', {}).keys()) if 'services' in self.user_config else set()
    new_personal_services = set(new_user_config.get('services', {}).keys()) if 'services' in new_user_config else set()
    
    # Update global config if provided
    if new_global_config:
      self.global_config = new_global_config
    
    # Get old and new enabled status for all modules (personal and global)
    old_enabled = {}
    new_enabled = {}
    
    # Get old configuration status
    for service_name in self.module_list.keys():
      service_config, is_enabled = self._get_module_config(service_name)
      old_enabled[service_name] = is_enabled if service_config is not None else False
    
    # Update user config
    old_user_config = self.user_config
    self.user_config = new_user_config
    
    # Get new configuration status
    for service_name in self.module_list.keys():
      service_config, is_enabled = self._get_module_config(service_name)
      new_enabled[service_name] = is_enabled if service_config is not None else False
    
    # Process changes for all available modules
    all_services = set(old_enabled.keys()) | set(new_enabled.keys())
    for service_name in all_services:
      old_enable = old_enabled.get(service_name, False)
      new_enable = new_enabled.get(service_name, False)
      
      if old_enable != new_enable:
        if new_enable:
          self._load_single_module(service_name)
        else:
          self._unload_single_module(service_name)
      elif service_name in new_personal_services and service_name not in old_personal_services:
        # New module added
        if new_enable:
          self._load_single_module(service_name)
      elif service_name in old_personal_services and service_name not in new_personal_services:
        # Module removed
        self._unload_single_module(service_name)
    
    # Synchronize functions to the main user instance after config update
    self._sync_functions_to_user_instance()
    
    tomlogger.info(f"Configuration updated for user {self.user_config['username']}", self.user_config['username'])

  def get_module_status(self):
    """Return the current status of all modules for this user"""
    return self.module_status.copy()
  
  def list_modules_status(self, username=None):
    """List modules status with permission-based access control"""
    current_user = self.user_config['username']
    is_admin = self.user_config.get('admin', False)
    
    # Convert username to lowercase if provided
    if username:
      username = username.lower()
    
    # Non-admin users can only see their own modules
    if not is_admin and username and username != current_user:
      return {
        "error": "Access denied. You can only view your own module status.",
        "current_user": current_user
      }
    
    # If no username specified
    if not username:
      # Both admin and regular user without username: show their own modules
      return self._get_user_module_status(self)
    
    # Username specified
    if username == current_user:
      # User requesting their own modules
      return self._get_user_module_status(self)
    
    # Admin requesting another user's modules
    if is_admin:
      if not self.module_managers:
        return {
          "error": "Module managers not available. Cannot retrieve other users' status."
        }
      
      if username in self.module_managers:
        module_manager = self.module_managers[username]
        return {username: self._get_user_module_status(module_manager)}
      else:
        return {
          "error": f"User '{username}' not found."
        }
    
    # This should never be reached due to the first check, but just in case
    return {
      "error": "Access denied."
    }

  
  def _get_user_module_status(self, module_manager):
    """Helper function to get module status for a specific module manager"""
    status_info = {
      "loaded_modules": [],
      "disabled_modules": [],
      "error_modules": [],
      "available_modules": list(module_manager.module_list.keys())
    }
    
    # Get current status of configured modules
    for module_name, status in module_manager.module_status.items():
      module_info = {
        "name": module_name,
        "description": module_manager.module_list.get(module_name, {}).get("description", "No description available"),
        "type": module_manager.module_list.get(module_name, {}).get("type", "unknown")
      }
      
      if status == "loaded":
        status_info["loaded_modules"].append(module_info)
      elif status == "disabled":
        status_info["disabled_modules"].append(module_info)
      elif status == "error":
        status_info["error_modules"].append(module_info)
    
    # Add summary
    status_info["summary"] = {
      "total_available": len(module_manager.module_list),
      "total_loaded": len(status_info["loaded_modules"]),
      "total_disabled": len(status_info["disabled_modules"]),
      "total_errors": len(status_info["error_modules"])
    }
    
    return status_info

  def toggle_module_status(self, username, module_name, enable):
    """Enable or disable a module for a specific user (admin only)"""
    # Check if current user is admin
    if not self.user_config.get('admin', False):
      return {
        "error": "Access denied. Administrator privileges required to modify module status."
      }
    
    # Convert username to lowercase for consistency
    username = username.lower()
    
    # Check if module exists in available modules
    if module_name not in self.module_list:
      return {
        "error": f"Module '{module_name}' not found in available modules.",
        "available_modules": list(self.module_list.keys())
      }
    
    try:
      # Read the config file
      config_path = self.global_config.get('config_path', '/data/config.yml')
      with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
      
      # Find the user in the config
      user_found = False
      for user in config.get('users', []):
        if user.get('username', '').lower() == username:
          user_found = True
          
          # Initialize services if not present
          if 'services' not in user:
            user['services'] = {}
          
          # Initialize module config if not present
          if module_name not in user['services']:
            user['services'][module_name] = {}
          
          # Set the enable status
          if isinstance(user['services'][module_name], dict):
            user['services'][module_name]['enable'] = enable
          else:
            # If it's not a dict, convert it to dict with enable
            user['services'][module_name] = {'enable': enable}
          
          break
      
      if not user_found:
        return {
          "error": f"User '{username}' not found in configuration."
        }
      
      # Write the updated config back to file
      with open(config_path, 'w') as file:
        yaml.safe_dump(config, file, default_flow_style=False, indent=2)
      
      action = "enabled" if enable else "disabled"
      return {
        "success": True,
        "message": f"Module '{module_name}' has been {action} for user '{username}'.",
        "username": username,
        "module_name": module_name,
        "enable": enable
      }
      
    except FileNotFoundError:
      return {
        "error": f"Configuration file not found at {config_path}."
      }
    except yaml.YAMLError as e:
      return {
        "error": f"Error parsing YAML configuration: {str(e)}"
      }
    except Exception as e:
      return {
        "error": f"Error modifying module status: {str(e)}"
      }

  def restart_module(self, module_name):
    """Restart a module that is in error state. Users can only restart their own modules."""
    current_user = self.user_config['username']
    
    # Check if the module exists in available modules
    if module_name not in self.module_list:
      return {
        "error": f"Module '{module_name}' not found in available modules.",
        "available_modules": list(self.module_list.keys())
      }
    
    # Check if the module is configured (either globally or for this user)
    service_config, is_enabled = self._get_module_config(module_name)
    if service_config is None:
      return {
        "error": f"Module '{module_name}' is not configured for user '{current_user}' or globally."
      }
    
    # Check if the module is in error state
    current_status = self.module_status.get(module_name, None)
    if current_status != 'error':
      return {
        "error": f"Module '{module_name}' is not in error state. Current status: {current_status}. Only modules in error state can be restarted."
      }
    
    try:
      # First unload the module if it's loaded
      self._unload_single_module(module_name)
      
      # Then try to load it again
      success = self._load_single_module(module_name)
      
      if success:
        return {
          "success": True,
          "message": f"Module '{module_name}' has been successfully restarted for user '{current_user}'.",
          "module_name": module_name,
          "new_status": self.module_status.get(module_name, 'unknown')
        }
      else:
        return {
          "error": f"Failed to restart module '{module_name}'. The module is still in error state.",
          "module_name": module_name,
          "status": self.module_status.get(module_name, 'unknown')
        }
    
    except Exception as e:
      return {
        "error": f"Error restarting module '{module_name}': {str(e)}",
        "module_name": module_name
      }

  def get_module_configuration_parameters(self, module_name):
    """Get the configuration parameters expected by a specific module"""
    # Check if module exists in available modules
    if module_name not in self.module_list:
      tomlogger.debug(f"Module {module_name} not found in module_list. Available: {list(self.module_list.keys())}", self.user_config['username'])
      return {
        "error": f"Module '{module_name}' not found in available modules.",
        "available_modules": list(self.module_list.keys())
      }
    
    try:
      # Load the module to access its tom_config
      modules_dir = '/data/modules'
      # Use the actual filename from module_list
      filename = self.module_list[module_name].get('filename', f"{module_name}.py")
      file_path = os.path.join(modules_dir, filename)
      
      if not os.path.exists(file_path):
        return {
          "error": f"Module file not found: {file_path}"
        }
      
      # Load the module
      spec = importlib.util.spec_from_file_location(module_name, file_path)
      if not spec or not spec.loader:
        return {
          "error": f"Failed to load module specification for '{module_name}'"
        }
      
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      
      # Get tom_config
      if not hasattr(module, 'tom_config'):
        return {
          "error": f"Module '{module_name}' does not have a tom_config definition"
        }
      
      tom_config = getattr(module, 'tom_config')
      
      # Extract configuration parameters
      config_params = tom_config.get('configuration_parameters', {})
      
      result = {
        "module_name": module_name,
        "description": tom_config.get('description', 'No description available'),
        "type": tom_config.get('type', 'global'),
        "configuration_parameters": config_params
      }
      
      # Add summary information
      if config_params:
        required_params = []
        optional_params = []
        
        for param_name, param_info in config_params.items():
          if param_info.get('required', False):
            required_params.append(param_name)
          else:
            optional_params.append(param_name)
        
        result["summary"] = {
          "total_parameters": len(config_params),
          "required_parameters": required_params,
          "optional_parameters": optional_params
        }
      else:
        result["summary"] = {
          "total_parameters": 0,
          "required_parameters": [],
          "optional_parameters": []
        }
        result["message"] = "This module does not define any configuration parameters."
      
      return result
      
    except Exception as e:
      return {
        "error": f"Error loading module configuration for '{module_name}': {str(e)}"
      }

  @staticmethod
  def print_modules_status_summary(user_modules_dict):
    """Print a summary of module loading status for all users"""
    tomlogger.info("📊 Module loading status summary:")
    
    for username, module_manager in user_modules_dict.items():
      status_counts = {'loaded': 0, 'disabled': 0, 'error': 0}
      
      for module_name, status in module_manager.get_module_status().items():
        status_counts[status] = status_counts.get(status, 0) + 1
      
      total_modules = sum(status_counts.values())
      if total_modules > 0:
        tomlogger.info(f"👤 {username}: {status_counts['loaded']} loaded, {status_counts['disabled']} disabled, {status_counts['error']} errors", username)


