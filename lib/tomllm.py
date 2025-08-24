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
        
        # History management - separate history for each client type
        self.history = {
            'web': [],      # Web browser client
            'android': [],  # Android mobile client  
            'tui': []       # Terminal UI client
        }
        
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
        else:  # android, web and pwa
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
        
        # Build conversation for triage with history
        from datetime import datetime
        gps = ""
        if position:
            gps = f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}."
        
        today = datetime.now().strftime("%A %d %B %Y %H:%M:%S")
        weeknumber = datetime.now().isocalendar().week
        
        # Create temporal message (date/GPS) - never stored in history
        temporal_message = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}. {gps}\n\n"}
        
        # Build current triage conversation (without temporal message or history)
        # Note: No response formatting context needed for triage since it doesn't generate user responses
        # Note: No Tom prompt needed for triage - it has its own specific prompt
        current_triage_conversation = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_request}
        ]
        
        # Build full triage conversation with temporal message first, then history
        # No tom_prompt for triage since it has its own specific system prompt
        triage_conversation = self.get_conversation_with_history(client_type, current_triage_conversation, temporal_message)
        
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
    
    async def execute_request_with_tools(self, conversation: List[Dict[str, str]], tools: List[Dict], 
                                        complexity: int = 1, max_iterations: int = 10, mcp_client=None, 
                                        client_type: str = 'web', track_history: bool = True) -> Any:
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
            
        Returns:
            Final response content or error dict
        """
        
        working_conversation = copy.deepcopy(conversation)
        iteration = 0
        
        # Extract user request from conversation for history tracking
        if track_history:
            # Find the last user message in the conversation to add to history
            user_messages = [msg for msg in conversation if msg.get('role') == 'user']
            if user_messages:
                last_user_message = user_messages[-1]
                self.add_user_request(client_type, last_user_message.get('content', ''))
        
        tomlogger.info(f"🚀 Starting tool execution with {len(tools)} tools, max {max_iterations} iterations", 
                      self.username, module_name="tomllm")
        
        while iteration < max_iterations:
            iteration += 1
            tomlogger.debug(f"🔄 Tool execution iteration {iteration}/{max_iterations}", 
                           self.username, module_name="tomllm")
            
            # For each iteration, use the conversation as-is (tools will drive the conversation)
            current_messages = working_conversation.copy()
            response = self.callLLM(messages=current_messages, tools=tools, complexity=complexity)
            
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
    
    def get_conversation_with_history(self, client_type: str, current_conversation: List[Dict[str, Any]], 
                                      temporal_message: Optional[Dict[str, Any]] = None,
                                      tom_prompt: Optional[Dict[str, Any]] = None,
                                      formatting_message: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Build conversation with history prepended in correct order
        
        Args:
            client_type: 'web', 'android', or 'tui'
            current_conversation: Current conversation messages (user request, response formatting, etc)
            temporal_message: Optional temporal message (date/GPS) that goes first but never in history
            tom_prompt: Optional Tom prompt that goes second but never in history
            formatting_message: Optional formatting message that goes third but never in history
            
        Returns:
            Full conversation: temporal → tom_prompt → formatting → history → current messages
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
        
        # Build conversation in correct OpenAI order:
        # 1. Temporal message first (date/GPS - never stored in history)
        # 2. Tom prompt second (global context - never stored in history) 
        # 3. Formatting message third (response context - never stored in history)
        # 4. History (previous conversation - without formatage messages)
        # 5. Current conversation messages (user request, etc)
        
        full_conversation = []
        
        # 1. Add temporal message first if provided (date/GPS)
        if temporal_message:
            full_conversation.append(temporal_message)
        
        # 2. Add Tom prompt second if provided 
        if tom_prompt:
            full_conversation.append(tom_prompt)
        
        # 3. Add formatting message third if provided
        if formatting_message:
            full_conversation.append(formatting_message)
        
        # 4. Add history (clean history without formatage messages)
        if client_history:
            full_conversation.extend(client_history)
        
        # 5. Add current conversation messages
        full_conversation.extend(current_conversation)
        
        temporal_count = 1 if temporal_message else 0
        tom_prompt_count = 1 if tom_prompt else 0
        formatting_count = 1 if formatting_message else 0
        tomlogger.debug(f"Built conversation for {client_type}: {temporal_count} temporal + {tom_prompt_count} tom + {formatting_count} formatting + {len(client_history)} history + {len(current_conversation)} current = {len(full_conversation)} total", 
                       self.username, module_name="tomllm")
        
        return full_conversation
    
    def reset_history(self, client_type: str):
        """
        Reset conversation history for specific client type
        
        Args:
            client_type: 'web', 'android', or 'tui'
        """
        if client_type not in self.history:
            tomlogger.warning(f"Invalid client type '{client_type}', cannot reset", 
                            self.username, module_name="tomllm")
            return
        
        history_length = len(self.history[client_type])
        
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
