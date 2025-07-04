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
                "description": tom_mod_config['description']
              }

  def _load_user_modules(self):
    if 'services' in self.user_config:
      for service_name in self.user_config['services'].keys():
        try:
          if service_name in self.module_list:
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
              }
              self.functions.update(module_instance.functions)
            else:
              print(f"Error loading module {service_name} for user {self.user_config['username']}: Class {module_class_name} not found.")

        except Exception as e:
          print(f"Error loading module {service_name} for user {self.user_config['username']}: {e}")
