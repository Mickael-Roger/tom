"""
Tom LLM Library
Handles LLM interactions and MCP server communication for Tom Agent
"""

import json
import os
import time
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
        
        # Debug logging
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