import json
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder
from datetime import datetime
import copy

# LitLLM
from litellm import completion
import os

# Logging
from tomlogger import logger




class TomLLM():

  def __init__(self, user_config, global_config) -> None:

    self.llms = {}

    if 'openai' in global_config['global'].keys():
      os.environ["OPENAI_API_KEY"] = global_config['global']["openai"]["api"]
      self.llms['openai'] = ["openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4o"]

    if 'mistral' in global_config['global'].keys():
      os.environ["MISTRAL_API_KEY"] = global_config['global']["mistral"]["api"]
      self.llms['mistral'] = [ "mistral/mistral-large-latest", "mistral/mistral-large-latest", "mistral/mistral-large-latest"]

    if 'deepseek' in global_config['global'].keys():
      os.environ["DEEPSEEK_API_KEY"] = global_config['global']["deepseek"]["api"]
      self.llms['deepseek'] = ["deepseek/deepseek-chat", "deepseek/deepseek-chat", "deepseek/deepseek-reasoner"]

    if 'xai' in global_config['global'].keys():
      os.environ["XAI_API_KEY"] = global_config['global']["xai"]["api"]
      self.llms['xai'] = ["xai/grok-beta", "xai/grok-beta", "xai/grok-beta"]

    if 'gemini' in global_config['global'].keys():
      os.environ["GEMINI_API_KEY"] = global_config['global']["gemini"]["api"]
      self.llms['gemini'] = ["gemini/gemini-1.5-flash", "gemini/gemini-1.5-flash", "gemini/gemini-1.5-flash"]


    if global_config['global']['llm'] not in ["mistral", "openai", "deepseek", "xai", "gemini"]:
      logger.critical(f"LLM {global_config['global']['llm']} not supported")
      exit(-1)

    self.llm = global_config['global']['llm']

      #elif global_config['global']['llm'] == "gemini":
      #  Gemini.configure(api_key=global_config['global']["gemini"]["api"])
      #  self.llm = self.callGemini
      #  self.llm_models = ["gemini-1.5-flash", "gemini-1.5-flash", "gemini-1.5-flash"]

    self.history = []

    self.username = user_config['username']

    self.services = {}
    self.functions = {}
    self.modules = []

    self.user_context = user_config['personalContext']


    self.tts = None

    #self.tom_context = f'''Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'.\n\nImportant: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'\nYour responses will be transcribed into audio, so by default, and unless otherwise specified, you must reply with audible sentences, without indents, dashes, lists, or any markdown or other formatting. Additionally, you should respond as concisely as possible whenever possible.\n{self.user_context} '''

    self.tom_context = f'''Your name is Tom, and you are my personal assistant. You have access to numerous external functionalities via function calls. Since you have access to more functions than your memory can hold, they are grouped into modules. A module is a logical grouping of functions within a specific scope. One of your primary tasks will be "triage," which involves identifying the modules to load to fulfill the user's request.

    When the user provides you with information, if you think it should be stored in memory, suggest doing so.

    It is important to be precise and not make assumptions. If the request is unclear, ask for clarification.

    When your response includes a temporal reference, it must be in the format 'Weekday day month'. Numbers must be written with digits and not in words. It is import you write numbers using digits and not in words. For example, you must answer '123' and not 'one two three' nor 'one hundred and three'.

    As a LLM, you have a lot of information and knowledge. However, you do not natively possess personal information or details about the user who is asking you questions. This is why you have a module called 'memory' that contains personal information about the user. Therefore, if you need to tell the user that you do not know or do not have the information to answer their request, you should first load the 'memory' module and list its contents. Only if your intrinsic knowledge and the contents of the 'memory' module do not provide you with the information needed to answer the user's request, can you say that you do not know or that you do not have the necessary information to respond.

    {self.user_context}
    '''



  def reset(self):
    logger.info(f"History cleaning", self.username)
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

    #svc_context = ""
    #for service in self.services:
    #  if self.services[service]['service_context'] != "":
    #    svc_context = f"{svc_context}\n{self.services[service]['service_context']}\n"

    behaviors = self.services['behavior']['obj'].behavior_get()

    #morning_routines = self.services['morningroutine']['obj'].morning_routine_prompt()
    
    

    if self.history: 
      self.history[0] = todayMsg
    else:
      self.history.append(todayMsg)
      self.history.append({"role": "system", "content": self.tom_context})
      #self.history.append({"role": "system", "content": f"{svc_context}"})

      if behaviors:
        self.history.append({"role": "system", "content": f"\n{behaviors}"})

    #behaviors = self.services['behavior']['obj'].behavior_get()
    #if len(behaviors) > 1:
    #  self.history.append({"role": "system", "content": behaviors})
  
    self.history.append({"role": "user", "content": input})



  def callLLM(self, messages, tools=None, complexity=0, llm=None):

    if llm == None:
      llm=self.llm

    model=self.llms[self.llm][complexity]

    logger.debug("Messages to send:", self.username)
    logger.debug(str(messages), self.username)
    logger.debug("Tools available:", self.username)
    logger.debug(str(tools), self.username)

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

    logger.debug("LLM Response:", self.username)
    logger.debug(str(response), self.username)


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

  def processRequest(self, input, lang, position, client_type):
  
    self.generateContextPrompt(input, lang, position, client_type)


    available_tools = []
    modules_name_list = []


    for module in self.services:
      available_tools.append({"module_name": module, "module_description": self.services[module]['description']})
      modules_name_list.append(module)


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
                #                "type": "array",
                #                "items": {
                  "type": "string",
                  "enum": modules_name_list,
                #                },
                "description": f"List of module names",
              },
            },
            "required": ["modules_name"],
            "additionalProperties": False,
          },
        },
      },
    ]

    conversation = copy.deepcopy(self.history) 
  
    tooling = json.dumps(available_tools)
    #    conversation.append({"role": "system", "content": f"Here is a list of available modules. Your role is to identify the necessary module(s) to meet the user's request. To do so, you must call the function 'modules_needed_to_answer_user_prompt' with the list of required modules as a parameter. If you are able to answer the user request without any modules, do it and do not call 'modules_needed_to_answer_user_prompt' function.\n\n{tooling}"})
    #conversation.append({"role": "system", "content": f"Here is a list of modules. For each module, you have the its description. Your role is to call the function 'modules_needed_to_answer_user_prompt' with the module needed to provide me the answer to my request. 'module_name' is not a name of a function, it's a possible value of the parameter of the 'modules_needed_to_answer_prompt'. You must never use the field 'module_name' as a function name.\n{tooling}"})
    prompt = f'''As an AI assistant, you have access to a wide range of functions, far more than your API allows. These functions are grouped into modules. A module is a logical grouping of functions for a specific theme.

    For each new user request, you have access to the conversation history.

    If you need a function that is not in your list of tools to respond to the user's request, you should call the 'modules_needed_to_answer_user_prompt' function with the necessary modules. You can call the 'modules_needed_to_answer_user_prompt' function as many times as needed.

    It is very important that you do not invent module names—only the modules provided in the list exist.

    Once you call the 'modules_needed_to_answer_user_prompt' function, the user's request will be sent back to you with the functions from the requested modules added to your tools. At that point, you can choose the appropriate function(s) to respond to the user's request.
    
    ```json
    {tooling}
    ```
    '''
    conversation.append({"role": "system", "content": prompt})

    # Alternative to test: As a language model, you cannot respond to all of my requests. Therefore, you might need additional information. Certain information or functionalities can be found in modules. You can load these modules to assist you in responding by using the load_module function. Below, you will find a complete list of modules along with their descriptions.

    complexity = 1

    llm = "openai"
    #llm = self.llm

    response_context = self.set_response_context(client_type)
    conversation.append({"role": 'system', "content": response_context})
    self.history.append({"role": 'system', "content": response_context})

    while True:


      response = self.callLLM(messages=conversation, tools=tools, complexity=complexity, llm=llm)

      conversation = copy.deepcopy(self.history)
  
      if response != False:
        if response.choices[0].finish_reason == "stop":
          self.history.append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})
          return response.choices[0].message.content
  
        elif response.choices[0].finish_reason == "tool_calls":

          load_modules= []
          # Are we in triage?
          for tool_call in response.choices[0].message.tool_calls:
            if tool_call.function.name.find("modules_needed_to_answer_user_prompt") != -1:    # Probably bad prompt, but sometimes it calls 'module_name.modules_needed_to_answer_user_prompt'
              mod = json.loads(tool_call.function.arguments)
              mod_name=mod['modules_name']
              #for mod in mods['modules_name']:
              load_modules.append(mod_name)
            # Todo add something to check if the function name is a module, if so, it's an LLM error and we must use it as if it was a parameter
            if tool_call.function.name in modules_name_list:
              mod_name=tool_call.function.name
              load_modules.append(mod_name)
            


          # Yes we are
          if load_modules:
            logger.debug("Load modules: " + str(load_modules), self.username)
  
            tools = []
            complexity = 0

            #if 'memory' not in load_modules:
            #  load_modules.append('memory')


            for mod in set(load_modules):
              if mod in self.services:
                tools = tools + self.services[mod]['tools']

                conversation.append({"role": "system", "content": self.services[mod]["systemContext"]})

                try:
                  if self.services[mod]["complexity"] > complexity:
                    complexity = self.services[mod]["complexity"]
                    logger.debug(f"Complexity increased to {complexity}", self.username)
                except:
                  pass
              else:
                logger.warning(f"Module '{mod}' not loaded in services, skipping", self.username)


            llm = None

  
          # We are not
          else:

            llm = None
            
            #self.history.append(response.choices[0].message.to_dict())
            conversation.append(response.choices[0].message.to_dict())

            for tool_call in response.choices[0].message.tool_calls:
    
              function_name = tool_call.function.name
              function_params = json.loads(tool_call.function.arguments)
    
              logger.info(f"Calling function: {function_name} with {function_params}", self.username)
    
              if function_name in self.functions:
                function_result = self.functions[function_name]['function'](**function_params)
              else:
                logger.error(f"Function '{function_name}' not found in available functions", self.username)
                logger.error(f"Available functions: {list(self.functions.keys())}", self.username)
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
