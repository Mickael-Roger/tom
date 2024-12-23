# Core
import cherrypy
import yaml
import os
import json
import sys
import importlib.util
import inspect
from datetime import datetime, timedelta
import tempfile
import base64
import subprocess
from TTS.api import TTS
import functools
import sqlite3


# OpenAI
from openai import OpenAI

# Mistral
from mistralai import Mistral


################################################################################################
#                                                                                              #
#                              Tom configuration management                                    #
#                                                                                              #
################################################################################################
config = {}

def initConf():
  # Load config
  with open('config.yml', 'r') as file:
    try:
      conf = yaml.safe_load(file)
    except yaml.YAMLError as exc:
      print(f"Error reading YAML file: {exc}")
      exit(1)

  return conf



################################################################################################
#                                                                                              #
#                                     Modules loading                                          #
#                                                                                              #
################################################################################################
mod_dir = './modules'

# Iterate over the files in the 'modules' directory
for filename in os.listdir(mod_dir):
    if filename.endswith('.py') and filename != '__init__.py':
        # Construct the full path to the module file
        module_name = filename[:-3]  # Remove the '.py' extension
        file_path = os.path.join(mod_dir, filename)
        
        # Dynamically import the module
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Inspect the module and add all classes to the global namespace
        for name, obj in inspect.getmembers(module, inspect.isclass):
            globals()[name] = obj


