import os
import importlib.util
import inspect

class TomCoreModules:
  def __init__(self, global_config, user_config, llm_instance):
    self.global_config = global_config
    self.user_config = user_config
    self.llm_instance = llm_instance
    self.services = {}
    self.functions = {}
    self.module_list = {}
    self.module_status = {}  # Track module loading status
    self._load_module_list()
    self._load_user_modules()

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

  def get_module_status(self):
    """Return the current status of all modules for this user"""
    return self.module_status.copy()

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
