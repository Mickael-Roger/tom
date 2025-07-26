import json
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder
from datetime import datetime
import copy

# LitLLM
from litellm import completion
import os

# Logging
import tomlogger
from tomlogger import set_log_context




class TomLLM():

  def __init__(self, user_config, global_config) -> None:

    self.llms = {}

    # Load LLM configuration from global.llms structure
    llms_config = global_config['global'].get('llms', {})

    # Configure each LLM provider from configuration
    for llm_name, llm_config in llms_config.items():
      if not isinstance(llm_config, dict):
        tomlogger.warning(f"Invalid configuration for LLM '{llm_name}', skipping")
        continue
        
      api_key = llm_config.get("api")
      if not api_key:
        tomlogger.warning(f"No API key found for LLM '{llm_name}', skipping")
        continue
        
      # Get models configuration (required)
      models = llm_config.get("models")
      if not models or len(models) != 3:
        tomlogger.warning(f"LLM '{llm_name}' must have exactly 3 models for complexity levels 0, 1, 2. Skipping.")
        continue
        
      # Get environment variable name (required)
      env_var = llm_config.get("env_var")
      if not env_var:
        tomlogger.warning(f"No env_var specified for LLM '{llm_name}', skipping")
        continue
      
      # Configure the LLM
      os.environ[env_var] = api_key
      self.llms[llm_name] = models

    # Check that the configured LLM was actually loaded
    configured_llm = global_config['global']['llm']
    if configured_llm not in self.llms:
      tomlogger.critical(f"LLM '{configured_llm}' is not configured or failed to load. Available LLMs: {list(self.llms.keys())}")
      exit(-1)

    self.llm = global_config['global']['llm']

    self.history = []

    self.username = user_config['username']

    self.services = {}
    self.functions = {}
    self.modules = []

    self.user_context = user_config['personalContext']

    self.tts = None

    self.tom_context = f'''Your name is Tom, and you are my personal assistant. You have access to numerous external functionalities via function calls. Since you have access to more functions than your memory can hold, they are grouped into modules. A module is a logical grouping of functions within a specific scope. One of your primary tasks will be "triage," which involves identifying the modules to load to fulfill the user's request.

    When the user provides you with information, if you think it should be stored in memory, suggest doing so.

    It is important to be precise and not make assumptions. If the request is unclear, ask for clarification.

    When your response includes a temporal reference, it must be in the format 'Weekday day month'. Numbers must be written with digits and not in words. It is import you write numbers using digits and not in words. For example, you must answer '123' and not 'one two three' nor 'one hundred and three'.

    As a LLM, you have a lot of information and knowledge. However, you do not natively possess personal information or details about the user who is asking you questions. This is why you have a module called 'memory' that contains personal information about the user. Therefore, if you need to tell the user that you do not know or do not have the information to answer their request, you should first load the 'memory' module and list its contents. Only if your intrinsic knowledge and the contents of the 'memory' module do not provide you with the information needed to answer the user's request, can you say that you do not know or that you do not have the necessary information to respond.

    {self.user_context}
    '''



  def reset(self):
    tomlogger.info(f"History cleaning", self.username)
    
    # Analyze session for memory before clearing history
    if self.history and 'memory' in self.services:
      try:
        memory_service = self.services['memory']['obj']
        if hasattr(memory_service, 'analyze_session_async'):
          # Update the LLM reference to ensure it points to this instance
          memory_service.llm = self
          memory_service.analyze_session_async(self.history)
      except Exception as e:
        tomlogger.error(f"Error during session memory analysis: {str(e)}", self.username)
    
    self.history = []
    return True



  def generateContextPrompt(self, input, lang, position, client_type):
  
    gps = "" 

    current_timezone = ZoneInfo("Europe/Paris")
    if position is not None:
      tf = TimezoneFinder()
      current_timezone = ZoneInfo(tf.timezone_at(lat=position['latitude'], lng=position['longitude']))
      gps = f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}."
  
  
    today= datetime.now(current_timezone).strftime("%A %d %B %Y %H:%M:%S")
    weeknumber = datetime.now().isocalendar().week
    todayMsg = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}. {gps}\n\n"}

    behaviors = self.services['behavior']['obj'].behavior_get()
  
    if self.history: 
      self.history[0] = todayMsg
    else:
      self.history.append(todayMsg)
      self.history.append({"role": "system", "content": self.tom_context})

      if behaviors:
        self.history.append({"role": "system", "content": f"\n{behaviors}"})
  
    self.history.append({"role": "user", "content": input})



  def callLLM(self, messages, tools=None, complexity=0, llm=None):

    if llm == None:
      llm=self.llm

    model=self.llms[self.llm][complexity]

    tomlogger.debug(f"Messages to send: {str(messages)} | Tools available: {str(tools)}", self.username)

    if llm == "deepseek":
      if tools: 
        for tool in tools:
          if "parameters" in tool["function"]:
            if not tool["function"]["parameters"]:
              del tool["function"]["parameters"]

    if tools: 
      response = completion(
        model = model,
        temperature = 0,
        messages = messages,
        tools = tools,
        tool_choice = "auto",
      )
    else:
      response = completion(
        model = model,
        messages = messages,
      )

    tomlogger.debug(f"LLM Response: {str(response)}", self.username)


    if not response:
      return False

    if not response.choices:
      return False

    if response.choices[0].finish_reason not in ["tool_calls", "stop"]:
      return False

    return response




  def set_response_context(self, client_type):
    if client_type == 'tui':
      return "Your response will be displayed in a TUI terminal application. You should use markdown to format your answer for better readability. You can use titles, lists, bold text, etc."
    else: # web and pwa
      return "Your response will be displayed in a web browser or in an mobile app, so it must be concise and free of any markdown formatting, lists, or complex layouts. Use simple text and line breaks for readability. Do not forget in most case, your response will be play using a text to speech feature. Unless the user explicitly ask for it, you must never directly write URL or stuff like that. Instead, you must use the tag [open:PLACE URL HERE]"




  def triageModules(self, conversation, available_tools, modules_name_list, client_type):
    tools = [
      {
        "type": "function",
        "function": {
          "name": "modules_needed_to_answer_user_prompt",
          "description": "This function is used to execute the appropriate module to get the required data to answer the user's request",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "modules_name": {
                "type": "string",
                "enum": modules_name_list,
                "description": f"List of module names",
              },
            },
            "required": ["modules_name"],
            "additionalProperties": False,
          },
        },
      },
    ]

    triage_conversation = copy.deepcopy(conversation) 
  
    tooling = json.dumps(available_tools)
    prompt = f'''As an AI assistant, you have access to a wide range of functions, far more than your API allows. These functions are grouped into modules. A module is a logical grouping of functions for a specific theme.

    For each new user request, you have access to the conversation history.

    If you need a function that is not in your list of tools to respond to the user's request, you should call the 'modules_needed_to_answer_user_prompt' function with the necessary modules. You can call the 'modules_needed_to_answer_user_prompt' function as many times as needed.

    It is very important that you do not invent module names—only the modules provided in the list exist.

    Once you call the 'modules_needed_to_answer_user_prompt' function, the user's request will be sent back to you with the functions from the requested modules added to your tools. At that point, you can choose the appropriate function(s) to respond to the user's request.
    
    ```json
    {tooling}
    ```
    '''
    triage_conversation.append({"role": "system", "content": prompt})

    complexity = 1
    llm = self.llm

    response_context = self.set_response_context(client_type)
    triage_conversation.append({"role": 'system', "content": response_context})

    response = self.callLLM(messages=triage_conversation, tools=tools, complexity=complexity, llm=llm)
    
    load_modules = []
    if response != False and response.choices[0].finish_reason == "tool_calls":
      for tool_call in response.choices[0].message.tool_calls:
        if tool_call.function.name.find("modules_needed_to_answer_user_prompt") != -1:
          mod = json.loads(tool_call.function.arguments)
          mod_name = mod['modules_name']
          load_modules.append(mod_name)
        if tool_call.function.name in modules_name_list:
          mod_name = tool_call.function.name
          load_modules.append(mod_name)
    
    return load_modules

  def executeRequest(self, conversation, modules, client_type):
    tools = []
    complexity = 0

    for mod in set(modules):
      if mod in self.services:
        tools = tools + self.services[mod]['tools']
        conversation.append({"role": "system", "content": self.services[mod]["systemContext"]})
        try:
          if self.services[mod]["complexity"] > complexity:
            complexity = self.services[mod]["complexity"]
            tomlogger.debug(f"Complexity increased to {complexity}", self.username)
        except KeyError:
          # Module doesn't have complexity setting, use default
          pass
      else:
        tomlogger.warning(f"Module '{mod}' not loaded in services, skipping", self.username)

    while True:
      response = self.callLLM(messages=conversation, tools=tools, complexity=complexity)
      
      if response != False:
        if response.choices[0].finish_reason == "stop":
          self.history.append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})
          return response.choices[0].message.content

        elif response.choices[0].finish_reason == "tool_calls":
          conversation.append(response.choices[0].message.to_dict())

          for tool_call in response.choices[0].message.tool_calls:
            function_name = tool_call.function.name
            function_params = json.loads(tool_call.function.arguments)

            tomlogger.info(f"Calling function: {function_name} with {function_params}", self.username)

            if function_name in self.functions:
              function_data = self.functions[function_name]
              module_name = function_data.get('module_name', 'system')
              set_log_context(module_name=module_name)
              
              try:
                function_result = function_data['function'](**function_params)
              finally:
                set_log_context(module_name=None)
            else:
              tomlogger.error(f"Function '{function_name}' not found in available functions", self.username)
              tomlogger.error(f"Available functions: {list(self.functions.keys())}", self.username)
              function_result = {"error": f"Function '{function_name}' not available. This might be due to a module loading error."}

            if function_result is False:
              self.history.append({"role": 'assistant', "content": "Error while executing the function call"})
              return False

            self.history.append({"role": 'system', "content": json.dumps(function_result)})
            conversation.append({"role": 'tool', "content": json.dumps(function_result), "tool_call_id": tool_call.id})
        else:
          return False
      else: 
        return False

  def processRequest(self, input, lang, position, client_type):
  
    self.generateContextPrompt(input, lang, position, client_type)

    available_tools = []
    modules_name_list = []

    for module in self.services:
      available_tools.append({"module_name": module, "module_description": self.services[module]['description']})
      modules_name_list.append(module)

    conversation = copy.deepcopy(self.history)

    # Phase 1: Triage to identify needed modules
    required_modules = self.triageModules(conversation, available_tools, modules_name_list, client_type)
    
    if required_modules:
      tomlogger.debug(f"Load modules: {str(required_modules)}", self.username)
      # Phase 2: Execute request with identified modules
      return self.executeRequest(conversation, required_modules, client_type)
    else:
      # If no modules identified, try to answer directly
      response_context = self.set_response_context(client_type)
      conversation.append({"role": 'system', "content": response_context})
      
      response = self.callLLM(messages=conversation)
      if response != False and response.choices[0].finish_reason == "stop":
        self.history.append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})
        return response.choices[0].message.content
      
      return False