"""
Tom LLM Library
Handles LLM interactions and MCP server communication for Tom Agent
"""

import json
import os
import time
import copy
import threading
import asyncio
import yaml
from datetime import datetime
from typing import Dict, Any, Optional, List
from litellm import completion
import tomlogger


class TomLLM:
    """
    Tom LLM handler class for managing LLM interactions
    """
    
    def __init__(self, config: Dict[str, Any], username: str, mcp_services: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize TomLLM instance
        
        Args:
            config: Configuration dictionary from config.yml
            username: Username for logging context
            mcp_services: Optional dictionary of MCP service configurations with their LLM and complexity settings
        """
        self.config = config
        self.username = username
        self.global_config = config.get('global', {})
        self.mcp_services = mcp_services or {}
        
        # Initialize LLM configuration
        self.llms_dict = {}  # Dict: llm_name -> {api, env_var, models}
        self.default_llm = self.global_config.get('llm', 'openai')
        self.tts_llm = self.global_config.get('llm_tts', self.default_llm)
        self.behavior_llm = self.global_config.get('llm_behavior', self.default_llm)
        self.triage_llm = self.global_config.get('llm_triage', self.default_llm)
        
        # Rate limiting for Mistral (1.5 seconds between requests)
        self.mistral_last_request = 0
        
        # History management - separate history for each client type
        self.history = {
            'web': [],      # Web browser client
            'android': [],  # Android mobile client  
            'tui': []       # Terminal UI client
        }
        
        # Debug logging configuration
        self.debug_llm = os.environ.get('TOM_DEBUG_LLM', '').lower() in ['true', '1']
        if self.debug_llm:
            self._setup_debug_logging()
        
        # Setup LLMs from configuration
        self._setup_llms()
        
        tomlogger.info(f"TomLLM initialized with {len(self.llms_dict)} LLM providers", 
                      username, module_name="tomllm")
        
        if self.debug_llm:
            tomlogger.info(f"LLM debug logging enabled for user {username}", 
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
        
        # Validate Triage LLM configuration
        if self.triage_llm not in self.llms_dict:
            tomlogger.warning(f"Triage LLM '{self.triage_llm}' not configured, falling back to default LLM", 
                            self.username, module_name="tomllm")
            self.triage_llm = self.default_llm
        
        # Log final configuration
        tomlogger.info(f"✅ Default LLM: {self.default_llm}", self.username, module_name="tomllm")
        tomlogger.info(f"✅ TTS LLM: {self.tts_llm}", self.username, module_name="tomllm")
        tomlogger.info(f"✅ Triage LLM: {self.triage_llm}", self.username, module_name="tomllm")

    def get_service_llm_config(self, service_name: str) -> tuple[str, int]:
        """
        Get LLM provider and complexity for a specific MCP service
        
        Args:
            service_name: Name of the MCP service
            
        Returns:
            Tuple of (llm_provider, complexity) - falls back to defaults if service config not found
        """
        if service_name in self.mcp_services:
            service_config = self.mcp_services[service_name]
            service_llm = service_config.get('llm', self.default_llm)
            service_complexity = service_config.get('complexity', 1)  # Default complexity 1
            
            # Validate that the specified LLM exists
            if service_llm not in self.llms_dict:
                tomlogger.warning(f"Service '{service_name}' specifies unknown LLM '{service_llm}', using default '{self.default_llm}'", 
                                self.username, module_name="tomllm")
                service_llm = self.default_llm
            
            # Validate complexity range
            if not isinstance(service_complexity, int) or service_complexity not in [0, 1, 2]:
                tomlogger.warning(f"Service '{service_name}' has invalid complexity '{service_complexity}', using default 1", 
                                self.username, module_name="tomllm")
                service_complexity = 1
            
            return service_llm, service_complexity
        
        # Default fallback
        return self.default_llm, 1

    def _setup_debug_logging(self):
        """Setup LLM debug logging infrastructure"""
        try:
            # Ensure user-specific logs directory exists
            self.debug_logs_dir = f"/data/logs/{self.username}"
            os.makedirs(self.debug_logs_dir, exist_ok=True)
            
            tomlogger.info(f"LLM debug logging directory: {self.debug_logs_dir}", 
                          self.username, module_name="tomllm")
                          
        except Exception as e:
            tomlogger.error(f"Failed to setup LLM debug logging: {e}", 
                          self.username, module_name="tomllm")
            self.debug_llm = False

    def _log_llm_debug(self, request_data: Dict[str, Any], response_data: Any, 
                      llm_provider: str, model: str, complexity: int):
        """
        Log LLM request and response to debug file
        
        Creates JSON log files in format: /data/logs/USERNAME/llm_debug_YYYY-MM-DD_HH-MM-SS.json
        Each file contains a single request/response pair with metadata
        
        Args:
            request_data: The request data sent to LLM
            response_data: The response received from LLM  
            llm_provider: Name of the LLM provider used
            model: Model name used
            complexity: Complexity level used
        """
        if not self.debug_llm:
            return
            
        try:
            # Generate unique filename with timestamp
            timestamp = datetime.now()
            log_filename = f"llm_debug_{timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.json"
            debug_log_path = os.path.join(self.debug_logs_dir, log_filename)
            
            # Prepare debug log entry
            debug_entry = {
                "timestamp": timestamp.isoformat(),
                "username": self.username,
                "llm_provider": llm_provider,
                "model": model,
                "complexity": complexity,
                "request": request_data,
                "response": response_data
            }
            
            # Write to unique file with pretty printing
            with open(debug_log_path, 'w', encoding='utf-8') as f:
                json.dump(debug_entry, f, indent=2, ensure_ascii=False, separators=(',', ': '))
            
            tomlogger.debug(f"Logged LLM debug entry to {debug_log_path}", 
                          self.username, module_name="tomllm")
                          
        except Exception as e:
            tomlogger.error(f"Failed to log LLM debug entry: {e}", 
                          self.username, module_name="tomllm")

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
        
        # Prepare request data for debug logging
        request_data = None
        if self.debug_llm:
            try:
                request_data = {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "complexity": complexity
                }
            except Exception as json_error:
                tomlogger.debug(f"Failed to prepare request data for debug logging: {json_error}", 
                               self.username, module_name="tomllm")

        # Debug logging - log full JSON content when in DEBUG mode
        if tomlogger.logger and tomlogger.logger.logger.level <= 10:  # DEBUG level = 10
            try:
                if not request_data:
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
                
                # Prepare response data for debug logging
                response_data = None
                if self.debug_llm:
                    try:
                        response_data = response.model_dump() if hasattr(response, 'model_dump') else str(response)
                    except Exception as json_error:
                        tomlogger.debug(f"Failed to prepare response data for debug logging: {json_error}", 
                                       self.username, module_name="tomllm")
                        response_data = {"error": "Failed to serialize response", "raw_response": str(response)}

                # Debug logging - log full JSON content when in DEBUG mode
                if tomlogger.logger and tomlogger.logger.logger.level <= 10:  # DEBUG level = 10
                    try:
                        if not response_data:
                            response_data = response.model_dump() if hasattr(response, 'model_dump') else str(response)
                        tomlogger.debug(f"📥 Full LLM response JSON: {json.dumps(response_data, indent=2, ensure_ascii=False)}", 
                                       self.username, module_name="tomllm")
                    except Exception as json_error:
                        tomlogger.debug(f"📥 LLM Response from {llm}: {str(response)} (JSON serialization failed: {json_error})", 
                                       self.username, module_name="tomllm")
                else:
                    tomlogger.debug(f"📥 LLM Response from {llm}: {str(response)}", 
                                   self.username, module_name="tomllm")
                
                # Log to debug file if enabled
                if self.debug_llm and request_data and response_data:
                    self._log_llm_debug(request_data, response_data, llm, model, complexity)
                
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
        else:  # android, web and pwa
            return "Your response will be displayed in a web browser or in a mobile app that supports markdown. You should use markdown to format your answer for better readability. You can use titles, lists, bold text, etc. Use simple text and line breaks for readability. Unless the user explicitly asks for it, you must never directly write URL or stuff like that. Instead, you must use the tag [open:PLACE URL HERE]"
    
    async def _retrieve_memory_async(self, user_request: str, mcp_client) -> Optional[Dict[str, Any]]:
        """Retrieve relevant memories asynchronously for the user request"""
        if not mcp_client:
            return None
            
        # Check if memory service is available
        memory_connection = mcp_client.get_mcp_connection("memory")
        if not memory_connection or not memory_connection.get("tools"):
            tomlogger.debug(f"Memory service not available for retrieval", self.username, module_name="tomllm")
            return None
        
        try:
            from mcp.client.streamable_http import streamablehttp_client
            from mcp import ClientSession
            
            async with streamablehttp_client(memory_connection['url']) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    # Search for relevant memories using the user request
                    result = await session.call_tool(
                        "search_memories",
                        {
                            "query": user_request,
                            "limit": 5  # Limit to 5 most relevant memories
                        }
                    )
                    
                    tomlogger.debug(f"Memory search result: {result}", self.username, module_name="tomllm")
                    
                    # Extract content from MCP result
                    if result and hasattr(result, 'content') and result.content:
                        content_items = []
                        for content in result.content:
                            if hasattr(content, 'text'):
                                content_items.append(content.text)
                            elif hasattr(content, 'data'):
                                content_items.append(str(content.data))
                            else:
                                content_items.append(str(content))
                        
                        result_text = '\n'.join(content_items) if content_items else None
                        
                        if result_text:
                            try:
                                # Parse the JSON result from memory service
                                memory_data = json.loads(result_text)
                                if memory_data.get("status") == "success" and memory_data.get("results"):
                                    tomlogger.info(f"🧠 Retrieved {len(memory_data['results'])} relevant memories", self.username, module_name="tomllm")
                                    return memory_data
                                else:
                                    tomlogger.debug(f"No relevant memories found", self.username, module_name="tomllm")
                                    return None
                            except json.JSONDecodeError:
                                tomlogger.warning(f"Failed to parse memory search result", self.username, module_name="tomllm")
                                return None
                    
                    return None
        
        except Exception as e:
            tomlogger.debug(f"Error retrieving memories: {e}", self.username, module_name="tomllm")
            return None
    
    def triage_modules(self, user_request: str, position: Optional[Dict[str, float]], 
                      available_modules: List[Dict[str, str]], client_type: str, personal_context: str = "", 
                      mcp_client=None) -> List[str]:
        """
        Triage modules needed to answer user request
        
        Args:
            user_request: User's request text
            position: Optional GPS position {'latitude': float, 'longitude': float}
            available_modules: List of {'name': str, 'description': str}
            client_type: 'web', 'tui', or 'android'
            personal_context: User's personal context from configuration
            mcp_client: Optional MCPClient instance for memory retrieval
            
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
        
        # Create textual triage instructions (first system prompt)
        triage_instructions = '''As an AI assistant, you have access to a wide range of functions, far more than your API allows. These functions are grouped into modules. A module is a logical grouping of functions for a specific theme.

For each new user request, you have access to the conversation history.

IMPORTANT: If the user greets you with expressions like "Hello", "Hi", "Salut", "Hi Tom", "Salut Tom", or similar greetings that indicate a fresh start to the conversation, you MUST call the 'reset_conversation' function first before processing any other request. This will clear the conversation history and provide a clean slate for the new conversation.

If you need a function that is not in your list of tools to respond to the user's request, you should call the 'modules_needed_to_answer_user_prompt' function with the necessary modules. You can call the 'modules_needed_to_answer_user_prompt' function as many times as needed.

It is very important that you do not invent module names—only the modules provided in the list exist.

Once you call the 'modules_needed_to_answer_user_prompt' function, the user's request will be sent back to you with the functions from the requested modules added to your tools. At that point, you can choose the appropriate function(s) to respond to the user's request.'''
        
        # Create JSON modules prompt (second system prompt) - wrap in object structure
        modules_data = {
            "available_modules": available_modules
        }
        modules_json = json.dumps(modules_data, ensure_ascii=False, separators=(',', ':'))
        
        # Build conversation for triage with history
        from datetime import datetime
        gps = ""
        if position:
            gps = f"My actual GPS position is \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}."
        
        today = datetime.now().strftime("%A %d %B %Y %H:%M:%S")
        weeknumber = datetime.now().isocalendar().week
        
        # Retrieve relevant memories in parallel with triage preparation
        memory_data = None
        if mcp_client:
            try:
                # Run memory retrieval asynchronously
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                memory_data = loop.run_until_complete(self._retrieve_memory_async(user_request, mcp_client))
            except Exception as e:
                tomlogger.debug(f"Error during memory retrieval: {e}", self.username, module_name="tomllm")
                memory_data = None
        
        # Build current triage conversation - user request + optional memory context
        current_triage_conversation = [
            {"role": "user", "content": user_request}
        ]
        
        # Add memory information as system message if available
        if memory_data and memory_data.get("results"):
            memory_info = {
                "description": "Relevant information retrieved from memory that may help answer the user's request",
                "source": "memory_system",
                "retrieved_memories": memory_data["results"],
                "total_memories_found": memory_data.get("count", len(memory_data["results"]))
            }
            
            memory_message = {
                "role": "system", 
                "content": json.dumps(memory_info, ensure_ascii=False, separators=(',', ':'))
            }
            
            # Insert memory message after user request
            current_triage_conversation.append(memory_message)
            
            tomlogger.info(f"🧠 Added {len(memory_data['results'])} memories to triage context", self.username, module_name="tomllm")
        
        # For triage, use JSON format with separate triage system messages
        triage_conversation = self.get_conversation_with_history(
            client_type=client_type, 
            current_conversation=current_triage_conversation,
            # New JSON format parameters for triage
            tom_persona="AI assistant specialized in module triage and tool selection",
            today=today,
            weeknumber=weeknumber,
            gps=gps,
            personal_context=personal_context,
            use_json_format=True,
            triage_instructions=triage_instructions,
            triage_modules_json=modules_json,
            triage_mode=True
        )
        
        tomlogger.info(f"🔍 Starting module triage for request: {user_request[:100]}...", 
                      self.username, module_name="tomllm")
        
        # Call LLM for triage (complexity 0 for speed, using triage LLM)
        response = self.callLLM(messages=triage_conversation, tools=tools, complexity=0, llm=self.triage_llm)
        
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
        
        # Log triage request to YAML file
        self._log_triage_request(user_request, load_modules)
        
        # Log triage request to YAML file
        self._log_triage_request(user_request, load_modules)
        
        return load_modules
    
    def _log_triage_request(self, user_request: str, loaded_modules: List[str]):
        """
        Log triage request to YAML file in /data/logs/USERNAME/
        
        Args:
            user_request: The user's request text
            loaded_modules: List of module names that were loaded
        """
        try:
            # Get username from environment variable
            username = os.environ.get('TOM_USERNAME', 'unknown')
            
            # Ensure user-specific logs directory exists
            logs_dir = f"/data/logs/{username}"
            os.makedirs(logs_dir, exist_ok=True)
            
            # Generate log file path with current date
            log_filename = f"triage_{datetime.now().strftime('%Y-%m-%d')}.yml"
            log_filepath = os.path.join(logs_dir, log_filename)
            
            # Prepare log entry
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "username": self.username,
                "prompt": user_request,
                "loaded_modules": loaded_modules
            }
            
            # Load existing entries or create empty list
            existing_entries = []
            if os.path.exists(log_filepath):
                try:
                    with open(log_filepath, 'r', encoding='utf-8') as f:
                        existing_entries = yaml.safe_load(f) or []
                except Exception as e:
                    tomlogger.debug(f"Could not load existing triage log file: {e}", self.username, module_name="tomllm")
                    existing_entries = []
            
            # Append new entry
            existing_entries.append(log_entry)
            
            # Write back to file
            with open(log_filepath, 'w', encoding='utf-8') as f:
                yaml.dump(existing_entries, f, default_flow_style=False, allow_unicode=True, 
                         default_style=None, sort_keys=False)
            
            tomlogger.debug(f"Logged triage request to {log_filepath}", self.username, module_name="tomllm")
            
        except Exception as e:
            tomlogger.warning(f"Failed to log triage request: {e}", self.username, module_name="tomllm")
    
    def triage_modules_sync(self, user_request: str, position: Optional[Dict[str, float]], 
                           available_modules: List[Dict[str, str]], client_type: str, personal_context: str = "", 
                           mcp_client=None) -> List[str]:
        """Synchronous wrapper for triage_modules for backward compatibility"""
        return self.triage_modules(user_request, position, available_modules, client_type, personal_context, mcp_client)
    
    async def execute_request_with_tools(self, conversation: List[Dict[str, str]], tools: List[Dict], 
                                        complexity: int = 1, max_iterations: int = 10, mcp_client=None, 
                                        client_type: str = 'web', track_history: bool = True, selected_modules: List[str] = None) -> Any:
        """
        Execute request with tools, handling multiple iterations of tool calls
        
        Args:
            conversation: List of conversation messages
            tools: List of available tools in OpenAI format
            complexity: LLM complexity level to use
            max_iterations: Maximum number of tool call iterations
            mcp_client: MCPClient instance for executing MCP tools
            client_type: Client type for history tracking ('web', 'android', 'tui')
            track_history: Whether to track conversation in history
            selected_modules: List of selected module names for behavior prompts
            
        Returns:
            Final response content or error dict
        """
        
        # Apply behavior prompts if behavior service is available
        enhanced_conversation = conversation
        if mcp_client and selected_modules:
            try:
                enhanced_conversation = await self._apply_behavior_prompts(conversation, selected_modules, mcp_client)
                tomlogger.debug(f"Applied behavior prompts for modules: {selected_modules}", self.username, module_name="tomllm")
            except Exception as e:
                tomlogger.debug(f"Failed to apply behavior prompts: {e}", self.username, module_name="tomllm")
                enhanced_conversation = conversation
        
        working_conversation = copy.deepcopy(enhanced_conversation)
        iteration = 0
        
        # Extract user request from conversation for history tracking
        if track_history:
            # Find the last user message in the conversation to add to history
            user_messages = [msg for msg in conversation if msg.get('role') == 'user']
            if user_messages:
                last_user_message = user_messages[-1]
                self.add_user_request(client_type, last_user_message.get('content', ''))
        
        # Determine complexity based on selected modules and their configurations
        if selected_modules:
            max_service_complexity = complexity  # Use provided complexity as minimum
            service_llm_override = None
            
            # Check if all selected services use the same LLM and get max complexity
            service_llms = set()
            for module_name in selected_modules:
                service_llm, service_complexity = self.get_service_llm_config(module_name)
                service_llms.add(service_llm)
                max_service_complexity = max(max_service_complexity, service_complexity)
            
            # If all services use the same LLM (and it's different from default), use that LLM
            if len(service_llms) == 1 and service_llms != {self.default_llm}:
                service_llm_override = list(service_llms)[0]
                tomlogger.info(f"🎯 All selected modules use LLM '{service_llm_override}', using for execution", 
                              self.username, module_name="tomllm")
            elif len(service_llms) > 1:
                tomlogger.info(f"📊 Selected modules use different LLMs: {service_llms}, using default '{self.default_llm}'", 
                              self.username, module_name="tomllm")
            
            # Use the calculated complexity
            complexity = max_service_complexity
            tomlogger.info(f"📈 Using complexity level {complexity} based on selected modules configuration", 
                          self.username, module_name="tomllm")
        
        tomlogger.info(f"🚀 Starting tool execution with {len(tools)} tools, max {max_iterations} iterations", 
                      self.username, module_name="tomllm")
        
        while iteration < max_iterations:
            iteration += 1
            tomlogger.debug(f"🔄 Tool execution iteration {iteration}/{max_iterations}", 
                           self.username, module_name="tomllm")
            
            # For each iteration, use the conversation as-is (tools will drive the conversation)
            current_messages = working_conversation.copy()
            
            # Use service-specific LLM if available
            llm_to_use = service_llm_override if 'service_llm_override' in locals() and service_llm_override else None
            response = self.callLLM(messages=current_messages, tools=tools, complexity=complexity, llm=llm_to_use)
            
            if not response:
                tomlogger.error(f"LLM call failed during tool execution iteration {iteration}", 
                               self.username, module_name="tomllm")
                return {
                    "status": "ERROR",
                    "message": f"LLM call failed at iteration {iteration}"
                }
            
            if response.choices[0].finish_reason == "stop":
                # Final response detected - add formatting message and make final call
                response_content = response.choices[0].message.content
                
                # If we have response content from a direct stop, return it
                if response_content and response_content.strip():
                    # Track final assistant response in history
                    if track_history:
                        self.add_assistant_response(client_type, response_content)
                    
                    tomlogger.info(f"✅ Tool execution completed after {iteration} iterations", 
                                  self.username, module_name="tomllm")
                    return {
                        "status": "OK",
                        "response": response_content,
                        "iterations": iteration
                    }
                
                # Formatting is now handled at conversation build time, not here
                # Track assistant response in history if we got content
                if track_history and response_content:
                    self.add_assistant_response(client_type, response_content)
                
                # Fallback if no content
                tomlogger.info(f"✅ Tool execution completed after {iteration} iterations", 
                              self.username, module_name="tomllm")
                return {
                    "status": "OK",
                    "response": response_content or "",
                    "iterations": iteration
                }
                
            elif response.choices[0].finish_reason == "tool_calls":
                # Add assistant message to conversation
                assistant_message = response.choices[0].message.to_dict()
                working_conversation.append(assistant_message)
                
                # Track assistant tool calls in history
                if track_history:
                    self.add_assistant_tool_calls(client_type, response.choices[0].message.tool_calls)
                
                # Execute each tool call
                for tool_call in response.choices[0].message.tool_calls:
                    function_name = tool_call.function.name
                    
                    try:
                        function_params = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        tomlogger.error(f"Failed to parse tool arguments for {function_name}: {tool_call.function.arguments}", 
                                       self.username, module_name="tomllm")
                        # Add error result
                        error_result = {
                            "error": f"Invalid tool arguments: {str(e)}"
                        }
                        working_conversation.append({
                            "role": "tool", 
                            "content": json.dumps(error_result), 
                            "tool_call_id": tool_call.id
                        })
                        continue
                    
                    tomlogger.info(f"🔧 Executing tool: {function_name} with params: {function_params}", 
                                  self.username, module_name="tomllm")
                    
                    # Execute actual MCP tool call
                    if mcp_client:
                        tool_result = await self._execute_mcp_tool(
                            mcp_client, function_name, function_params
                        )
                    else:
                        # Fallback if no MCP client provided
                        tomlogger.warning(f"No MCP client provided for tool {function_name}, simulating", 
                                        self.username, module_name="tomllm")
                        tool_result = {
                            "error": f"No MCP client available to execute {function_name}",
                            "function": function_name,
                            "params": function_params
                        }
                    
                    # Add tool result to conversation
                    tool_result_content = json.dumps(tool_result)
                    working_conversation.append({
                        "role": "tool",
                        "content": tool_result_content,
                        "tool_call_id": tool_call.id
                    })
                    
                    # Track tool result in history
                    if track_history:
                        self.add_tool_result(client_type, tool_call.id, tool_result_content)
                    
                    tomlogger.debug(f"📥 Tool {function_name} result: {json.dumps(tool_result)}", 
                                   self.username, module_name="tomllm")
            else:
                tomlogger.warning(f"Unexpected finish_reason: {response.choices[0].finish_reason}", 
                                 self.username, module_name="tomllm")
                return {
                    "status": "ERROR",
                    "message": f"Unexpected response finish_reason: {response.choices[0].finish_reason}"
                }
        
        # Max iterations reached
        tomlogger.warning(f"Tool execution reached max iterations ({max_iterations})", 
                         self.username, module_name="tomllm")
        return {
            "status": "ERROR", 
            "message": f"Tool execution reached maximum iterations ({max_iterations})",
            "iterations": max_iterations
        }
    
    async def _execute_mcp_tool(self, mcp_client, function_name: str, function_params: dict) -> dict:
        """
        Execute a specific MCP tool
        
        Args:
            mcp_client: MCPClient instance
            function_name: Name of the function to call
            function_params: Parameters for the function
            
        Returns:
            Dict with execution result
        """
        try:
            # Find which service contains this tool
            service_name = None
            mcp_connections = mcp_client.get_mcp_connections()
            
            for svc_name, connection_info in mcp_connections.items():
                tools = connection_info.get('tools', [])
                for tool in tools:
                    if tool['function']['name'] == function_name:
                        service_name = svc_name
                        break
                if service_name:
                    break
            
            if not service_name:
                tomlogger.error(f"Tool '{function_name}' not found in any MCP service", 
                               self.username, module_name="tomllm")
                return {
                    "error": f"Tool '{function_name}' not found in any MCP service"
                }
            
            tomlogger.debug(f"Found tool '{function_name}' in service '{service_name}'", 
                           self.username, module_name="tomllm")
            
            # Create MCP session for this service
            connection_info = mcp_connections[service_name]
            url = connection_info.get('url')
            headers = connection_info.get('headers', {})
            
            if not url:
                tomlogger.error(f"No URL found for service '{service_name}'", 
                               self.username, module_name="tomllm")
                return {
                    "error": f"No URL configured for service '{service_name}'"
                }
            
            # Import required MCP modules
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
            import asyncio
            
            tomlogger.debug(f"Creating MCP session for '{service_name}' at {url}", 
                           self.username, module_name="tomllm")
            
            # Create session and execute tool
            async with streamablehttp_client(url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    tomlogger.debug(f"Calling MCP tool '{function_name}' with params: {function_params}", 
                                   self.username, module_name="tomllm")
                    
                    # Call the tool
                    result = await session.call_tool(function_name, function_params)
                    
                    tomlogger.debug(f"MCP tool '{function_name}' returned: {result}", 
                                   self.username, module_name="tomllm")
                    
                    # Convert MCP result to standard format
                    if result and hasattr(result, 'content') and result.content:
                        # Extract content from MCP result
                        content_items = []
                        for content in result.content:
                            if hasattr(content, 'text'):
                                content_items.append(content.text)
                            elif hasattr(content, 'data'):
                                content_items.append(str(content.data))
                            else:
                                content_items.append(str(content))
                        
                        # Join all content items
                        result_text = '\n'.join(content_items) if content_items else str(result)
                        
                        return {
                            "status": "success",
                            "result": result_text,
                            "function": function_name,
                            "service": service_name
                        }
                    else:
                        tomlogger.warning(f"Empty or invalid result from MCP tool '{function_name}'", 
                                        self.username, module_name="tomllm")
                        return {
                            "status": "success",
                            "result": "Tool executed successfully but returned no content",
                            "function": function_name,
                            "service": service_name
                        }
        
        except Exception as e:
            tomlogger.error(f"Error executing MCP tool '{function_name}': {str(e)}", 
                           self.username, module_name="tomllm")
            import traceback
            tomlogger.debug(f"MCP tool execution error traceback: {traceback.format_exc()}", 
                           self.username, module_name="tomllm")
            return {
                "error": f"Failed to execute MCP tool '{function_name}': {str(e)}",
                "function": function_name
            }
    
    def add_to_history(self, client_type: str, message: Dict[str, Any]):
        """
        Add a message to conversation history for specific client type
        
        Args:
            client_type: 'web', 'android', or 'tui'
            message: Message dict to add to history
        """
        if client_type not in self.history:
            tomlogger.warning(f"Invalid client type '{client_type}', defaulting to 'web'", 
                            self.username, module_name="tomllm")
            client_type = 'web'
        
        self.history[client_type].append(message)
        
        # Debug logging - show what message was added in DEBUG mode
        if tomlogger.logger and tomlogger.logger.logger.level <= 10:  # DEBUG level = 10
            try:
                tomlogger.debug(f"📝 Added to {client_type} history ({len(self.history[client_type])} total): {json.dumps(message, indent=2, ensure_ascii=False)}", 
                               self.username, module_name="tomllm")
            except Exception as json_error:
                tomlogger.debug(f"📝 Added to {client_type} history ({len(self.history[client_type])} total): {str(message)} (JSON serialization failed: {json_error})", 
                               self.username, module_name="tomllm")
        else:
            tomlogger.debug(f"Added message to {client_type} history (now {len(self.history[client_type])} messages)", 
                           self.username, module_name="tomllm")
    
    def add_user_request(self, client_type: str, user_content: str):
        """
        Add user request to history
        
        Args:
            client_type: 'web', 'android', or 'tui'
            user_content: User's request text
        """
        user_message = {
            "role": "user",
            "content": user_content
        }
        self.add_to_history(client_type, user_message)
        tomlogger.debug(f"Added user request to {client_type} history: {user_content[:50]}...", 
                       self.username, module_name="tomllm")
    
    def add_assistant_tool_calls(self, client_type: str, tool_calls: List[Any]):
        """
        Add assistant tool calls to history
        
        Args:
            client_type: 'web', 'android', or 'tui'
            tool_calls: List of tool call objects from LLM response
        """
        assistant_message = {
            "role": "assistant", 
            "content": None,
            "tool_calls": [tool_call.to_dict() if hasattr(tool_call, 'to_dict') else tool_call for tool_call in tool_calls]
        }
        self.add_to_history(client_type, assistant_message)
        tomlogger.debug(f"Added {len(tool_calls)} tool calls to {client_type} history", 
                       self.username, module_name="tomllm")
    
    def add_tool_result(self, client_type: str, tool_call_id: str, result_content: str):
        """
        Add tool execution result to history
        
        Args:
            client_type: 'web', 'android', or 'tui'
            tool_call_id: ID of the tool call this result corresponds to
            result_content: JSON string result from tool execution
        """
        tool_message = {
            "role": "tool",
            "content": result_content,
            "tool_call_id": tool_call_id
        }
        self.add_to_history(client_type, tool_message)
        tomlogger.debug(f"Added tool result to {client_type} history for call {tool_call_id}", 
                       self.username, module_name="tomllm")
    
    def add_assistant_response(self, client_type: str, response_content: str):
        """
        Add final assistant response to history
        
        Args:
            client_type: 'web', 'android', or 'tui'
            response_content: Final response text from assistant
        """
        response_message = {
            "role": "assistant",
            "content": response_content
        }
        self.add_to_history(client_type, response_message)
        tomlogger.debug(f"Added assistant response to {client_type} history: {response_content[:50]}...", 
                       self.username, module_name="tomllm")
    
    def _create_json_system_message(self, tom_persona: str, today: str, weeknumber: int, gps: str, 
                                   personal_context: str, client_type: str, 
                                   available_tools: bool = False) -> Dict[str, Any]:
        """
        Create a single JSON-formatted system message that replaces temporal, tom prompt, personal context messages
        
        Args:
            tom_persona: Tom's persona description for the specific context
            today: Current date/time string
            weeknumber: Current week number
            gps: GPS position string (empty if not available)
            personal_context: User's personal context from config
            client_type: 'web', 'android', or 'tui'
            available_tools: Whether tools are available for this conversation
            
        Returns:
            JSON-formatted system message dict
        """
        import json
        
        # Build GPS position object
        gps_position = None
        if gps and "latitude:" in gps and "longitude:" in gps:
            try:
                # Extract GPS coordinates from the GPS string
                lines = gps.strip().split('\n')
                lat_line = next((line for line in lines if 'latitude:' in line), '')
                lon_line = next((line for line in lines if 'longitude:' in line), '')
                
                if lat_line and lon_line:
                    latitude = float(lat_line.split('latitude:')[1].strip().rstrip('.'))
                    longitude = float(lon_line.split('longitude:')[1].strip().rstrip('.'))
                    gps_position = {
                        "latitude": latitude,
                        "longitude": longitude
                    }
            except (ValueError, IndexError):
                # If parsing fails, leave gps_position as None
                pass
        
        # Build JSON content
        json_content = {
            "description": "Define the assistant's role, style, rules, and available tools.",
            "persona": {
                "name": "Tom",
                "role": tom_persona,
                "language_policy": "Always respond in the same language as the user (FR/EN); use informal 'tu' if the user writes in French.",
                "style": "clear, structured, markdown-friendly"
            },
            "system_context": {
                "current_date_time": today,
                "week_number": weeknumber
            },
            "formatting": {
                "markdown": True,
                "language": "auto-detect to match user input",
                "no_urls_direct": True if client_type in ['web', 'android'] else False
            }
        }
        
        # Add GPS position if available
        if gps_position:
            json_content["system_context"]["gps_position"] = gps_position
        
        # Add user profile if available - convert from text/YAML to JSON
        if personal_context and personal_context.strip():
            json_content["user_profile"] = self._parse_user_profile_to_json(personal_context.strip())
        
        # Add specific formatting rules based on client type
        if client_type == 'tui':
            json_content["formatting"]["context"] = "Response will be displayed in a TUI terminal application. Use markdown for better readability: titles, lists, bold text, etc."
        else:
            json_content["formatting"]["context"] = "Response will be displayed in a web browser or mobile app. Use markdown for better readability. Use [open:URL] tag instead of direct URLs unless explicitly asked."
        
        return {
            "role": "system",
            "content": json.dumps(json_content, ensure_ascii=False, separators=(',', ':'))
        }

    def _parse_user_profile_to_json(self, personal_context: str):
        """
        Parse user profile from text or YAML format to JSON-compatible structure
        
        Args:
            personal_context: Raw personal context from config.yml
            
        Returns:
            JSON-compatible object (string, dict, or list)
        """
        import yaml
        
        # First, try to parse as YAML to see if it's structured
        try:
            # Check if the content looks like structured YAML (contains colons, dashes, etc.)
            if any(indicator in personal_context for indicator in [':', '-', '\n  ', '\n-']):
                # Attempt to parse as YAML
                parsed_yaml = yaml.safe_load(personal_context)
                
                # If parsing succeeded and returned a complex structure, use it
                if parsed_yaml is not None and not isinstance(parsed_yaml, str):
                    tomlogger.debug(f"Parsed user profile as YAML structure", self.username, module_name="tomllm")
                    return parsed_yaml
                else:
                    # YAML parsing returned a simple string, treat as plain text
                    tomlogger.debug(f"YAML parsing returned simple string, treating as plain text", self.username, module_name="tomllm")
                    return personal_context.strip()
            else:
                # Content doesn't look like YAML, treat as plain text
                tomlogger.debug(f"User profile treated as plain text", self.username, module_name="tomllm")
                return personal_context.strip()
                
        except yaml.YAMLError as e:
            # YAML parsing failed, fallback to plain text
            tomlogger.debug(f"YAML parsing failed, fallback to plain text: {e}", self.username, module_name="tomllm")
            return personal_context.strip()
        except Exception as e:
            # Any other error, fallback to plain text
            tomlogger.debug(f"Error parsing user profile, fallback to plain text: {e}", self.username, module_name="tomllm")
            return personal_context.strip()

    def get_conversation_with_history(self, client_type: str, current_conversation: List[Dict[str, Any]], 
                                      temporal_message: Optional[Dict[str, Any]] = None,
                                      tom_prompt: Optional[Dict[str, Any]] = None,
                                      personal_context_message: Optional[Dict[str, Any]] = None,
                                      formatting_message: Optional[Dict[str, Any]] = None,
                                      # New JSON-based parameters
                                      tom_persona: Optional[str] = None,
                                      today: Optional[str] = None,
                                      weeknumber: Optional[int] = None,
                                      gps: Optional[str] = None,
                                      personal_context: Optional[str] = None,
                                      use_json_format: bool = True,
                                      triage_instructions: Optional[str] = None,
                                      triage_modules_json: Optional[str] = None,
                                      triage_mode: bool = False) -> List[Dict[str, Any]]:
        """
        Build conversation with history prepended in correct order
        
        Args:
            client_type: 'web', 'android', or 'tui'
            current_conversation: Current conversation messages (user request, response formatting, etc)
            temporal_message: DEPRECATED - Optional temporal message (date/GPS) that goes first but never in history
            tom_prompt: DEPRECATED - Optional Tom prompt that goes second but never in history
            personal_context_message: DEPRECATED - Optional personal context message that goes third but never in history
            formatting_message: DEPRECATED - Optional formatting message that goes fourth but never in history
            
            # New JSON-based parameters:
            tom_persona: Tom's persona description for the specific context
            today: Current date/time string
            weeknumber: Current week number  
            gps: GPS position string (empty if not available)
            personal_context: User's personal context from config
            use_json_format: Whether to use new JSON format (default True) or legacy format
            triage_instructions: Textual triage instructions (used only in triage_mode)
            triage_modules_json: JSON string containing available modules (used only in triage_mode)
            triage_mode: Whether to build conversation for triage (separates system prompts)
            
        Returns:
            Triage mode: global_system → history → triage_system → helper_systems → user_message
            Normal mode: global_system → history → helper_systems → user_messages
            Legacy mode: temporal → tom_prompt → personal_context → formatting → history → current messages
        """
        if client_type not in self.history:
            tomlogger.warning(f"Invalid client type '{client_type}', using empty history", 
                            self.username, module_name="tomllm")
            client_history = []
        else:
            client_history = self.history[client_type]
        
        # Debug logging - show history content in DEBUG mode
        if client_history and tomlogger.logger and tomlogger.logger.logger.level <= 10:  # DEBUG level = 10
            try:
                tomlogger.debug(f"📚 History for {client_type} ({len(client_history)} messages): {json.dumps(client_history, indent=2, ensure_ascii=False)}", 
                               self.username, module_name="tomllm")
            except Exception as json_error:
                tomlogger.debug(f"📚 History for {client_type} ({len(client_history)} messages): {str(client_history)} (JSON serialization failed: {json_error})", 
                               self.username, module_name="tomllm")
        
        full_conversation = []
        
        if use_json_format:
            # NEW JSON FORMAT: Build conversation with separate system messages
            
            # Use new JSON system message if all required parameters are provided
            if tom_persona is not None and today is not None and weeknumber is not None:
                # 1. Global system message (without triage instructions)
                global_system_message = self._create_json_system_message(
                    tom_persona=tom_persona,
                    today=today,
                    weeknumber=weeknumber,
                    gps=gps or "",
                    personal_context=personal_context or "",
                    client_type=client_type
                )
                full_conversation.append(global_system_message)
                
                # 2. Add history if exists
                if client_history:
                    full_conversation.extend(client_history)
                
                if triage_mode and triage_instructions:
                    # TRIAGE MODE: Add two separate triage system messages
                    # First: textual instructions
                    triage_instructions_message = {
                        "role": "system",
                        "content": triage_instructions
                    }
                    full_conversation.append(triage_instructions_message)
                    
                    # Second: JSON modules (if provided)
                    if triage_modules_json:
                        triage_modules_message = {
                            "role": "system",
                            "content": triage_modules_json
                        }
                        full_conversation.append(triage_modules_message)
                    
                    # 3. Add helper messages from current_conversation (memory, etc.)
                    # In triage mode, helper messages come after triage instructions
                    helper_messages = [msg for msg in current_conversation if msg.get('role') == 'system']
                    user_messages = [msg for msg in current_conversation if msg.get('role') != 'system']
                    
                    if helper_messages:
                        full_conversation.extend(helper_messages)
                    
                    # 4. Add user messages last
                    if user_messages:
                        full_conversation.extend(user_messages)
                        
                    triage_systems_count = 2 if triage_modules_json else 1
                    tomlogger.debug(f"Built triage conversation for {client_type}: 1 global + {len(client_history)} history + {triage_systems_count} triage + {len(helper_messages)} helpers + {len(user_messages)} user = {len(full_conversation)} total", 
                                   self.username, module_name="tomllm")
                else:
                    # NORMAL MODE: Add helper messages then user messages
                    # 3. Add helper messages from current_conversation (behavior, memory, etc.)
                    helper_messages = [msg for msg in current_conversation if msg.get('role') == 'system']
                    user_messages = [msg for msg in current_conversation if msg.get('role') != 'system']
                    
                    if helper_messages:
                        full_conversation.extend(helper_messages)
                    
                    # 4. Add user messages last
                    if user_messages:
                        full_conversation.extend(user_messages)
                        
                    tomlogger.debug(f"Built normal conversation for {client_type}: 1 global + {len(client_history)} history + {len(helper_messages)} helpers + {len(user_messages)} user = {len(full_conversation)} total", 
                                   self.username, module_name="tomllm")
                
                # Early return - conversation is already complete
                return full_conversation
                
            else:
                tomlogger.warning(f"Missing required parameters for JSON format (tom_persona: {tom_persona is not None}, today: {today is not None}, weeknumber: {weeknumber is not None}), falling back to legacy format", 
                               self.username, module_name="tomllm")
                use_json_format = False
        
        if not use_json_format:
            # LEGACY FORMAT: Build conversation in correct OpenAI order:
            # 1. Temporal message first (date/GPS - never stored in history)
            # 2. Tom prompt second (global context - never stored in history) 
            # 3. Personal context message third (user context - never stored in history)
            # 4. Formatting message fourth (response context - never stored in history)
            
            # 1. Add temporal message first if provided (date/GPS)
            if temporal_message:
                full_conversation.append(temporal_message)
            
            # 2. Add Tom prompt second if provided 
            if tom_prompt:
                full_conversation.append(tom_prompt)
            
            # 3. Add personal context message third if provided
            if personal_context_message:
                full_conversation.append(personal_context_message)
            
            # 4. Add formatting message fourth if provided
            if formatting_message:
                full_conversation.append(formatting_message)
            
            temporal_count = 1 if temporal_message else 0
            tom_prompt_count = 1 if tom_prompt else 0
            personal_context_count = 1 if personal_context_message else 0
            formatting_count = 1 if formatting_message else 0
            tomlogger.debug(f"Built conversation for {client_type}: {temporal_count} temporal + {tom_prompt_count} tom + {personal_context_count} personal_context + {formatting_count} formatting + {len(client_history)} history + {len(current_conversation)} current = {len(full_conversation) + len(client_history) + len(current_conversation)} total", 
                           self.username, module_name="tomllm")
        
        # Add history (clean history without context messages)
        if client_history:
            full_conversation.extend(client_history)
        
        # Add current conversation messages
        full_conversation.extend(current_conversation)
        
        return full_conversation
    
    def reset_history(self, client_type: str, mcp_client=None):
        """
        Reset conversation history for specific client type, with optional behavior tuning analysis
        
        Args:
            client_type: 'web', 'android', or 'tui'
            mcp_client: Optional MCPClient instance for behavior tuning analysis
        """
        if client_type not in self.history:
            tomlogger.warning(f"Invalid client type '{client_type}', cannot reset", 
                            self.username, module_name="tomllm")
            return
        
        history_length = len(self.history[client_type])
        
        # Analyze behavior tuning before clearing history if behavior service is available
        if history_length > 0 and mcp_client:
            # Check if behavior service is available before trying to analyze
            behavior_connection = mcp_client.get_mcp_connection("behavior")
            if behavior_connection and behavior_connection.get("tools"):
                self._analyze_behavior_tuning_async(client_type, mcp_client)
            else:
                tomlogger.debug(f"Behavior service not available, skipping behavior tuning analysis", self.username, module_name="tomllm")
        
        # Analyze and store conversation in memory before clearing history if memory service is available
        if history_length > 0 and mcp_client:
            # Check if memory service is available before trying to store
            memory_connection = mcp_client.get_mcp_connection("memory")
            if memory_connection and memory_connection.get("tools"):
                self._analyze_and_store_conversation_async(client_type, mcp_client)
            else:
                tomlogger.debug(f"Memory service not available, skipping conversation storage", self.username, module_name="tomllm")
        
        # Debug logging - show what was cleared in DEBUG mode
        if tomlogger.logger and tomlogger.logger.logger.level <= 10 and history_length > 0:  # DEBUG level = 10
            try:
                tomlogger.debug(f"🗑️ Clearing {client_type} history content: {json.dumps(self.history[client_type], indent=2, ensure_ascii=False)}", 
                               self.username, module_name="tomllm")
            except Exception as json_error:
                tomlogger.debug(f"🗑️ Clearing {client_type} history content: {str(self.history[client_type])} (JSON serialization failed: {json_error})", 
                               self.username, module_name="tomllm")
        
        self.history[client_type] = []
        tomlogger.info(f"🔄 Reset {client_type} conversation history ({history_length} messages cleared)", 
                      self.username, module_name="tomllm")
    
    def get_history_length(self, client_type: str) -> int:
        """
        Get the number of messages in history for a client type
        
        Args:
            client_type: 'web', 'android', or 'tui'
            
        Returns:
            Number of messages in history
        """
        if client_type not in self.history:
            return 0
        return len(self.history[client_type])
    
    def _analyze_behavior_tuning_async(self, client_type: str, mcp_client):
        """Analyze session for behavior tuning insights and update behavior configuration asynchronously"""
        
        def analyze_tuning_thread():
            try:
                # Check if behavior service is available
                behavior_connection = mcp_client.get_mcp_connection("behavior")
                if not behavior_connection or not behavior_connection.get("tools"):
                    tomlogger.debug(f"Behavior service not available for tuning analysis", self.username, module_name="tomllm")
                    return
                
                tomlogger.info(f"🎯 Starting behavior tuning analysis for {client_type} client", self.username, module_name="tomllm")
                
                # Prepare conversation history as text (only user and assistant messages)
                conversation_text = ""
                history = self.history.get(client_type, [])
                
                for msg in history:
                    if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                        if msg['role'] in ['user', 'assistant'] and isinstance(msg['content'], str):
                            # Truncate very long messages to avoid API limits
                            content = msg['content']
                            if len(content) > 1000:
                                content = content[:1000] + "..."
                            conversation_text += f"{msg['role']}: {content}\n"
                
                # Skip analysis if no meaningful conversation content
                if len(conversation_text.strip()) < 50:
                    tomlogger.debug(f"Conversation too short for behavior tuning analysis, skipping", self.username, module_name="tomllm")
                    return
                
                # Limit conversation text size to avoid API limits
                if len(conversation_text) > 3000:
                    conversation_text = conversation_text[-3000:]  # Keep only the last 3000 chars
                    conversation_text = "...\n" + conversation_text
                
                # Get current behavior configuration via MCP resource
                current_behavior_prompts = ""
                try:
                    # Create async task to get behavior prompts
                    async def get_behavior_prompts():
                        try:
                            from mcp.client.streamable_http import streamablehttp_client
                            from mcp import ClientSession
                            
                            async with streamablehttp_client(behavior_connection['url']) as (read_stream, write_stream, _):
                                async with ClientSession(read_stream, write_stream) as session:
                                    await session.initialize()
                                    
                                    # Get all behavior prompts via resource
                                    resource_uri = "description://behavior_prompts"
                                    resource_result = await session.read_resource(resource_uri)
                                    
                                    if resource_result and resource_result.contents:
                                        content = resource_result.contents[0]
                                        if hasattr(content, 'text'):
                                            return content.text
                                        elif hasattr(content, 'data'):
                                            return str(content.data)
                                    return ""
                        except Exception as e:
                            tomlogger.debug(f"Error getting behavior prompts: {e}", self.username, module_name="tomllm")
                            return ""
                    
                    # Run async function
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    current_behavior_prompts = loop.run_until_complete(get_behavior_prompts())
                    
                except Exception as e:
                    tomlogger.debug(f"Error getting current behavior prompts: {e}", self.username, module_name="tomllm")
                    current_behavior_prompts = ""
                
                if not current_behavior_prompts:
                    current_behavior_prompts = "# No current behavior adjustments configured"
                
                # Prepare available modules description from MCP services
                available_modules = []
                mcp_connections = mcp_client.get_mcp_connections()
                for service_name, connection_info in mcp_connections.items():
                    available_modules.append(f"- {service_name}: {connection_info.get('description', 'MCP service')}")
                
                modules_description = "\n".join(available_modules)
                
                # Create analysis prompt (inspired by the old version)
                tuning_prompt = f"""Analyze the following conversation to identify any information that would be useful for behavioral tuning of modules. Based on the conversation content, available modules, and current behavior configuration, determine if any updates would be beneficial.

Available modules and their descriptions:
{modules_description}

Current behavior configuration:
{current_behavior_prompts}

Conversation history:
{conversation_text}

Instructions:
1. Look for user preferences, specific requirements, or behavioral adjustments mentioned in the conversation
2. Identify which modules could benefit from these insights, or if this should be a GLOBAL behavioral change
3. Consider adding new behavioral adjustments for modules not currently configured
4. Consider modifying existing behavioral adjustments if new information contradicts or enhances current settings
5. Only suggest updates if there's clear, actionable information from the conversation
6. Use the 'global' module for behavioral changes that apply to all modules (e.g., language preferences, response style)

Examples of what to look for:
- User preferences about response style or format (use 'global' module)
- Language preferences (use 'global' module)
- Specific requirements for how certain modules should behave
- Corrections or feedback about module behavior
- Contextual information that would improve module responses

If behavioral adjustments are needed, use the update_behavior_prompt_for_module function to make the changes.
If no updates are needed, simply respond with "NO_UPDATE".

IMPORTANT: 
- Use 'global' for changes that affect all modules (language, general response style, etc.)
- Use specific module names for module-specific behavioral adjustments
- Each behavioral adjustment should be a clear, actionable instruction
- Be concise and specific in behavioral instructions"""

                # Call LLM for tuning analysis using behavior LLM
                tuning_messages = [
                    {"role": "system", "content": "You are a behavioral tuning analyst specialized in identifying user preferences and module optimization opportunities from conversation history."},
                    {"role": "user", "content": tuning_prompt}
                ]
                
                # Validate message content before sending to LLM
                for msg in tuning_messages:
                    if not isinstance(msg.get('content'), str):
                        tomlogger.error(f"Invalid message content type in behavior tuning analysis: {type(msg.get('content'))}", self.username, module_name="tomllm")
                        return
                    if len(msg['content']) > 15000:  # Limit to prevent API errors
                        msg['content'] = msg['content'][:15000] + "...\n[Content truncated due to length]"
                
                # Get behavior tools from MCP connection
                behavior_tools = behavior_connection.get("tools", [])
                
                # Execute LLM analysis with behavior tools
                try:
                    async def run_behavior_analysis():
                        from mcp.client.streamable_http import streamablehttp_client
                        from mcp import ClientSession
                        
                        async with streamablehttp_client(behavior_connection['url']) as (read_stream, write_stream, _):
                            async with ClientSession(read_stream, write_stream) as session:
                                await session.initialize()
                                
                                # Execute request with tools using the existing execution method
                                execution_result = await self.execute_request_with_tools(
                                    conversation=tuning_messages,
                                    tools=behavior_tools,
                                    complexity=1,
                                    max_iterations=5,
                                    mcp_client=mcp_client,
                                    client_type=client_type,
                                    track_history=False  # Don't add this to user history
                                )
                                
                                return execution_result
                    
                    # Run the analysis
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    execution_result = loop.run_until_complete(run_behavior_analysis())
                    
                    if execution_result.get("status") == "OK":
                        tomlogger.info(f"✅ Behavior tuning analysis completed successfully", self.username, module_name="tomllm")
                    else:
                        tomlogger.warning(f"Behavior tuning analysis completed with issues: {execution_result.get('message', 'Unknown error')}", self.username, module_name="tomllm")
                        
                except Exception as analysis_error:
                    tomlogger.error(f"Error during behavior tuning analysis: {str(analysis_error)}", self.username, module_name="tomllm")
                
            except Exception as e:
                tomlogger.error(f"Error during behavior tuning analysis: {str(e)}", self.username, module_name="tomllm")
        
        # Start analysis in background thread
        thread = threading.Thread(target=analyze_tuning_thread)
        thread.daemon = True
        thread.start()
        tomlogger.debug(f"Started behavior tuning analysis in background thread", self.username, module_name="tomllm")
    
    def _analyze_and_store_conversation_async(self, client_type: str, mcp_client):
        """Analyze conversation and store in memory asynchronously"""
        
        def analyze_conversation_thread():
            try:
                # Check if memory service is available
                memory_connection = mcp_client.get_mcp_connection("memory")
                if not memory_connection or not memory_connection.get("tools"):
                    tomlogger.debug(f"Memory service not available for conversation storage", self.username, module_name="tomllm")
                    return
                
                tomlogger.info(f"🧠 Starting conversation analysis for memory storage ({client_type} client)", self.username, module_name="tomllm")
                
                # Prepare conversation history - filter to user and assistant messages only
                history = self.history.get(client_type, [])
                filtered_conversation = []
                
                for msg in history:
                    if (isinstance(msg, dict) and 
                        msg.get('role') in ['user', 'assistant'] and 
                        isinstance(msg.get('content'), str) and 
                        msg['content'].strip()):
                        
                        filtered_conversation.append({
                            "role": msg['role'],
                            "content": msg['content'].strip()
                        })
                
                # Skip if no meaningful conversation
                if not filtered_conversation:
                    tomlogger.debug(f"No meaningful conversation content for memory storage", self.username, module_name="tomllm")
                    return
                
                if len(filtered_conversation) < 2:  # Need at least one user + one assistant message
                    tomlogger.debug(f"Conversation too short for memory storage (only {len(filtered_conversation)} messages)", self.username, module_name="tomllm")
                    return
                
                # Convert conversation to JSON string
                conversation_json = json.dumps(filtered_conversation, ensure_ascii=False)
                
                tomlogger.debug(f"Prepared conversation for memory analysis: {len(filtered_conversation)} messages", self.username, module_name="tomllm")
                
                # Call memory service to analyze and store conversation
                try:
                    async def store_conversation():
                        try:
                            from mcp.client.streamable_http import streamablehttp_client
                            from mcp import ClientSession
                            
                            async with streamablehttp_client(memory_connection['url']) as (read_stream, write_stream, _):
                                async with ClientSession(read_stream, write_stream) as session:
                                    await session.initialize()
                                    
                                    # Call the analyze_and_store_conversation tool
                                    result = await session.call_tool(
                                        "analyze_and_store_conversation",
                                        {
                                            "conversation": conversation_json
                                        }
                                    )
                                    
                                    tomlogger.debug(f"Memory storage result: {result}", self.username, module_name="tomllm")
                                    return result
                        except Exception as e:
                            tomlogger.debug(f"Error calling memory service: {e}", self.username, module_name="tomllm")
                            return None
                    
                    # Run async function
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    storage_result = loop.run_until_complete(store_conversation())
                    
                    if storage_result:
                        tomlogger.info(f"✅ Conversation successfully stored in memory", self.username, module_name="tomllm")
                    else:
                        tomlogger.warning(f"Failed to store conversation in memory", self.username, module_name="tomllm")
                        
                except Exception as storage_error:
                    tomlogger.error(f"Error during conversation memory storage: {str(storage_error)}", self.username, module_name="tomllm")
                
            except Exception as e:
                tomlogger.error(f"Error during conversation memory analysis: {str(e)}", self.username, module_name="tomllm")
        
        # Start analysis in background thread
        thread = threading.Thread(target=analyze_conversation_thread)
        thread.daemon = True
        thread.start()
        tomlogger.debug(f"Started conversation memory analysis in background thread", self.username, module_name="tomllm")
    
    async def _apply_behavior_prompts(self, conversation: List[Dict[str, str]], selected_modules: List[str], mcp_client) -> List[Dict[str, str]]:
        """Apply behavior prompts from the behavior service to the conversation"""
        if not mcp_client:
            return conversation
        
        # Check if behavior service is available
        behavior_connection = mcp_client.get_mcp_connection("behavior")
        if not behavior_connection or not behavior_connection.get("tools"):
            return conversation
        
        try:
            from mcp.client.streamable_http import streamablehttp_client
            from mcp import ClientSession
            
            async with streamablehttp_client(behavior_connection['url']) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    enhanced_conversation = conversation.copy()
                    
                    # Get global behavior prompts first
                    try:
                        global_resource = await session.read_resource("description://behavior_prompts")
                        if global_resource and global_resource.contents:
                            content = global_resource.contents[0]
                            global_prompts = ""
                            if hasattr(content, 'text'):
                                global_prompts = content.text
                            elif hasattr(content, 'data'):
                                global_prompts = str(content.data)
                            
                            if global_prompts:
                                # Extract global behavioral adjustments
                                if "GLOBAL BEHAVIOR ADJUSTMENTS:" in global_prompts:
                                    global_section = global_prompts.split("GLOBAL BEHAVIOR ADJUSTMENTS:")[1]
                                    if "\n\nMODULE" in global_section:
                                        global_section = global_section.split("\n\nMODULE")[0]
                                    global_section = global_section.strip()
                                    
                                    if global_section:
                                        enhanced_conversation.append({
                                            "role": "system", 
                                            "content": f"BEHAVIORAL ADJUSTMENT (Global): {global_section}"
                                        })
                                        tomlogger.debug(f"Applied global behavior prompt", self.username, module_name="tomllm")
                                
                                # Extract module-specific behavioral adjustments for selected modules
                                for module_name in selected_modules:
                                    module_marker = f"MODULE '{module_name}' BEHAVIOR ADJUSTMENTS:"
                                    if module_marker in global_prompts:
                                        module_section = global_prompts.split(module_marker)[1]
                                        if "\n\nMODULE" in module_section:
                                            module_section = module_section.split("\n\nMODULE")[0]
                                        module_section = module_section.strip()
                                        
                                        if module_section:
                                            enhanced_conversation.append({
                                                "role": "system", 
                                                "content": f"BEHAVIORAL ADJUSTMENT ({module_name}): {module_section}"
                                            })
                                            tomlogger.debug(f"Applied behavior prompt for module {module_name}", self.username, module_name="tomllm")
                    
                    except Exception as e:
                        tomlogger.debug(f"Could not get behavior prompts: {e}", self.username, module_name="tomllm")
                    
                    return enhanced_conversation
        
        except Exception as e:
            tomlogger.debug(f"Error applying behavior prompts: {e}", self.username, module_name="tomllm")
            return conversation
    
    def synthesize_tts_response(self, text_response: str) -> str:
        """
        Synthesize a TTS-friendly version of the response using the configured LLM
        
        Args:
            text_response: The original response text to synthesize
            
        Returns:
            TTS-friendly text suitable for voice reading
        """
        try:
            # Create TTS synthesis prompt (based on old version logic)
            tts_prompt = f"""You must synthesize the following response to make it suitable for voice reading by a text-to-speech (TTS) system.

Original response:
{text_response}

TTS synthesis guidelines:
- IMPORTANT: Keep the same language as the original text (French/English/etc.)
- Remove all Markdown formatting (links, bold, italic, lists, etc.)
- Convert lists into short, natural sentences
- Replace URLs with simple descriptions like "link" or "website"
- Keep only essential information
- Limit to 1-2 sentences maximum
- IMPORTANT: Write as short as you can
- Use fluid sentences for voice reading
- Use informal tone ("tu" form in French, casual in English)
- Remove polite endings like "let me know if you want to know more" or "tell me if you want me to do this or that"
- For ACTION requests: respond with brief confirmation like "C'est fait" (French) or "Done" (English)
- For INFORMATION requests: provide brief summary without "C'est fait", for example "Tu as 13 news, dont 4 en sciences, 6 en cyber et 3 en blog" or "You have 5 emails, 3 urgent"
- Be direct and concise, avoid unnecessary politeness formulas
- Use relative time references: say "demain" instead of "demain, le jeudi 12 septembre 2025", "aujourd'hui" instead of full dates
- Avoid redundant temporal information

Respond only with the text to be read, without explanation or formatting."""

            # Create messages for TTS synthesis
            tts_messages = [
                {"role": "system", "content": "You are a text synthesis assistant specialized in creating TTS-friendly content."},
                {"role": "user", "content": tts_prompt}
            ]
            
            # Call LLM for TTS synthesis using TTS LLM and complexity 0 for speed
            tts_response = self.callLLM(messages=tts_messages, complexity=0, llm=self.tts_llm)
            
            if tts_response and tts_response.choices[0].finish_reason == "stop":
                tts_text = tts_response.choices[0].message.content.strip()
                tomlogger.debug(f"TTS synthesis successful: {len(tts_text)} chars", 
                              self.username, module_name="tomllm")
                return tts_text
            else:
                tomlogger.warning(f"TTS synthesis failed, using fallback", 
                                self.username, module_name="tomllm")
                return self._create_fallback_tts_text(text_response)
                
        except Exception as e:
            tomlogger.error(f"Error during TTS synthesis: {str(e)}", 
                          self.username, module_name="tomllm")
            return self._create_fallback_tts_text(text_response)
    
    def _create_fallback_tts_text(self, text_response: str) -> str:
        """
        Create simple fallback TTS text when synthesis fails
        
        Args:
            text_response: Original text response
            
        Returns:
            Simple cleaned text suitable for TTS
        """
        import re
        
        # Simple fallback: basic text cleaning
        clean_text = re.sub(r'\[.*?\]', '', text_response)  # Remove markdown links
        clean_text = re.sub(r'[*_`#]', '', clean_text)     # Remove markdown formatting
        clean_text = re.sub(r'\n+', ' ', clean_text)       # Replace newlines with spaces
        clean_text = clean_text.strip()
        
        # Limit to first 200 characters
        if len(clean_text) > 200:
            clean_text = clean_text[:200].rsplit(' ', 1)[0] + "..."
            
        return clean_text
