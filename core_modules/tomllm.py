import json
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder
from datetime import datetime
import copy



# OpenAI
from openai import OpenAI
# Mistral AI
from mistralai import Mistral
# Gemini
import google.generativeai as Gemini




class TomLLM():

  def __init__(self, user_config, global_config) -> None:

    self.llms = {}

    if 'mistral' in global_config['global'].keys():
      self.llms['mistral'] = {}
      self.llms['mistral']['llm_client'] = Mistral(api_key=global_config['global']["mistral"]["api"])
      self.llms['mistral']['func'] = self.callMistral
      self.llms['mistral']['llm_models'] = [ "mistral-large-latest", "mistral-large-latest", "mistral-large-latest"]

    if 'openai' in global_config['global'].keys():
      self.llms['openai'] = {}
      self.llms['openai']['llm_client'] = OpenAI(api_key=global_config['global']["openai"]["api"])
      self.llms['openai']['func'] = self.callOpenai
      self.llms['openai']['llm_models'] = ["gpt-4o-mini", "gpt-4o", "gpt-4o"]

    if 'deepseek' in global_config['global'].keys():
      self.llms['deepseek'] = {}
      self.llms['deepseek']['llm_client'] = OpenAI(api_key=global_config['global']["deepseek"]["api"], base_url="https://api.deepseek.com")
      self.llms['deepseek']['func'] = self.callDeepseek
      self.llms['deepseek']['llm_models'] = ["deepseek-chat", "deepseek-chat", "deepseek-chat"]

    if 'xai' in global_config['global'].keys():
      self.llms['xai'] = {}
      self.llms['xai']['llm_client'] = OpenAI(api_key=global_config['global']["xai"]["api"], base_url="https://api.x.ai/v1")
      self.llms['xai']['func'] = self.callXai
      self.llms['xai']['llm_models'] = ["grok-beta", "grok-beta", "grok-beta"]

    if global_config['global']['llm'] not in ["mistral", "openai", "deepseek", "xai"]:
      print(f"LLM {global_config['global']['llm']} not supported")
      exit(-1)

    self.llm = self.llms[global_config['global']['llm']]

      #elif global_config['global']['llm'] == "gemini":
      #  Gemini.configure(api_key=global_config['global']["gemini"]["api"])
      #  self.llm = self.callGemini
      #  self.llm_models = ["gemini-1.5-flash", "gemini-1.5-flash", "gemini-1.5-flash"]

    self.history = []

    self.username = user_config['username']

    self.services = {}
    self.functions = {}

    self.user_context = user_config['personalContext']


    self.tts = None

    #self.tom_context = f"""Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'.\n\nImportant: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'\nYour responses will be transcribed into audio, so by default, and unless otherwise specified, you must reply with audible sentences, without indents, dashes, lists, or any markdown or other formatting. Additionally, you should respond as concisely as possible whenever possible.\n{self.user_context} """

    self.tom_context = f"""Your name is Tom, and you are my personal assistant. You have access to numerous external functionalities via function calls. Since you have access to more functions than your memory can hold, they are grouped into modules. A module is a logical grouping of functions within a specific scope. One of your primary tasks will be "triage," which involves identifying the modules to load to fulfill the user's request.

    When the user provides you with information, if you think it should be stored in memory, suggest doing so.

    It is important to be precise and not make assumptions. If the request is unclear, ask for clarification.

    Your responses will be read aloud using a text-to-speech function. Unless otherwise specified, you must reply with audible sentences, avoiding indents, dashes, bullet points, or formatting like markdown. Additionally, always aim to be as concise as possible in your responses.

    When your response includes a temporal reference, it must be in the format 'Weekday day month'. Numbers must be written with digits and not in words. It is import you write numbers using digits and not in words. For example, you must answer '123' and not 'one two three' nor 'one hundred and three'.

    It is important that if the user asks you a question, before responding that you don’t know, you must check the information stored in your memory.

    {self.user_context}

    """



  def reset(self):
    print(f"{self.username}: History cleaning")
    self.history = []

    return True



  def callMistral(self, messages, tools=None, complexity=0):

    print("///////////////// Mistral ///////////////////")

    if tools: 
      response = self.llms['mistral']['llm_client'].chat.complete(
        model = self.llms['mistral']['llm_models'][complexity],
        messages = messages,
        tools = tools,
        tool_choice = "auto",
      )
    else:
      response = self.llms['mistral']['llm_client'].chat.complete(
        model = self.llms['mistral']['llm_models'][complexity],
        messages = messages
      )
        
    values = {}

    if response:
      if response.choices:
        values["finish_reason"] = response.choices[0].finish_reason
        if response.choices[0].message:
          values["role"] = response.choices[0].message.role
          values["content"] = response.choices[0].message.content
          values["tool_calls"] = response.choices[0].message.tool_calls

    if not values:
      return False

    if values["finish_reason"] not in ["tool_calls", "stop"]:
      return False

    return response


  def callDeepseek(self, messages, tools=None, complexity=0):


    print("///////////////// DeepSeek ///////////////////")

    print("---------1----------")
    print(messages)
    print("---------1----------")
    print(tools)
    print("---------1----------")

    if tools: 
      newtools = copy.deepcopy(tools)
      for tool in newtools:
        if not tool["function"]["parameters"]:
          del tool["function"]["parameters"]

    else:
      newtools = None

    if tools: 
      response = self.llms['deepseek']['llm_client'].chat.completions.create(
        model = self.llms['deepseek']['llm_models'][complexity],
        messages = messages,
        tools = newtools,
        tool_choice = "auto",
      )
    else:
      response = self.llms['deepseek']['llm_client'].chat.completions.create(
        model = self.llms['deepseek']['llm_models'][complexity],
        messages = messages,
      )

    print("---------2----------")
    print(response)
    print("---------2----------\n\n\n")


    if not response:
      return False

    if not response.choices:
      return False

    if response.choices[0].finish_reason not in ["tool_calls", "stop"]:
      return False

    return response



  def callXai(self, messages, tools=None, complexity=0):

    print("///////////////// xAI ///////////////////")

    if tools: 
      newtools = copy.deepcopy(tools)
      for tool in newtools:
        if "strict" in tool["function"].keys():
          del tool["function"]["strict"]

    else:
      newtools = None

    if tools: 
      response = self.llms['xai']['llm_client'].chat.completions.create(
        model = self.llms['xai']['llm_models'][complexity],
        messages = messages,
        tools = newtools,
        tool_choice = "auto",
      )
    else:
      response = self.llms['xai']['llm_client'].chat.completions.create(
        model = self.llms['xai']['llm_models'][complexity],
        messages = messages,
      )

    print("---------2----------")
    print(response)
    print("---------2----------\n\n\n")


    if not response:
      return False

    if not response.choices:
      return False

    if response.choices[0].finish_reason not in ["tool_calls", "stop"]:
      return False

    return response



  def callOpenai(self, messages, tools=None, complexity=0):

    print("---------1----------")
    print(messages)
    print("---------1----------")
    print(tools)
    print("---------1----------")

    if tools: 
      response = self.llms['openai']['llm_client'].chat.completions.create(
        model = self.llms['openai']['llm_models'][complexity],
        messages = messages,
        tools = tools,
        tool_choice = "auto",
      )
    else:
      response = self.llms['openai']['llm_client'].chat.completions.create(
        model = self.llms['openai']['llm_models'][complexity],
        messages = messages,
      )

    print("---------2----------")
    print(response)
    print("---------2----------\n\n\n")


    if not response:
      return False

    if not response.choices:
      return False

    if response.choices[0].finish_reason not in ["tool_calls", "stop"]:
      return False

    return response


  def callGemini(self, messages, tools=None, complexity=0):

    if tools: 
      model = Gemini.GenerativeModel(model_name=self.llm_models[complexity], tools=tools)
    else:
      model = Gemini.GenerativeModel(model_name=self.llm_models[complexity])

    response = model.start_chat().send_message(
      messages,
    )

    return response





  def generateContextPrompt(self, input, lang, position):
  
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
      llm_call=self.llm
    else:
      llm_call = self.llms[llm]

    return llm_call['func'](messages=messages, tools=tools, complexity=complexity)





  def processRequest(self, input, lang, position):
  
    self.generateContextPrompt(input, lang, position)


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
    prompt = f"""As an AI assistant, you have access to a wide range of functions, far more than your API allows. These functions are grouped into modules. A module is a logical grouping of functions for a specific theme.

    For each new user request, you have access to the conversation history.

    If you need a function that is not in your list of tools to respond to the user's request, you should call the 'modules_needed_to_answer_user_prompt' function with the necessary modules. You can call the 'modules_needed_to_answer_user_prompt' function as many times as needed.

    It is very important that you do not invent module names—only the modules provided in the list exist.

    Once you call the 'modules_needed_to_answer_user_prompt' function, the user's request will be sent back to you with the functions from the requested modules added to your tools. At that point, you can choose the appropriate function(s) to respond to the user's request.
    
    ```json
    {tooling}
    ```
    """
    conversation.append({"role": "system", "content": prompt})

    # Alternative to test: As a language model, you cannot respond to all of my requests. Therefore, you might need additional information. Certain information or functionalities can be found in modules. You can load these modules to assist you in responding by using the load_module function. Below, you will find a complete list of modules along with their descriptions.

    complexity = 1

    llm = "openai"
