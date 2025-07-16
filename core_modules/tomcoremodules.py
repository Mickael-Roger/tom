import os
import importlib.util
import inspect
import functools
import yaml

class TomCoreModules:
  def __init__(self, global_config, user_config, llm_instance, module_managers=None):
    self.global_config = global_config
    self.user_config = user_config
    self.llm_instance = llm_instance
    self.module_managers = module_managers  # Reference to all user module managers
    self.services = {}
    self.functions = {}
    self.module_list = {}
    self.module_status = {}  # Track module loading status
    self._load_module_list()
    self._load_user_modules()
    
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
                "description": "Optional: specific username to get status for"
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
      }
    ]
    
    self.systemContext = "This module manages the loading and status of extension modules. It can provide information about which modules are currently loaded, disabled, or have errors."
    self.complexity = 0
    self.functions = {
      "list_modules_status": {
        "function": functools.partial(self.list_modules_status)
      },
      "toggle_module_status": {
        "function": functools.partial(self.toggle_module_status)
      }
    }

  def _load_module_list(self):
    mod_dir = './modules'
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
                "type": tom_mod_config.get('type', 'global')
              }

  def _load_user_modules(self):
    if 'services' in self.user_config:
      for service_name in self.user_config['services'].keys():
        try:
          # Check if module is enabled (default is True if not specified)
          service_config = self.user_config['services'][service_name]
          is_enabled = service_config.get('enable', True) if isinstance(service_config, dict) else True
          
          if not is_enabled:
            self.module_status[service_name] = 'disabled'
            continue
          
          if service_name not in self.module_list:
            self.module_status[service_name] = 'error'
            continue
          
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
            module_instance = module_class(self.user_config['services'][service_name], self.llm_instance)

            self.services[service_name] = {
              "obj": module_instance,
              "description": module_info['description'],
              "systemContext": getattr(module_instance, 'systemContext', ''),
              "tools": getattr(module_instance, 'tools', []),
              "complexity": getattr(module_instance, 'complexity', 0),
              "functions": getattr(module_instance, 'functions', {}),
              "type": module_info['type']
            }
            self.functions.update(module_instance.functions)
            self.module_status[service_name] = 'loaded'
          else:
            self.module_status[service_name] = 'error'
            print(f"Error loading module {service_name} for user {self.user_config['username']}: Class {module_class_name} not found.")

        except Exception as e:
          self.module_status[service_name] = 'error'
          print(f"Error loading module {service_name} for user {self.user_config['username']}: {e}")

  def _load_single_module(self, service_name):
    """Load a single module"""
    try:
      if service_name not in self.module_list:
        self.module_status[service_name] = 'error'
        print(f"Module {service_name} not found in available modules")
        return False
      
      service_config = self.user_config['services'][service_name]
      is_enabled = service_config.get('enable', True) if isinstance(service_config, dict) else True
      
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
        module_instance = module_class(self.user_config['services'][service_name], self.llm_instance)

        self.services[service_name] = {
          "obj": module_instance,
          "description": module_info['description'],
          "systemContext": getattr(module_instance, 'systemContext', ''),
          "tools": getattr(module_instance, 'tools', []),
          "complexity": getattr(module_instance, 'complexity', 0),
          "functions": getattr(module_instance, 'functions', {}),
          "type": module_info['type']
        }
        self.functions.update(module_instance.functions)
        self.module_status[service_name] = 'loaded'
        print(f"✓ Module {service_name} loaded for user {self.user_config['username']}")
        return True
      else:
        self.module_status[service_name] = 'error'
        print(f"✗ Error loading module {service_name} for user {self.user_config['username']}: Class {module_class_name} not found.")
        return False

    except Exception as e:
      self.module_status[service_name] = 'error'
      print(f"✗ Error loading module {service_name} for user {self.user_config['username']}: {e}")
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
        print(f"○ Module {service_name} unloaded for user {self.user_config['username']}")
        return True
      else:
        self.module_status[service_name] = 'disabled'
        return True
    except Exception as e:
      print(f"✗ Error unloading module {service_name} for user {self.user_config['username']}: {e}")
      return False

  def update_modules_config(self, new_user_config):
    """Reload user configuration and update modules accordingly"""
    old_services = set(self.user_config.get('services', {}).keys()) if 'services' in self.user_config else set()
    new_services = set(new_user_config.get('services', {}).keys()) if 'services' in new_user_config else set()
    
    # Get old and new enabled status
    old_enabled = {}
    new_enabled = {}
    
    if 'services' in self.user_config:
      for service_name, service_config in self.user_config['services'].items():
        old_enabled[service_name] = service_config.get('enable', True) if isinstance(service_config, dict) else True
    
    if 'services' in new_user_config:
      for service_name, service_config in new_user_config['services'].items():
        new_enabled[service_name] = service_config.get('enable', True) if isinstance(service_config, dict) else True
    
    self.user_config = new_user_config
    
    # Process changes
    for service_name in old_services | new_services:
      old_enable = old_enabled.get(service_name, False)
      new_enable = new_enabled.get(service_name, False)
      
      if old_enable != new_enable:
        if new_enable:
          self._load_single_module(service_name)
        else:
          self._unload_single_module(service_name)
      elif service_name in new_services and service_name not in old_services:
        # New module added
        if new_enable:
          self._load_single_module(service_name)
      elif service_name in old_services and service_name not in new_services:
        # Module removed
        self._unload_single_module(service_name)
    
    print(f"Configuration updated for user {self.user_config['username']}")

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
      config_path = '/data/config.yml'
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

  @staticmethod
  def print_modules_status_summary(user_modules_dict):
    """Print a summary of module loading status for all users"""
    print("\n" + "="*60)
    print("MODULE LOADING STATUS SUMMARY")
    print("="*60)
    
    for username, module_manager in user_modules_dict.items():
      print(f"\nUser: {username}")
      print("-" * 40)
      
      status_counts = {'loaded': 0, 'disabled': 0, 'error': 0}
      
      for module_name, status in module_manager.get_module_status().items():
        status_symbol = {
          'loaded': '✓',
          'disabled': '○',
          'error': '✗'
        }.get(status, '?')
        
        print(f"  {status_symbol} {module_name:<20} {status}")
        status_counts[status] = status_counts.get(status, 0) + 1
      
      total_modules = sum(status_counts.values())
      if total_modules > 0:
        print(f"\nSummary: {status_counts['loaded']} loaded, {status_counts['disabled']} disabled, {status_counts['error']} errors")
    
    print("\n" + "="*60)


