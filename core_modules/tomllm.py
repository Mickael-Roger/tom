import json
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder
from datetime import datetime
import copy



# OpenAI
from openai import OpenAI
# Mistral AI
from mistralai import Mistral




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

    return True, response


  def callOpenai(self, messages, tools=None):

    print("--------------------------------")
    print(messages)
    print("++++++++++++++++++++++++++++++++")
    print(tools)
    print("--------------------------------")


    if tools: 
      response = self.llm_client.chat.completions.create(
        model = self.llm_model,
        messages = messages,
        tools = tools,
      )
    else:
      response = self.llm_client.chat.completions.create(
        model = self.llm_model,
        messages = messages,
      )

    return True, response



  def generateContextPrompt(self, input, lang, position):
  
    current_timezone = ZoneInfo("Europe/Paris")
    if position is not None:
      tf = TimezoneFinder()
      current_timezone = ZoneInfo(tf.timezone_at(lat=position['latitude'], lng=position['longitude']))
  
  
    today= datetime.now(current_timezone).strftime("%A %d %B %Y %H:%M:%S")
    weeknumber = datetime.now().isocalendar().week
    todayMsg = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}.\n\n"}
  
    if self.history: 
      self.history[0] = todayMsg
    else:
      self.history.append(todayMsg)
  
    if len(self.history) == 1: 
      self.history.append({"role": "system", "content": self.tom_context})
  
    if position is not None:
      self.history.append({"role": "system", "content": f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}"})


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


    triage_tools = [
      {
        "type": "function",
        "function": {
          "name": "modules_needed_to_answer_user_prompt",
          "description": "Get information about a train station. For a train, subway or tram station, this function returns its ID, name, city and all the lines of the station",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "modules_name": {
                "type": "array",
                "items": {
                  "type": "string",
                  "enum": modules_name_list,
                },
                "description": f"List of module names",
              },
            },
            "required": ["modules_name"],
            "additionalProperties": False,
          },
        },
      },
    ]

    conversation = []
    conversation.append({"role": "system", "content": self.tom_context})
  
    if position is not None:
      conversation.append({"role": "system", "content": f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}"})

    svc_context = ""
    for service in self.services:
      if self.services[service]['service_context'] != "":
        svc_context = f"{svc_context}\n{self.services[service]['service_context']}"
    
    conversation.append({"role": "system", "content": f"{svc_context}"})

    tooling = json.dumps(available_tools)
    conversation.append({"role": "system", "content": f"Here is a list of modules. For each module, you have the its description. Your role is to call the function 'modules_needed_to_answer_user_prompt' with the list of modules needed to provide me the answer to my request.\n{tooling}"})
#
#
    # Create a message history with only 'user' and 'assistant' role messages
    for message in self.history:
      if isinstance(message, dict):     
        if "role" in message.keys():
          if message['role'] in ["assistant", "user"]:
            conversation.append(message)
#

    ret, triage = self.llm(messages=conversation, tools=triage_tools)


    load_modules= []

    # No more thing to process, just return the answer
    if triage.choices is not None:
      if triage.choices[0].message.content is not None:
        self.history.append({"role": triage.choices[0].message.role, "content": triage.choices[0].message.content})
        return triage.choices[0].message.content

      
      if triage.choices[0].message.tool_calls is not None:
        for tool_call in triage.choices[0].message.tool_calls:
          if tool_call.function.name.find("modules_needed_to_answer_user_prompt") != -1:    # Probably bad prompt, but sometimes it calls 'module_name.modules_needed_to_answer_user_prompt'
            mods = json.loads(tool_call.function.arguments)
            for mod in mods['modules_name']:
              load_modules.append(mod)

        print("Load: " + str(load_modules))
        print(type(load_modules))

    else: 
      return "Error, no response from LLM"

  

    # Triage:
    #  Add the triage prompt
    #   -> Response without any fonction calls: Return response
    #   -> Add the function calling for modules: Continue with the list of modules until no response

    tools = []
    for mod in list(set(load_modules)):
      tools = tools + self.services[mod]['tools']

    print("Tools: " + str(tools))
  
    while True:
      
      ret, response = self.llm(messages=self.history, tools=tools)
  
      if not ret:
        return f"Error: {response}"
      elif response is None:
        return f"Error: No response from LLM"
  
  
      if response.choices is not None:
  
        if response.choices[0].message.content is not None:
          self.history.append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})
  
        if response.choices[0].message.tool_calls is not None:
  
          self.history.append(response.choices[0].message)
  
          print("\n\n\n*******************************************************")
          print(self.history)
          print("********************************************************\n\n\n")
  
          responseContext = {"functions": [], "rules": []}
  
          for tool_call in response.choices[0].message.tool_calls:
  
            #tool_call = response.choices[0].message.tool_calls[0]
  
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
              
  
            print(self.functions.keys())
  
            # End of memory
            res, function_result = self.functions[function_name]['function'](**function_params)
  
            if res is False:
              return "Error execution the function"
  
  
            print(res)
            print(function_result)

            self.history.append({"role": 'tool', "content": json.dumps(function_result), "tool_call_id": tool_call.id})
            
            # TODODODODODDODODO
            if function_name not in responseContext['functions']:
              responseContext['functions'].append(function_name)
              responseContext['rules'].append({"role": "system", "content": self.functions[function_name]['responseContext']})
  
          self.history = self.history + responseContext['rules']
  
          print("\n\n\n********************** 2 *********************************")
          print(self.history)
          print("********************************************************\n\n\n")
  
  
        else:
  
          print("\n\n\n********************** 3 *********************************")
          print(response.choices[0].message.content)
          print("********************************************************\n\n\n")
  
          return response.choices[0].message.content
  
      else:
        return "Error: Response choices is None"