#
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
            print("Load: " + str(load_modules))
  
            tools = []
            complexity = 0

            #if 'memory' not in load_modules:
            #  load_modules.append('memory')


            for mod in set(load_modules):
              tools = tools + self.services[mod]['tools']

              conversation.append({"role": "system", "content": self.services[mod]["systemContext"]})

              try:
                if self.services[mod]["complexity"] > complexity:
                  complexity = self.services[mod]["complexity"]
                  print(f"Complexity increased to {complexity}")
              except:
                pass


            llm = None

  
          # We are not
          else:

            llm = None
            
            self.history.append(response.choices[0].message.to_dict())
            conversation.append(response.choices[0].message.to_dict())

            for tool_call in response.choices[0].message.tool_calls:
    
              function_name = tool_call.function.name
              function_params = json.loads(tool_call.function.arguments)
    
              print("Call: " + str(function_name) + " with " + str(function_params))
    
              function_result = self.functions[function_name]['function'](**function_params)
    
              if function_result is False:
                self.history.append({"role": 'assistant', "content": "Error while executing the function call"})
                return False
    
  
              if self.functions[function_name]['responseContext'] != "": 
                response_data = self.functions[function_name]['responseContext'] + "```json\n" + json.dumps(function_result) + "\n```"
              else:
                response_data = json.dumps(function_result) 

              self.history.append({"role": 'tool', "content": response_data, "tool_call_id": tool_call.id})
              conversation.append({"role": 'tool', "content": response_data, "tool_call_id": tool_call.id})
  
        else:
          return False
    
      else: 
        return False



