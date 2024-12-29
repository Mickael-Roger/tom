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

    if global_config['global']['llm'] == "mistral":
      self.llm_client = Mistral(api_key=global_config['global']["mistral"]["api"])
      self.llm = self.callMistral
      self.llm_model = "mistral-large-latest"

    elif global_config['global']['llm'] == "openai":
      self.llm_client = OpenAI(api_key=global_config['global']["openai"]["api"])
      self.llm = self.callOpenai
      self.llm_model = "gpt-4o-mini"

    elif global_config['global']['llm'] == "gemini":
      Gemini.configure(api_key=global_config['global']["gemini"]["api"])
      self.llm = self.callGemini
      self.llm_model = "gemini-1.5-flash"

    elif global_config['global']['llm'] == "deepseek":
      self.llm_client = OpenAI(api_key=global_config['global']["deepseek"]["api"], base_url="https://api.deepseek.com")
      self.llm = self.callDeepseek
      self.llm_model = "deepseek-chat"

    else:
      print(f"LLM {global_config['global']['llm']} not supported")
      exit(-1)


    self.history = []

    self.username = user_config['username']

    self.services = {}
    self.functions = {}

    self.user_context = user_config['personalContext']

    self.tts = None

    self.tom_context = f"""Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'.\n\nImportant: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'\n\n{self.user_context} """



  def reset(self):
    print(f"{self.username}: History cleaning")
    self.history = []

    return True



  def callMistral(self, messages, tools=None):
    if tools: 
      response = self.llm_client.chat.complete(
        model = self.llm_model,
        messages = messages,
        tools = tools,
        tool_choice = "auto",
      )
    else:
      response = self.llm_client.chat.complete(
        model = self.llm_model,
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


  def callDeepseek(self, messages, tools=None):


    if tools: 
      newtools = copy.deepcopy(tools)
      for tool in newtools:
        if not tool["function"]["parameters"]:
          del tool["function"]["parameters"]

    else:
      newtools = None

    return self.callOpenai(messages, newtools)



  def callOpenai(self, messages, tools=None):

    print("---------1----------")
    print(messages)
    print("---------1----------")

    if tools: 
      response = self.llm_client.chat.completions.create(
        model = self.llm_model,
        messages = messages,
        tools = tools,
        tool_choice = "auto",
      )
    else:
      response = self.llm_client.chat.completions.create(
        model = self.llm_model,
        messages = messages,
      )

    print("---------2----------")
    print(response)
    print("---------2----------\n\n\n")


    if not response:
      print("prout")
      return False

    if not response.choices:
      print("prout2")
      return False

    if response.choices[0].finish_reason not in ["tool_calls", "stop"]:
      print("prout3")
      return False

    return response


  def callGemini(self, messages, tools=None):

    if tools: 
      model = Gemini.GenerativeModel(model_name=self.llm_model, tools=tools)
    else:
      model = Gemini.GenerativeModel(model_name=self.llm_model)

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

    svc_context = ""
    for service in self.services:
      if self.services[service]['service_context'] != "":
        svc_context = f"{svc_context}\n{self.services[service]['service_context']}\n"

    behaviors = self.services['behavior']['obj'].behavior_get()
    
    



    if self.history: 
      self.history[0] = todayMsg
    else:
      self.history.append(todayMsg)
      self.history.append({"role": "system", "content": self.tom_context})
      self.history.append({"role": "system", "content": f"{svc_context}"})
      if behaviors:
        self.history.append({"role": "system", "content": f"{behaviors}"})


    #behaviors = self.services['behavior']['obj'].behavior_get()
    #if len(behaviors) > 1:
    #  self.history.append({"role": "system", "content": behaviors})
  
    self.history.append({"role": "user", "content": input})






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
    conversation.append({"role": "system", "content": f"Here is a list of modules. For each module, you have the its description. Your role is to call the function 'modules_needed_to_answer_user_prompt' with the module needed to provide me the answer to my request. 'module_name' is not a name of a function, it's a possible value of the parameter of the 'modules_needed_to_answer_prompt'. You must never use the field 'module_name' as a function name.\n{tooling}"})

    # Alternative to test: As a language model, you cannot respond to all of my requests. Therefore, you might need additional information. Certain information or functionalities can be found in modules. You can load these modules to assist you in responding by using the load_module function. Below, you will find a complete list of modules along with their descriptions.
#
    while True:

      response = self.llm(messages=conversation, tools=tools)

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
              #for mod in mods['modules_name']:
              load_modules.append(mod['modules_name'])
            # Todo add something to check if the function name is a module, if so, it's an LLM error and we must use it as if it was a parameter
            if tool_call.function.name in modules_name_list:
              load_modules.append(tool_call.function.name)



          # Yes we are
          if load_modules:
            print("Load: " + str(load_modules))
  
            tools = []
            for mod in load_modules:
              tools = tools + self.services[mod]['tools']
  
          # We are not
          else:
            
            conversation.append(response.choices[0].message.to_dict())

            responseContext = {"functions": [], "rules": []}
    
            for tool_call in response.choices[0].message.tool_calls:
    
              function_name = tool_call.function.name
              function_params = json.loads(tool_call.function.arguments)
    
              print("Call: " + str(function_name) + " with " + str(function_params))
    
                # Memory
                #if function_name == "tom_keep_current_conversation_in_memory":
                #  res, msg = userList[username]['services']['memory'].history_keep(userList[username]['history'], username)
    
                #  if res:
                #    userList[username].reset()
                #    return msg
                #  else:
                #    return "Error while keeping our conversation"
                  
    
                # End of memory
              function_result = self.functions[function_name]['function'](**function_params)
    
              if function_result is False:
                self.history.append({"role": 'assistant', "content": "Error while executing the function call"})
                return False
    
  
              conversation.append({"role": 'tool', "content": json.dumps(function_result), "tool_call_id": tool_call.id})
                
              # TODODODODODDODODO
              if function_name not in responseContext['functions']:
                responseContext['functions'].append(function_name)
                if self.functions[function_name]['responseContext'] != "":
                  responseContext['rules'].append({"role": "system", "content": self.functions[function_name]['responseContext']})
              
    
            conversation = conversation + responseContext['rules']
  
        else:
          return False
    
      else: 
        return False