################################################################################################
#                                                                                              #
#                                 Memorization capability                                      #
#                                                                                              #
################################################################################################
class TomMemory:

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "memory.sqlite")

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        summary TEXT,
        conversation BLOB
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_keep_current_conversation_in_memory",
          "description": "Keep the conversation in Tom's memory. For example when a user aks 'Keep that conversation in memory'",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_list_old_conversations",
          "description": "List all old conversation we previously had. For example when a user aks 'Do we have already talked about something?', 'We already talked about that, could you remember?'. Will return, the conversation ID, the datetime of the conversation and a summary of it.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_retreive_old_conversation_content",
          "description": "Retreive the content of an old conversation we previously had.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "conversation_id": {
                "type": "string",
                "description": f"ID of the conversation",
              },
            },
            "required": ["conversation_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_old_conversation_content",
          "description": "Delete from your memory an old conversation we previously had.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "conversation_id": {
                "type": "string",
                "description": f"ID of the conversation",
              },
            },
            "required": ["conversation_id"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""

    self.answerContext = {
      "tom_keep_current_conversation_in_memory": "",
      "tom_list_old_conversations": "",
      "tom_retreive_old_conversation_content": "",
      "tom_delete_old_conversation_content": "",
    }


  def history_get(self, conversation_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT id, datetime, conversation FROM conversations WHERE id = ?', (conversation_id,))
    val = cursor.fetchone()
    dbconn.close()


    return True, {"id": val[0], "datetime": val[1], "conversation": val[2]}


  def history_delete(self, conversation_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('DELETE FROM conversations WHERE id = ?', (conversation_id,))
    dbconn.commit()
    dbconn.close()

    return True, "Conversation deleted"


  def history_list(self):

    history = []

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT id, datetime, summary FROM conversations')
    values = cursor.fetchall()
    dbconn.close()

    for val in values:
      history.append({"id": val[0], "datetime": val[1], "conversation_summary": val[2]})

    return True, history



  def history_keep(self, history):

    conversation = []

    # Parse conversation
    for message in history:
      if isinstance(message, dict):     
        if "role" in message.keys():
          if message['role'] in ["assistant", "user"]:
            conversation.append(message)

    # Then make a summary and extract keywords
    systemContext = """The user input will be a conversation between you and me. You will need to respond with a brief summary of this conversation."""

    conversation = json.dumps(conversation)
    messages = [{"role": "system", "content": systemContext},{"role": "user", "content": conversation}]

    res, response = processLLM(messages, None)

    if res:
      db = self.db

      if response.choices is not None:
        if response.choices[0].message.content is not None:

          summary = str(response.choices[0].message.content)

          dbconn = sqlite3.connect(db)
          cursor = dbconn.cursor()
          cursor.execute('INSERT INTO conversations (summary, conversation) VALUES (?, ?)', (summary, conversation))
          dbconn.commit()
          dbconn.close()

      return True, "Conversation kept in memory"

    else:
      return False, "Could not keep conversation in memory"


################################################################################################
#                                                                                              #
#                                   Behavior capability                                        #
#                                                                                              #
################################################################################################
class TomBehavior:

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "memory.sqlite")

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists behaviors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        date_from DATETIME DEFAULT '2020-01-01',
        date_to DATETIME DEFAULT '2030-01-01',
        behavior TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_list_behaviors",
          "description": "List all prompts that modify you behavior. For example when a user aks 'What are your specific behavior?', 'Do I ask you to behave like that?', 'What are you specific consignes?'. Will return, the behaviour ID, the application datetime from and to and the behavior description.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_behavior",
          "description": "Remove a previously prompt that ask you to behave in a certain way. For example when a user aks 'Stop behaving like that', 'Remove this consigne'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "behavior_id": {
                "type": "string",
                "description": f"ID of the behavior",
              },
            },
            "required": ["behavior_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_add_behavior",
          "description": "Add an explicit prompt to change you behavior. For example when a user aks 'I want you to change you behavior', 'Add this consigne'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "behavior_consigne": {
                "type": "string",
                "description": f"The new behavior consigne",
              },
            },
            "required": ["behavior_consigne"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""

    self.answerContext = {
      "tom_list_behaviors": "",
      "tom_add_behavior": "",
      "tom_delete_behavior": "",
    }

  def behavior_get(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT behavior FROM behaviors WHERE datetime('now') > date_from AND datetime('now') < date_to")
      values = cursor.fetchall()
      dbconn.close()

      behavior = ""
      for val in values:
        behavior = behavior + "\nTu as une nouvelle consigne: " + val[0]

      return behavior

    except:
      return ""


  def behavior_add(self, behavior_consigne, date_from='2020-01-01', date_to='2030-01-01'):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("INSERT INTO behaviors (date_from, date_to, behavior) VALUES (?, ?, ?)", (date_from, date_to, behavior_consigne))
      dbconn.commit()
      dbconn.close()

      return True, "Behavior added"

    except:
      return False, "Cannot add behavior"


  def behavior_delete(self, behavior_id):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("DELETE FROM behaviors WHERE id = ?", (behavior_id))
      dbconn.commit()
      dbconn.close()

      return True, "Behavior removed"

    except:
      return False, "Cannot remove behavior"



  def behavior_list(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT id, date_from, date_to, behavior FROM behaviors")
      values = cursor.fetchall()
      dbconn.close()

      behaviors = []
      for val in values:
        behaviors.append({"id": val[0], "date_from": val[1], "date_to": val[2], "behavior": val[3]})

      return True, behaviors

    except:
      return False, "Could not list behaviors"





################################################################################################
#                                                                                              #
#                                       TTS Capabilities                                       #
#                                                                                              #
################################################################################################
class TomTTS:

  def __init__(self, config):

    self.models = {}
    for lang in config['global']['tts']['langs'].keys():
      self.models[lang] = TTS(config['global']['tts']['langs'][lang]['model'], progress_bar=False).to("cpu")


  def infere(self, input, lang):
  
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wavFile:
      wavFileName = wavFile.name
      self.models[lang].tts_to_file(text=input, language=config['global']['tts']['langs'][lang]['language'], speaker=config['global']['tts']['langs'][lang]['speaker'], file_path=wavFileName)
  
      base64_result = self.ConvertToMp3(wavFileName)
  
      os.remove(wavFileName)
  
    return base64_result
  
  
  
  
  def ConvertToMp3(self, wavfile):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3File:
      mp3FileName = mp3File.name
  
      subprocess.run(['ffmpeg', '-y', '-i', wavfile, '-c:a', 'mp3', mp3FileName], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  
      with open(mp3FileName, 'rb') as temp_file2:
        output_data = temp_file2.read()
  
      base64_data = base64.b64encode(output_data).decode('utf-8')
  
      os.remove(mp3FileName)
  
      return base64_data






################################################################################################
#                                                                                              #
#                                    CherryPy API endpoint                                     #
#                                                                                              #
################################################################################################
class TomWebService:

  #  def __init__(self):
  #    self.sessions = {}


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  def index(self):
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")
    
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()

  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_out()
  def reset(self):
    if reset(username=cherrypy.session['username']):
      return {"success": True}
    else:
      raise cherrypy.HTTPError(500, "Could not reset and save the session")


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):
    
    if not self.check_auth():
       raise cherrypy.HTTPRedirect("/auth")

    input_json = cherrypy.request.json

    print("+++++++")
    print(input_json)
    print("+++++++")
    
    user = input_json.get('request')
    lang = input_json.get('lang')
    position = input_json.get('position')
    localTTS = input_json.get('tts')

    print(cherrypy.session['username'])

    response = processRequest(input=user, username=cherrypy.session['username'], lang=lang, position=position)

    voice= None
    if not localTTS:
      voice = userList[username]['tts'].infere(response, lang)

    return {"response": response, "voice": voice} 

  @cherrypy.expose
  def auth(self):
    with open(os.path.join('static', 'auth.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  def login(self, username, password):

    for user in global_config['users']:
      if user['username'] == username and user['password'] == password:
        cherrypy.session['username'] = username
        print(f"History cleaning for user {username}")
        userList[username]['history'] = []

        raise cherrypy.HTTPRedirect("/index")

    return "Invalid credentials. <a href='/auth'>Try again</a>"



  def check_auth(self):
    if cherrypy.session.get('username', None) is not None:
      return True
      
    raise cherrypy.HTTPRedirect("/auth")
    



startNewConversationTools = [
  {
    "type": "function",
    "function": {
        "description": "This function must be called to start a new conversation with the user. Must be called when the user say: 'Hey', 'Hi', 'Hi Tom', 'Hey Tom' or 'Change of topic' or 'Let\'s change the subject'",
        "name": "start_new_conversation",
        "parameters": {
        },
    },
  },
]


def processLLM(messages, tools):


  mistralmodel = "mistral-large-latest"
  openaimodel = "gpt-4o-mini"

  print("-------- EXECUTE ---------", flush=True)
  print(messages, flush=True)
  print("--------------", flush=True)

  if tools: 
    if global_config['global']['llm'] == "mistral":
      response = mistralClient.chat.complete(
        model = mistralmodel,
        messages = messages,
        tools = tools,
        tool_choice = "auto",
      )
    elif global_config['global']['llm'] == "openai":
      response = openaiClient.chat.completions.create(
        model = openaimodel,
        messages = messages,
        tools = tools,
      )
    else:
      print("LLM not defined")
      return False, "LLM not defined"
  else:
    if global_config['global']['llm'] == "mistral":
      response = mistralClient.chat.complete(
        model = mistralmodel,
        messages = messages
      )
    elif global_config['global']['llm'] == "openai":
      response = openaiClient.chat.completions.create(
        model = openaimodel,
        messages = messages
      )
    else:
      print("LLM not defined")
      return False, "LLM not defined"

  print("-------- RESPONSE ---------", flush=True)
  print(response, flush=True)
  print("--------------", flush=True)

  return True, response


def reset(username):

  print("History cleaning")
  userList[username]['history'] = []
  return True


def generateContextPrompt(input, username, lang, position):

  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")
  weeknumber = datetime.now().isocalendar().week
  todayMsg = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}.\n\n"}

  if userList[username]['history']: 
    userList[username]['history'][0] = todayMsg
  else:
    userList[username]['history'].append(todayMsg)

  if len(userList[username]['history']) == 1: 
    userList[username]['history'].append({"role": "system", "content": "Your name is Tom and you are my personal life assistant. When your answer contains a date, it must be in the form 'Weekday day month'." +"\n\n" + "Important: 'Do not make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous'" + "\n\n" + userList[username]['systemContext']})

  if position is not None:
    userList[username]['history'].append({"role": "system", "content": f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}"})

  behavior= userList[username]['services']['behavior'].behavior_get()
  if len(behavior) > 1:
    userList[username]['history'].append({"role": "system", "content": behavior})

  userList[username]['history'].append({"role": "user", "content": input})



def processRequest(input, username, lang, position):

  tools = userList[username]['tools']

  generateContextPrompt(input, username, lang, position)

  while True:
    
    ret, response = processLLM(userList[username]['history'], tools)

    if not ret:
      return f"Error: {response}"
    elif response is None:
      return f"Error: No response from LLM"


    if response.choices is not None:

      if response.choices[0].message.content is not None:
        userList[username]['history'].append({"role": response.choices[0].message.role, "content": response.choices[0].message.content})

      if response.choices[0].message.tool_calls is not None:

        userList[username]['history'].append(response.choices[0].message)

        print("\n\n\n*******************************************************")
        print(userList[username]['history'])
        print("********************************************************\n\n\n")

        responseContext = {"functions": [], "rules": []}

        for tool_call in response.choices[0].message.tool_calls:

          #tool_call = response.choices[0].message.tool_calls[0]

          function_name = tool_call.function.name
          function_params = json.loads(tool_call.function.arguments)

          print("Call: " + str(function_name) + " with " + str(function_params))

          if function_name == "start_new_conversation":
            if reset(username=cherrypy.session['username']):
              return f"Hi {username}"
            else:
              return "Error while saving your history"


          # Memory
          if function_name == "tom_keep_current_conversation_in_memory":
            res, msg = userList[username]['services']['memory'].history_keep(userList[username]['history'], username)

            if res:
              reset(username)
              return msg
            else:
              return "Error while keeping our conversation"
            


          # End of memory

          res, function_result = userList[username]['functions'][function_name]['function'](**function_params)

          print(res)
          print(function_result)

          if res is False:
            return "Error execution the function"

          userList[username]['history'].append({"role": 'tool', "content": json.dumps(function_result), "tool_call_id": tool_call.id})
          
          # TODODODODODDODODO
          if function_name not in responseContext['functions']:
            responseContext['functions'].append(function_name)
            responseContext['rules'].append({"role": "system", "content": userList[username]['functions'][function_name]['responseContext']})

        userList[username]['history'] = userList[username]['history'] + responseContext['rules']

        print("\n\n\n********************** 2 *********************************")
        print(userList[username]['history'])
        print("********************************************************\n\n\n")


      else:

        print("\n\n\n********************** 3 *********************************")
        print(response.choices[0].message.content)
        print("********************************************************\n\n\n")

        return response.choices[0].message.content

    else:
      return "Error: Response choices is None"



################################################################################################
#                                                                                              #
#                                         Main                                                 #
#                                                                                              #
################################################################################################

global_config = {}

global_config = initConf()

tts = TomTTS(global_config)

userList = {}

for user in global_config['users']:
  username = user['username']
  userList[username] = {}
  userList[username]['history'] = []
  userList[username]['services'] = {}

  userList[username]['systemContext'] = user['personalContext'] + "\n\n"

  userList[username]['functions'] = {}


  userList[username]['tools'] = startNewConversationTools

  for service_name in user['services'].keys():

    if service_name == "calendar":
      userList[username]['services']['calendar'] = TomCalendar(user['services']['calendar'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['calendar'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['calendar'].systemContext + "\n\n"
      userList[username]['functions']['calendar_add'] = {"function": functools.partial(userList[username]['services']['calendar'].addEvent), "responseContext": userList[username]['services']['calendar'].answerContext['calendar_add']}
      userList[username]['functions']['calendar_search'] = {"function": functools.partial(userList[username]['services']['calendar'].search), "responseContext": userList[username]['services']['calendar'].answerContext['calendar_search']}

    if service_name == "groceries":
      userList[username]['services']['groceries'] = TomGroceries(user['services']['groceries'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['groceries'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['groceries'].systemContext + "\n\n"
      userList[username]['functions']['grocery_list_content'] = {"function": functools.partial(userList[username]['services']['groceries'].listProducts), "responseContext": userList[username]['services']['groceries'].answerContext['grocery_list_content']}
      userList[username]['functions']['grocery_list_add'] = {"function": functools.partial(userList[username]['services']['groceries'].add), "responseContext": userList[username]['services']['groceries'].answerContext['grocery_list_add']}
      userList[username]['functions']['grocery_list_remove'] = {"function": functools.partial(userList[username]['services']['groceries'].remove), "responseContext": userList[username]['services']['groceries'].answerContext['grocery_list_remove']}

    if service_name == "todo":
      userList[username]['services']['todo'] = TomTodo(user['services']['todo'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['todo'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['todo'].systemContext + "\n\n"
      userList[username]['functions']['todo_list_all'] = {"function": functools.partial(userList[username]['services']['todo'].listTasks), "responseContext": userList[username]['services']['todo'].answerContext['todo_list_all']}
      userList[username]['functions']['todo_close_task'] = {"function": functools.partial(userList[username]['services']['todo'].close), "responseContext": userList[username]['services']['todo'].answerContext['todo_close_task']}
      userList[username]['functions']['todo_create_task'] = {"function": functools.partial(userList[username]['services']['todo'].create), "responseContext": userList[username]['services']['todo'].answerContext['todo_create_task']}

    if service_name == "anki":
      userList[username]['services']['anki'] = TomAnki(user['services']['anki'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['anki'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['anki'].systemContext + "\n\n"
      userList[username]['functions']['anki_list_decks'] = {"function": functools.partial(userList[username]['services']['anki'].slist_decks), "responseContext": userList[username]['services']['anki'].answerContext['anki_list_decks']}
      userList[username]['functions']['anki_list_due_cards'] = {"function": functools.partial(userList[username]['services']['anki'].due_cards), "responseContext": userList[username]['services']['anki'].answerContext['anki_list_due_cards']}
      userList[username]['functions']['anki_list_all_cards'] = {"function": functools.partial(userList[username]['services']['anki'].list_cards), "responseContext": userList[username]['services']['anki'].answerContext['anki_list_all_cards']}
      userList[username]['functions']['anki_review_card'] = {"function": functools.partial(userList[username]['services']['anki'].card_review), "responseContext": userList[username]['services']['anki'].answerContext['anki_review_card']}
      userList[username]['functions']['anki_add_card'] = {"function": functools.partial(userList[username]['services']['anki'].add_card), "responseContext": userList[username]['services']['anki'].answerContext['anki_add_card']}

    if service_name == "kwyk":
      userList[username]['services']['kwyk'] = TomKwyk(user['services']['kwyk'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['kwyk'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['kwyk'].systemContext + "\n\n"
      userList[username]['functions']['kwyk_get'] = {"function": functools.partial(userList[username]['services']['kwyk'].get), "responseContext": userList[username]['services']['kwyk'].answerContext['kwyk_get']}

    if service_name == "cafetaria":
      userList[username]['services']['cafetaria'] = TomCafetaria(user['services']['cafetaria'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['cafetaria'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['cafetaria'].systemContext + "\n\n"
      userList[username]['functions']['get_cafetaria_credit'] = {"function": functools.partial(userList[username]['services']['cafetaria'].credit), "responseContext": userList[username]['services']['cafetaria'].answerContext['get_cafetaria_credit']}
      userList[username]['functions']['list_cafetaria_reservations'] = {"function": functools.partial(userList[username]['services']['cafetaria'].reservations), "responseContext": userList[username]['services']['cafetaria'].answerContext['list_cafetaria_reservations']}
      userList[username]['functions']['make_a_cafetaria_reservation'] = {"function": functools.partial(userList[username]['services']['cafetaria'].add), "responseContext": userList[username]['services']['cafetaria'].answerContext['make_a_cafetaria_reservation']}
      userList[username]['functions']['cancel_a_cafetaria_reservation'] = {"function": functools.partial(userList[username]['services']['cafetaria'].cancel), "responseContext": userList[username]['services']['cafetaria'].answerContext['cancel_a_cafetaria_reservation']}

    if service_name == "pronote":
      userList[username]['services']['pronote'] = TomPronote(user['services']['pronote'])
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['pronote'].tools
      userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['pronote'].systemContext + "\n\n"
      userList[username]['functions']['list_grade_averages'] = {"function": functools.partial(userList[username]['services']['pronote'].averages), "responseContext": userList[username]['services']['pronote'].answerContext['list_grade_averages']}
      userList[username]['functions']['list_grades'] = {"function": functools.partial(userList[username]['services']['pronote'].grades), "responseContext": userList[username]['services']['pronote'].answerContext['list_grades']}
      userList[username]['functions']['list_homeworks'] = {"function": functools.partial(userList[username]['services']['pronote'].homeworks), "responseContext": userList[username]['services']['pronote'].answerContext['list_homeworks']}
      userList[username]['functions']['list_school_absences'] = {"function": functools.partial(userList[username]['services']['pronote'].absences), "responseContext": userList[username]['services']['pronote'].answerContext['list_school_absences']}
      userList[username]['functions']['list_school_delays'] = {"function": functools.partial(userList[username]['services']['pronote'].delays), "responseContext": userList[username]['services']['pronote'].answerContext['list_school_delays']}
      userList[username]['functions']['list_school_punishments'] = {"function": functools.partial(userList[username]['services']['pronote'].punishments), "responseContext": userList[username]['services']['pronote'].answerContext['list_school_punishments']}
      userList[username]['functions']['list_school_teachers'] = {"function": functools.partial(userList[username]['services']['pronote'].teachers), "responseContext": userList[username]['services']['pronote'].answerContext['list_grades']}
      userList[username]['functions']['get_school_calendar'] = {"function": functools.partial(userList[username]['services']['pronote'].getCal), "responseContext": userList[username]['services']['pronote'].answerContext['get_school_calendar']}
      userList[username]['functions']['list_school_observations'] = {"function": functools.partial(userList[username]['services']['pronote'].observations), "responseContext": userList[username]['services']['pronote'].answerContext['list_school_observations']}
      userList[username]['functions']['list_school_evaluations'] = {"function": functools.partial(userList[username]['services']['pronote'].evaluations), "responseContext": userList[username]['services']['pronote'].answerContext['list_school_evaluations']}
      userList[username]['functions']['list_school_information_communication'] = {"function": functools.partial(userList[username]['services']['pronote'].informations), "responseContext": userList[username]['services']['pronote'].answerContext['list_school_information_communication']}
      userList[username]['functions']['pronote_mark_as_seen'] = {"function": functools.partial(userList[username]['services']['pronote'].mark_seen), "responseContext": userList[username]['services']['pronote'].answerContext['pronote_mark_as_seen']}
      userList[username]['functions']['get_school_information_communication_message'] = {"function": functools.partial(userList[username]['services']['pronote'].information_message), "responseContext": userList[username]['services']['pronote'].answerContext['get_school_information_communication_message']}

    userList[username]['services']['weather'] = TomWeather()
    userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['weather'].tools
    userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['weather'].systemContext + "\n\n"
    userList[username]['functions']['weather_get_by_gps_position'] = {"function": functools.partial(userList[username]['services']['weather'].getGps), "responseContext": userList[username]['services']['weather'].answerContext['weather_get_by_gps_position']}
    userList[username]['functions']['get_gps_position_by_city_name'] = {"function": functools.partial(userList[username]['services']['weather'].getCity), "responseContext": userList[username]['services']['weather'].answerContext['get_gps_position_by_city_name']}


    # Memory functions
    if user['memory']:
      userList[username]['services']['memory'] = TomMemory(global_config, username)
      userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['memory'].tools
      userList[username]['functions']['tom_list_old_conversations'] = {"function": functools.partial(userList[username]['services']['memory'].history_list), "responseContext": userList[username]['services']['memory'].answerContext['tom_list_old_conversations']}
      userList[username]['functions']['tom_retreive_old_conversation_content'] = {"function": functools.partial(userList[username]['services']['memory'].history_get), "responseContext": userList[username]['services']['memory'].answerContext['tom_retreive_old_conversation_content']}
      userList[username]['functions']['tom_delete_old_conversation_content'] = {"function": functools.partial(userList[username]['services']['memory'].history_delete), "responseContext": userList[username]['services']['memory'].answerContext['tom_delete_old_conversation_content']}

    userList[username]['services']['behavior'] = TomBehavior(global_config, username)
    userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['behavior'].tools
    userList[username]['functions']['tom_list_behaviors'] = {"function": functools.partial(userList[username]['services']['behavior'].behavior_list), "responseContext": userList[username]['services']['behavior'].answerContext['tom_list_behaviors']}
    userList[username]['functions']['tom_add_behavior'] = {"function": functools.partial(userList[username]['services']['behavior'].behavior_add), "responseContext": userList[username]['services']['behavior'].answerContext['tom_add_behavior']}
    userList[username]['functions']['tom_delete_behavior'] = {"function": functools.partial(userList[username]['services']['behavior'].behavior_delete), "responseContext": userList[username]['services']['behavior'].answerContext['tom_delete_behavior']}




    #userList[username]['services']['idfm'] = Idfm(config['global']['idfm'])
    #userList[username]['tools'] = userList[username]['tools'] + userList[username]['services']['idfm'].tools
    #userList[username]['systemContext'] = userList[username]['systemContext'] + userList[username]['services']['idfm'].systemContext + "\n\n"
    #userList[username]['functions']['get_train_schedule'] = {"function": functools.partial(userList[username]['services']['idfm'].schedule), "responseContext": userList[username]['services']['idfm'].answerContext['get_train_schedule']}
    #userList[username]['functions']['get_train_disruption'] = {"function": functools.partial(userList[username]['services']['idfm'].disruption), "responseContext": userList[username]['services']['idfm'].answerContext['get_train_disruption']}
    
    userList[username]['tts'] = tts


mistralClient = Mistral(api_key=global_config['global']["mistral"]["api"])
openaiClient = OpenAI(api_key=global_config['global']["openai"]["api"])


if __name__ == "__main__":    

  cherrypy.config.update({
    'server.socket_host': '0.0.0.0', 
    'server.socket_port': 8082, 
    'tools.sessions.on': True, 
    'tools.sessions.timeout': 3600 * 24 * 30,
    'tools.sessions.storage_type': 'file',
    'tools.sessions.storage_path': global_config['global']['sessions'] 
  })
  cherrypy.quickstart(TomWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

