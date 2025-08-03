import os
import functools
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import time
import json
from datetime import datetime
import tomlogger

################################################################################################
#                                                                                              #
#                                   Memory capability                                          #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "memory",
  "class_name": "TomMemory",
  "description": """This module manages personal memory storage for important user information. It automatically stores personal details, preferences, and situational information shared by the user.

     AUTOMATIC STORAGE (no confirmation needed):
     - Personal facts: "My PIN code is 1234," "Today I went to the doctor," "I live at 123 Main Street"
     - Life events: "Today I had a job interview," "I bought a new car," "I moved to a new apartment"
     - Situational details: "I left my keys on the table," "I parked in spot B12," "The Wi-Fi password is abc123"
     - Preferences: "I prefer coffee without sugar," "I usually take the 8:15 train"
     - Daily activities: "Today I went shopping," "I had lunch with Sarah," "I finished my project"

     DO NOT STORE:
     - Requests for other modules (Nintendo Switch control, calendar management, weather queries, etc.)
     - Technical questions or troubleshooting
     - General conversations without personal information
     - Commands or requests for actions

     LOCATION STORAGE:
     When storing location information, save GPS coordinates with descriptive details like parking spot number, street name, or nearby landmarks.

     This module must be used when the user explicitly asks you to search in your memory or shares personal information.
    """,
  "type": "core",
  "complexity": 0
}