#startNewConversationTools = [
#  {
#    "type": "function",
#    "function": {
#        "description": "This function must be called to start a new conversation with the user. Must be called when the user say: 'Hey', 'Hi', 'Hi Tom', 'Hey Tom' or 'Change of topic' or 'Let\'s change the subject'",
#        "name": "start_new_conversation",
#        "parameters": {
#        },
#    },
#  },
#]




#def processLLM(messages, tools, global_config):
#
#
#
#  llm_tools = startNewConversationTools
#
#  # Wee ned some tricks to handle the limitation of the maximum number of tools we can declare
#  # This idea is to provide the history context + make a call that's not gonna be part of the history. This call will contains a json list of all functions (grouped by modules) and ask the LLM which modules does it needs to answer, then add all functions of these modules in the next (and real user requests. It's only ine function that is called (module_selection)). If the answer does not contains a call to this function. It means the LLM jus tprovide an answer without needs of function calling. In that case, we just return the answer, no need to perform the same query twice
#
#  available_tools = []
#  modules_name_list = []
#
#  if tools is not None:
#    for module, functions in tools.items():
#      functions_list = []
#      for function in functions:
#        functions_list.append({"function_name": function['function']['name'], "function_description": function['function']['description']})
#
#      available_tools.append({"module_name": module, "functions": functions_list})
#      modules_name_list.append(module)
#
#
#    selection_tools = [
#      {
#        "type": "function",
#        "function": {
#          "name": "modules_needed_to_answer_user_prompt",
#          "description": "Get information about a train station. For a train, subway or tram station, this function returns its ID, name, city and all the lines of the station",
#          "strict": True,
#          "parameters": {
#            "type": "object",
#            "properties": {
#              "modules_name": {
#                "type": "array",
#                "items": {
#                  "type": "string",
#                  "enum": modules_name_list,
#                },
#                "description": f"List of module names",
#              },
#            },
#            "required": ["modules_name"],
#            "additionalProperties": False,
#          },
#        },
#      },
#    ]
#
#    tooling = json.dumps(available_tools)
#    conversation = []
#    # Here is a list of modules. For each module, you have the list of its functions.
#    conversation.append({"role": "system", "content": f"Here is a list of modules. For each module, you have the list of its functions. Your role is to call the function 'modules_needed_to_answer_user_prompt' with the list of modules needed to provide me with the answer to my request.\n{tooling}"})
#
#
#    # Create a message history with only 'user' and 'assistant' role messages
#    for message in messages:
#      if isinstance(message, dict):     
#        if "role" in message.keys():
#          if message['role'] in ["assistant", "user"]:
#            conversation.append(message)
#
#
#    print("-------- EXECUTE ---------", flush=True)
#    print(conversation, flush=True)
#    print("--------------", flush=True)
#    print(llm_tools + selection_tools, flush=True)
#    print("--------------", flush=True)
#
#
#    if global_config['global']['llm'] == "mistral":
#      response = mistralClient.chat.complete(
#        model = mistralmodel,
#        messages = conversation,
#        tools = llm_tools + selection_tools,
#        tool_choice = "auto",
#      )
#    elif global_config['global']['llm'] == "openai":
#      response = openaiClient.chat.completions.create(
#        model = openaimodel,
#        messages = conversation,
#        tools = llm_tools + selection_tools,
#      )
#    else:
#      print("LLM not defined")
#      return False, "LLM not defined"
#
#
#    print(response)
#
#    exit(0)
#
#  
#
#
#
#
#
#
#
#
#  print("-------- EXECUTE ---------", flush=True)
#  print(messages, flush=True)
#  print("--------------", flush=True)
#
#
#  if tools: 
#    if global_config['global']['llm'] == "mistral":
#      response = mistralClient.chat.complete(
#        model = mistralmodel,
#        messages = messages,
#        tools = llm_tools + tools,
#        tool_choice = "auto",
#      )
#    elif global_config['global']['llm'] == "openai":
#      response = openaiClient.chat.completions.create(
#        model = openaimodel,
#        messages = messages,
#        tools = llm_tools + tools,
#      )
#    else:
#      print("LLM not defined")
#      return False, "LLM not defined"
#  else:
#    if global_config['global']['llm'] == "mistral":
#      response = mistralClient.chat.complete(
#        model = mistralmodel,
#        messages = messages
#      )
#    elif global_config['global']['llm'] == "openai":
#      response = openaiClient.chat.completions.create(
#        model = openaimodel,
#        messages = messages
#      )
#    else:
#      print("LLM not defined")
#      return False, "LLM not defined"
#
#  print("-------- RESPONSE ---------", flush=True)
#  print(response, flush=True)
#  print("--------------", flush=True)
#
#  return True, response


