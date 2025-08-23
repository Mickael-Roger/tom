"""
Tom LLM Library
Handles LLM interactions and MCP server communication for Tom Agent
"""

import json
import os
import time
import copy
from typing import Dict, Any, Optional, List
from litellm import completion
import tomlogger


class TomLLM:
    """
    Tom LLM handler class for managing LLM interactions
    """
    
    def __init__(self, config: Dict[str, Any], username: str):
        """
        Initialize TomLLM instance
        
        Args:
            config: Configuration dictionary from config.yml
            username: Username for logging context
        """
        self.config = config
        self.username = username
        self.global_config = config.get('global', {})
        
        # Initialize LLM configuration
        self.llms_dict = {}  # Dict: llm_name -> {api, env_var, models}
        self.default_llm = self.global_config.get('llm', 'openai')
        self.tts_llm = self.global_config.get('llm_tts', self.default_llm)
        
        # Rate limiting for Mistral (1.5 seconds between requests)
        self.mistral_last_request = 0
        
        # Setup LLMs from configuration
        self._setup_llms()
        
        tomlogger.info(f"TomLLM initialized with {len(self.llms_dict)} LLM providers", 
                      username, module_name="tomllm")
    
    def _setup_llms(self):
        """Setup LLM configurations from config"""
        llms_config = self.global_config.get('llms', {})
        
        tomlogger.info(f"Setting up LLMs: {list(llms_config.keys())}", 
                      self.username, module_name="tomllm")
        
        # Configure each LLM provider from configuration
        for llm_name, llm_config in llms_config.items():
            if not isinstance(llm_config, dict):
                tomlogger.warning(f"Invalid configuration for LLM '{llm_name}', skipping", 
                                self.username, module_name="tomllm")
                continue
                
            api_key = llm_config.get("api")
            if not api_key:
                tomlogger.warning(f"No API key found for LLM '{llm_name}', skipping", 
                                self.username, module_name="tomllm")
                continue
                
            # Get models configuration (required - 3 complexity levels)
            models = llm_config.get("models")
            if not models or len(models) != 3:
                tomlogger.warning(f"LLM '{llm_name}' must have exactly 3 models for complexity levels 0, 1, 2. Skipping.", 
                                self.username, module_name="tomllm")
                continue
                
            # Get environment variable name (required)
            env_var = llm_config.get("env_var")
            if not env_var:
                tomlogger.warning(f"No env_var specified for LLM '{llm_name}', skipping", 
                                self.username, module_name="tomllm")
                continue
            
            # Configure the LLM environment variable
            os.environ[env_var] = api_key
            
            # Store LLM configuration
            self.llms_dict[llm_name] = {
                "api": api_key,
                "env_var": env_var,
                "models": models
            }
            
            tomlogger.info(f"✅ Configured LLM '{llm_name}' with models: {models}", 
                          self.username, module_name="tomllm")
        
        # Validate default LLM configuration
        if self.default_llm not in self.llms_dict:
            available_llms = list(self.llms_dict.keys())
            tomlogger.error(f"Default LLM '{self.default_llm}' is not configured. Available LLMs: {available_llms}", 
                           self.username, module_name="tomllm")
            if available_llms:
                self.default_llm = available_llms[0]
                tomlogger.warning(f"Falling back to first available LLM: {self.default_llm}", 
                                self.username, module_name="tomllm")
            else:
                tomlogger.critical("No LLMs configured! Agent will not function properly.", 
                                 self.username, module_name="tomllm")
        
        # Validate TTS LLM configuration
        if self.tts_llm not in self.llms_dict:
            tomlogger.warning(f"TTS LLM '{self.tts_llm}' not configured, falling back to default LLM", 
                            self.username, module_name="tomllm")
            self.tts_llm = self.default_llm
        
        # Log final configuration
        tomlogger.info(f"✅ Default LLM: {self.default_llm}", self.username, module_name="tomllm")
        tomlogger.info(f"✅ TTS LLM: {self.tts_llm}", self.username, module_name="tomllm")

    def callLLM(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None, 
                complexity: int = 0, llm: Optional[str] = None) -> Any:
        """
        Call LLM with retry logic and error handling
        
        Args:
            messages: List of message objects for the conversation
            tools: Optional list of available tools/functions
            complexity: Complexity level (0, 1, or 2) to select appropriate model
            llm: Optional specific LLM provider name, defaults to configured default
            
        Returns:
            LLM response object or False on failure
        """
        
        # Use default LLM if none specified
        if llm is None:
            llm = self.default_llm
        
        # Validate LLM exists
        if llm not in self.llms_dict:
            tomlogger.error(f"LLM '{llm}' not configured. Available: {list(self.llms_dict.keys())}", 
                           self.username, module_name="tomllm")
            return False
        
        # Get model for complexity level
        model = self.llms_dict[llm]["models"][complexity]
        
        # Log LLM usage
        tomlogger.info(f"🤖 Using LLM: {llm} | Model: {model} | Complexity: {complexity}", 
                      self.username, module_name="tomllm")
        
        # Rate limiting for Mistral
        if llm == "mistral":
            current_time = time.time()
            time_since_last_request = current_time - self.mistral_last_request
            if time_since_last_request < 1.5:
                sleep_time = 1.5 - time_since_last_request
                tomlogger.debug(f"Rate limiting Mistral: sleeping {sleep_time:.2f}s", 
                               self.username, module_name="tomllm")
                time.sleep(sleep_time)
            self.mistral_last_request = time.time()
        
        # Debug logging - log full JSON content when in DEBUG mode
        if tomlogger.logger and tomlogger.logger.logger.level <= 10:  # DEBUG level = 10
            try:
                request_data = {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "complexity": complexity
                }
                tomlogger.debug(f"📤 Full LLM request JSON: {json.dumps(request_data, indent=2, ensure_ascii=False)}", 
                               self.username, module_name="tomllm")
            except Exception as json_error:
                tomlogger.debug(f"📤 Messages to send: {str(messages)} | Tools available: {str(tools)} (JSON serialization failed: {json_error})", 
                               self.username, module_name="tomllm")
        else:
            tomlogger.debug(f"📤 Messages to send: {str(messages)} | Tools available: {str(tools)}", 
                           self.username, module_name="tomllm")
        
        # Handle DeepSeek specific tool parameter cleanup
        if llm == "deepseek" and tools:
            for tool in tools:
                if "parameters" in tool["function"]:
                    if not tool["function"]["parameters"]:
                        del tool["function"]["parameters"]
        
        # Retry logic for 5xx errors (maximum 2 retries)
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Check if model is GPT-5 and its variants
                is_gpt5 = model.startswith("openai/gpt-5")
                
                if tools:
                    if is_gpt5:
                        # GPT-5 models use verbosity and reasoning_effort instead of temperature
                        response = completion(
                            model=model,
                            verbosity="low",
                            reasoning_effort="minimal",
                            messages=messages,
                            tools=tools,
                            tool_choice="auto",
                            allowed_openai_params=["reasoning_effort", "verbosity"],
                        )
                    else:
                        response = completion(
                            model=model,
                            temperature=0,
                            messages=messages,
                            tools=tools,
                            tool_choice="auto",
                        )
                else:
                    if is_gpt5:
                        # GPT-5 models use verbosity and reasoning_effort instead of temperature
                        response = completion(
                            model=model,
                            verbosity="low",
                            reasoning_effort="minimal",
                            messages=messages,
                            allowed_openai_params=["reasoning_effort", "verbosity"],
                        )
                    else:
                        response = completion(
                            model=model,
                            temperature=0,
                            messages=messages,
                        )
                
                # Debug logging - log full JSON content when in DEBUG mode
                if tomlogger.logger and tomlogger.logger.logger.level <= 10:  # DEBUG level = 10
                    try:
                        # Convert response to dict for JSON serialization
                        response_dict = response.model_dump() if hasattr(response, 'model_dump') else str(response)
                        tomlogger.debug(f"📥 Full LLM response JSON: {json.dumps(response_dict, indent=2, ensure_ascii=False)}", 
                                       self.username, module_name="tomllm")
                    except Exception as json_error:
                        tomlogger.debug(f"📥 LLM Response from {llm}: {str(response)} (JSON serialization failed: {json_error})", 
                                       self.username, module_name="tomllm")
                else:
                    tomlogger.debug(f"📥 LLM Response from {llm}: {str(response)}", 
                                   self.username, module_name="tomllm")
                
                # Validate response
                if not response:
                    tomlogger.warning(f"Empty response from {llm}", 
                                    self.username, module_name="tomllm")
                    return False
                
                if not response.choices:
                    tomlogger.warning(f"No choices in response from {llm}", 
                                    self.username, module_name="tomllm")
                    return False
                
                if response.choices[0].finish_reason not in ["tool_calls", "stop"]:
                    tomlogger.warning(f"Invalid finish_reason: {response.choices[0].finish_reason}", 
                                    self.username, module_name="tomllm")
                    return False
                
                return response
                
            except Exception as e:
                # Check if it's a 5xx error
                error_str = str(e)
                is_5xx_error = False
                
                # Check for common 5xx error patterns
                if any(code in error_str for code in ['500', '501', '502', '503', '504', '505', '507', '508', '510', '511']):
                    is_5xx_error = True
                elif 'Internal Server Error' in error_str or 'Bad Gateway' in error_str or 'Service Unavailable' in error_str:
                    is_5xx_error = True
                elif 'Gateway Timeout' in error_str or 'HTTP Version Not Supported' in error_str:
                    is_5xx_error = True
                
                if is_5xx_error and retry_count < max_retries:
                    retry_count += 1
                    tomlogger.warning(f"5xx error encountered, retrying ({retry_count}/{max_retries}): {error_str}", 
                                    self.username, module_name="tomllm")
                    time.sleep(0.3)
                    continue
                else:
                    # Re-raise the exception if it's not a 5xx error or we've exhausted retries
                    tomlogger.error(f"LLM call failed after {retry_count} retries: {error_str}", 
                                   self.username, module_name="tomllm")
                    raise e
        
        return False
    
    def set_response_context(self, client_type: str) -> str:
        """Set response context based on client type"""
        if client_type == 'tui':
            return "Your response will be displayed in a TUI terminal application. You should use markdown to format your answer for better readability. You can use titles, lists, bold text, etc."
        elif client_type == 'android':
            return "Your response will be displayed in an Android mobile application. You should use markdown to format your answer for better readability. Keep responses concise and mobile-friendly."
        else:  # web and pwa
            return "Your response will be displayed in a web browser or in a mobile app that supports markdown. You should use markdown to format your answer for better readability. You can use titles, lists, bold text, etc. Use simple text and line breaks for readability. Unless the user explicitly asks for it, you must never directly write URL or stuff like that. Instead, you must use the tag [open:PLACE URL HERE]"
    
    def triage_modules(self, user_request: str, position: Optional[Dict[str, float]], 
                      available_modules: List[Dict[str, str]], client_type: str) -> List[str]:
        """
        Triage modules needed to answer user request
        
        Args:
            user_request: User's request text
            position: Optional GPS position {'latitude': float, 'longitude': float}
            available_modules: List of {'name': str, 'description': str}
            client_type: 'web', 'tui', or 'android'
            
        Returns:
            List of module names needed to answer the request
        """
        
        # Create modules name list for enum
        modules_name_list = [module['name'] for module in available_modules]
        
        # If no modules available, return empty list immediately
        if not modules_name_list:
            tomlogger.info(f"💭 No modules available for triage, will use general knowledge", 
                          self.username, module_name="tomllm")
            return []
        
        # Build triage tools
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
                                "description": "Module name needed to answer the user's request",
                            },
                        },
                        "required": ["modules_name"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reset_conversation",
                    "description": "Reset the conversation history when the user greets you with expressions like 'Hello', 'Hi', 'Salut', 'Hi Tom', 'Salut Tom', or similar greetings that indicate a fresh start to the conversation",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            },
        ]
        
        # Build available tools description for prompt
        tooling = json.dumps(available_modules)
        
        # Create triage prompt
        prompt = f'''As an AI assistant, you have access to a wide range of functions, far more than your API allows. These functions are grouped into modules. A module is a logical grouping of functions for a specific theme.

For each new user request, you have access to the conversation history.

IMPORTANT: If the user greets you with expressions like "Hello", "Hi", "Salut", "Hi Tom", "Salut Tom", or similar greetings that indicate a fresh start to the conversation, you MUST call the 'reset_conversation' function first before processing any other request. This will clear the conversation history and provide a clean slate for the new conversation.

If you need a function that is not in your list of tools to respond to the user's request, you should call the 'modules_needed_to_answer_user_prompt' function with the necessary modules. You can call the 'modules_needed_to_answer_user_prompt' function as many times as needed.

It is very important that you do not invent module names—only the modules provided in the list exist.

Once you call the 'modules_needed_to_answer_user_prompt' function, the user's request will be sent back to you with the functions from the requested modules added to your tools. At that point, you can choose the appropriate function(s) to respond to the user's request.

```json
{tooling}
```
'''
        
        # Build conversation for triage
        triage_conversation = []
        
        # Add current time and GPS info if available
        from datetime import datetime
        gps = ""
        if position:
            gps = f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}."
        
        today = datetime.now().strftime("%A %d %B %Y %H:%M:%S")
        weeknumber = datetime.now().isocalendar().week
        today_msg = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}. {gps}\n\n"}
        triage_conversation.append(today_msg)
        
        # Add main system prompt
        triage_conversation.append({"role": "system", "content": prompt})
        
        # Add user request
        triage_conversation.append({"role": "user", "content": user_request})
        
        # Add response context
        response_context = self.set_response_context(client_type)
        triage_conversation.append({"role": "system", "content": response_context})
        
        tomlogger.info(f"🔍 Starting module triage for request: {user_request[:100]}...", 
                      self.username, module_name="tomllm")
        
        # Call LLM for triage (complexity 1 for good reasoning)
        response = self.callLLM(messages=triage_conversation, tools=tools, complexity=1)
        
        load_modules = []
        reset_requested = False
        
        if response and response.choices[0].finish_reason == "tool_calls":
            for tool_call in response.choices[0].message.tool_calls:
                if tool_call.function.name == "reset_conversation":
                    reset_requested = True
                    tomlogger.info(f"Reset conversation requested via greeting detection", 
                                 self.username, module_name="tomllm")
                elif tool_call.function.name == "modules_needed_to_answer_user_prompt":
                    try:
                        args = json.loads(tool_call.function.arguments)
                        mod_name = args.get('modules_name')
                        if mod_name in modules_name_list:
                            load_modules.append(mod_name)
                            tomlogger.info(f"📦 Triage selected module: {mod_name}", 
                                         self.username, module_name="tomllm")
                        else:
                            tomlogger.warning(f"Invalid module name returned by triage: {mod_name}", 
                                            self.username, module_name="tomllm")
                    except json.JSONDecodeError as e:
                        tomlogger.error(f"Failed to parse triage arguments: {tool_call.function.arguments}", 
                                      self.username, module_name="tomllm")
        
        # Handle reset request
        if reset_requested:
            tomlogger.info(f"🔄 Conversation reset requested", self.username, module_name="tomllm")
            return ["reset_performed"]  # Special indicator for reset
        
        # Remove duplicates and return
        load_modules = list(set(load_modules))
        
        if load_modules:
            tomlogger.info(f"✅ Triage completed - modules needed: {load_modules}", 
                          self.username, module_name="tomllm")
        else:
            tomlogger.info(f"💭 Triage completed - no specific modules needed, will use general knowledge", 
                          self.username, module_name="tomllm")
        
        return load_modules