class TomMemory:

  def __init__(self, global_config, username, llm=None) -> None:
    self.tom_config = tom_config

    memory_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(memory_path, exist_ok=True)

    self.memory_file = os.path.join(memory_path, "memory.md")
    self.username = username
    self.llm = llm

    # Initialize memory file if it doesn't exist
    self._init_memory_file()

    self.users = []
    for user in global_config['users']:
      self.users.append(user['username'])

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "list_stored_information",
          "description": "Function to retrieve all the information that the is stored in the memory. Use this when the user asks about information that you could find in your memory, searches for specific information, or wants to know what you remember about them. For example: 'Where did I park my car?', 'Where are my keys?', 'What is my PIN code?', etc. This returns the complete memory content for you to analyze and respond to the user's query.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "delete_stored_information",
          "description": "Function to remove specific information previously stored by the user. The function allows the user to specify which piece of remembered information to delete, ensuring that the stored context remains relevant and up-to-date.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information_text": {
                "type": "string",
                "description": "The text content of the information to delete. This should match exactly the information you want to remove from memory.",
              },
            },
            "required": ["information_text"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "store_information",
          "description": "Store personal information, life events, or important details shared by the user. Use this automatically when the user shares personal facts, daily activities, or situational information. DO NOT use for module requests (Nintendo Switch, calendar, weather, etc.) or technical questions. Examples: 'My PIN is 1234', 'Today I went to the doctor', 'I parked in spot B12', 'I prefer coffee without sugar'.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information": {
                "type": "string",
                "description": "The text of the information to remember",
              },
            },
            "required": ["information"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = """You have access to a personal memory system for storing and retrieving important user information.

     AUTOMATIC MEMORY STORAGE (NO CONFIRMATION REQUIRED):
     - When a user shares personal information or daily activities ("Today I went to the doctor", "My PIN is 1234", "I had lunch with Sarah"), automatically store it using store_information.
     - Simply acknowledge with "OK" or respond briefly. NEVER ask "Do you want me to remember this?"
     - The user sharing information implies they want it stored for future reference.

     INFORMATION TO AUTOMATICALLY STORE:
     - Personal facts: PIN codes, addresses, phone numbers, dates of birth, ages, names
     - Daily activities: "Today I went shopping", "I had a meeting", "I visited my mother"
     - Life events: "I got a new job", "I moved apartments", "I bought a car"
     - Situational details: where objects are located, parking spots with GPS coordinates
     - Preferences: food preferences, habits, usual schedules
     - Important personal information shared in conversation

     INFORMATION NOT TO STORE:
     - Requests for other modules: Nintendo Switch control, calendar management, weather queries, etc.
     - Technical questions or troubleshooting help
     - Commands or action requests ("Extend my Switch time", "Add to calendar", etc.)
     - General conversations without personal facts
     - Temporary information or casual chat

     DETECTING PERSONAL INFORMATION:
     Store information when the user:
     - States facts about themselves ("I am 25 years old", "My address is...")
     - Describes what they did ("Today I...", "Yesterday I...", "I went to...")
     - Shares preferences or habits ("I prefer...", "I usually...")
     - Mentions important details ("My password is...", "I left my keys...")

     GPS COORDINATES:
     When storing location information, save GPS coordinates with descriptive details.
     Format: `{"latitude": LATITUDE_VALUE, "longitude": LONGITUDE_VALUE}`
     
     For guidance requests, use: `[open: https://www.google.com/maps/dir/?api=1&origin=Current+Location&destination=LATITUDE,LONGITUDE&travelmode=walking]`

     FUNCTION USAGE:
     - Use store_information automatically for personal information (no confirmation)
     - Use list_stored_information when user asks what you remember
     - Use delete_stored_information when user asks to forget something
    """

    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "list_stored_information": {
        "function": functools.partial(self.remember_list)
      },
      "delete_stored_information": {
        "function": functools.partial(self.remember_delete)
      },
      "store_information": {
        "function": functools.partial(self.remember_add)
      },
    }

  def _init_memory_file(self):
    """Initialize the markdown memory file if it doesn't exist."""
    if not os.path.exists(self.memory_file):
      with open(self.memory_file, 'w', encoding='utf-8') as f:
        f.write("# Mémoire personnelle\n\n")
        f.write("Ce fichier contient toutes les informations que vous avez demandé de retenir.\n\n")


  def remember_add(self, information):
    """Add information to memory with current date as heading."""
    try:
      current_date = datetime.now().strftime("%Y-%m-%d")
      
      # Read existing content
      with open(self.memory_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      # Check if this information already exists to avoid duplicates
      if f"- {information}" in content:
        return {"status": "success", "message": "Information already exists in memory"}
      
      # Check if today's date section already exists
      date_header = f"# {current_date}"
      
      if date_header in content:
        # Add to existing date section
        lines = content.split('\n')
        insert_index = -1
        
        for i, line in enumerate(lines):
          if line.startswith(date_header):
            # Find the end of this date section (next # or end of file)
            for j in range(i + 1, len(lines)):
              if lines[j].startswith('# ') and j != i:
                insert_index = j
                break
            if insert_index == -1:
              insert_index = len(lines)
            break
        
        # Insert the new information
        new_entry = f"- {information}"
        lines.insert(insert_index, new_entry)
        content = '\n'.join(lines)
      else:
        # Create new date section
        new_section = f"\n\n{date_header}\n- {information}"
        content += new_section
      
      # Write back to file
      with open(self.memory_file, 'w', encoding='utf-8') as f:
        f.write(content)
      
      return {"status": "success", "message": "Added to memory"}
    
    except Exception as e:
      return {"status": "error", "message": f"Failed to add to memory: {str(e)}"}


  def remember_delete(self, information_text):
    """Delete information from memory by matching text content."""
    try:
      # Read existing content
      with open(self.memory_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      lines = content.split('\n')
      new_lines = []
      found = False
      
      for line in lines:
        # Check if this line contains the information to delete
        if information_text.lower() in line.lower() and line.strip().startswith('- '):
          found = True
          continue  # Skip this line (delete it)
        new_lines.append(line)
      
      if not found:
        return {"status": "error", "message": "Information not found in memory"}
      
      # Write back to file
      with open(self.memory_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
      
      return {"status": "success", "message": "Deleted from memory"}
    
    except Exception as e:
      return {"status": "error", "message": f"Failed to delete from memory: {str(e)}"}



  def remember_list(self):
    """Get all stored information from memory file for LLM to analyze."""
    try:
      # Read the memory file
      with open(self.memory_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      if not content.strip():
        return {"status": "success", "content": "", "message": "Aucune information n'est stockée en mémoire."}
      
      return {"status": "success", "content": content, "message": "Contenu de la mémoire récupéré avec succès."}
    
    except FileNotFoundError:
      return {"status": "success", "content": "", "message": "Aucun fichier de mémoire trouvé. Aucune information n'est stockée."}
    except Exception as e:
      return {"status": "error", "message": f"Erreur lors de la récupération des souvenirs : {str(e)}"}


  def extract_user_visible_content(self, conversation_history):
    """Extract only user-visible content from conversation history (input/output text only)."""
    user_visible_content = []
    
    try:
      for message in conversation_history:
        role = message.get('role', '')
        content = message.get('content', '')
        
        # Only include user and assistant messages (not system, function calls, etc.)
        if role in ['user', 'assistant'] and content:
          user_visible_content.append({
            'role': role,
            'content': content
          })
      
      return user_visible_content
    except Exception as e:
      tomlogger.error(f"Error extracting user-visible content: {str(e)}", self.username)
      return []


  def store_session_insight(self, information):
    """Function to store insights extracted from session analysis."""
    try:
      result = self.remember_add(information)
      tomlogger.info(f"Auto-stored from session analysis: {information}", self.username)
      return {"status": "success", "message": f"Stored: {information}"}
    except Exception as e:
      tomlogger.error(f"Error storing session insight: {str(e)}", self.username)
      return {"status": "error", "message": f"Failed to store: {str(e)}"}

  def analyze_session_with_llm(self, conversation_history):
    """Analyze conversation history with Mistral LLM to extract important information."""
    if not self.llm:
      tomlogger.warning("No LLM available for session analysis", self.username)
      return
    
    # Debug: check the type and attributes of self.llm
    tomlogger.debug(f"LLM object type: {type(self.llm)}", self.username)
    if hasattr(self.llm, 'callLLM'):
      tomlogger.debug("LLM object has callLLM method", self.username)
    else:
      tomlogger.error(f"LLM object does not have callLLM method. Available attributes: {dir(self.llm)}", self.username)
      return

    if not conversation_history:
      tomlogger.debug("Empty conversation history, nothing to analyze", self.username)
      return

    # Get current memory content to avoid duplicates
    current_memory = self.remember_list()
    memory_content = current_memory.get('content', '') if current_memory.get('status') == 'success' else ''

    # Extract only user-visible content
    user_content = self.extract_user_visible_content(conversation_history)
    
    if not user_content:
      tomlogger.debug("No user-visible content to analyze", self.username)
      return

    # Prepare conversation content for analysis
    conversation_text = ""
    for msg in user_content:
      role_label = "Utilisateur" if msg['role'] == 'user' else "Assistant"
      conversation_text += f"{role_label}: {msg['content']}\n\n"

    # LLM prompt for memory analysis with function calling
    context = f"""Tu es un assistant qui analyse les conversations pour identifier les informations personnelles importantes à retenir en mémoire.

    Analyse la conversation suivante et identifie UNIQUEMENT les informations personnelles partagées par l'utilisateur. Focus sur ce que l'utilisateur dit sur lui-même, ses activités, ou sa vie.

    IMPORTANT: Voici le contenu actuel de la mémoire. Ne stocke PAS d'informations qui sont déjà présentes :

    === CONTENU ACTUEL DE LA MÉMOIRE ===
    {memory_content}
    === FIN DU CONTENU DE LA MÉMOIRE ===

    INFORMATIONS À RETENIR (seulement si nouvelles) :
    - Faits personnels : "Mon code PIN est 1234", "J'habite à Paris", "J'ai 30 ans"
    - Activités quotidiennes : "Aujourd'hui j'ai été chez le médecin", "J'ai déjeuné avec Sarah"
    - Événements de vie : "J'ai eu un entretien", "J'ai acheté une nouvelle voiture"
    - Préférences durables : "Je préfère le café sans sucre", "Je prends le train de 8h15"
    - Informations situationnelles : "J'ai garé ma voiture en B12", "Mes clés sont sur la table"

    INFORMATIONS À NE JAMAIS RETENIR :
    - Demandes de gestion de modules (Nintendo Switch, calendrier, météo, transport, etc.)
    - Questions techniques ou dépannage
    - Commandes d'action ("Étends mon temps de jeu", "Ajoute au calendrier")
    - Conversations générales sans information personnelle
    - Requêtes de fonctionnalités ("Peux-tu faire...", "Comment...")
    - Discussions sur le système ou les modules

    RÈGLE IMPORTANTE : Si l'utilisateur demande quelque chose concernant un autre module (Nintendo Switch, calendrier, météo, transport, etc.), ou pose une question technique, NE STOCKE RIEN.

    Si tu identifies des informations personnelles pertinentes ET qu'elles ne sont pas déjà dans la mémoire, utilise la fonction store_session_insight pour chaque information importante.
    Si aucune information personnelle n'est identifiée ou si tout est déjà en mémoire, ne fais aucun appel de fonction.

    Conversation à analyser :
    """

    # Define the tool for storing session insights
    session_analysis_tools = [
      {
        "type": "function",
        "function": {
          "name": "store_session_insight",
          "description": "Stocke une information importante extraite de l'analyse de session",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information": {
                "type": "string",
                "description": "L'information importante à retenir en mémoire"
              }
            },
            "required": ["information"],
            "additionalProperties": False
          }
        }
      }
    ]

    llm_messages = [
      {"role": "system", "content": context},
      {"role": "user", "content": conversation_text}
    ]

    try:
      response = self.llm.callLLM(llm_messages, tools=session_analysis_tools, llm='mistral')
      
      if response and response.choices:
        choice = response.choices[0]
        
        # Check if there are tool calls (information to store)
        if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
          for tool_call in choice.message.tool_calls:
            if tool_call.function.name == "store_session_insight":
              try:
                import json
                args = json.loads(tool_call.function.arguments)
                information = args.get("information", "")
                if information:
                  self.store_session_insight(information)
              except Exception as e:
                tomlogger.error(f"Error processing tool call: {str(e)}", self.username)
        else:
          tomlogger.debug("No relevant information found in session for memory storage", self.username)
      
    except Exception as e:
      tomlogger.error(f"Error during LLM session analysis: {str(e)}", self.username)


  def analyze_session_async(self, conversation_history):
    """Analyze session in a separate thread to avoid blocking the reset call."""
    def analysis_worker():
      try:
        self.analyze_session_with_llm(conversation_history)
      except Exception as e:
        tomlogger.error(f"Error in async session analysis: {str(e)}", self.username)
    
    # Start analysis in background thread
    analysis_thread = threading.Thread(target=analysis_worker)
    analysis_thread.daemon = True
    analysis_thread.start()
    
    tomlogger.debug("Started async session analysis", self.username)
