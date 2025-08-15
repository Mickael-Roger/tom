#!/usr/bin/env python3
"""
Tom Agent Server
Backend service for individual user agents
"""

import cherrypy
import json
import os
import sys
import yaml
import logging
from typing import Dict, Any, Optional

# Add lib directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from tomlogger import init_logger
import tomlogger


def init_config(config_path: str = '/data/config.yml') -> Dict[str, Any]:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found: {config_path}")
        # Use default config if file not found
        return {'global': {'log_level': 'INFO'}}
    except yaml.YAMLError as exc:
        print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {'global': {'log_level': 'INFO'}}


class LLMConfig:
    """Configuration class for LLM setup"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Variables to store LLM configuration
        self.default_llm = None
        self.tts_llm = None
        self.llms_dict = {}  # Dict with llm_name -> {api, env_var, models}
        
        self._setup_llms()
        
    def _setup_llms(self):
        """Setup LLM configurations from config"""
        global_config = self.config.get('global', {})
        
        # Get default LLMs
        self.default_llm = global_config.get('llm', 'openai')
        self.tts_llm = global_config.get('llm_tts', self.default_llm)
        
        # Load LLM configuration from global.llms structure
        llms_config = global_config.get('llms', {})
        
        tomlogger.info(f"Setting up LLMs from config: {list(llms_config.keys())}", module_name="llm")
        
        # Configure each LLM provider from configuration
        for llm_name, llm_config in llms_config.items():
            if not isinstance(llm_config, dict):
                tomlogger.warning(f"Invalid configuration for LLM '{llm_name}', skipping", module_name="llm")
                continue
                
            api_key = llm_config.get("api")
            if not api_key:
                tomlogger.warning(f"No API key found for LLM '{llm_name}', skipping", module_name="llm")
                continue
                
            # Get models configuration (required)
            models = llm_config.get("models")
            if not models or len(models) != 3:
                tomlogger.warning(f"LLM '{llm_name}' must have exactly 3 models for complexity levels 0, 1, 2. Skipping.", module_name="llm")
                continue
                
            # Get environment variable name (required)
            env_var = llm_config.get("env_var")
            if not env_var:
                tomlogger.warning(f"No env_var specified for LLM '{llm_name}', skipping", module_name="llm")
                continue
            
            # Configure the LLM environment variable
            os.environ[env_var] = api_key
            
            # Store LLM configuration in dict
            self.llms_dict[llm_name] = {
                "api": api_key,
                "env_var": env_var,
                "models": models
            }
            
            tomlogger.info(f"✅ Configured LLM '{llm_name}' with models: {models}", module_name="llm")
        
        # Check that the configured default LLM was actually loaded
        if self.default_llm not in self.llms_dict:
            available_llms = list(self.llms_dict.keys())
            tomlogger.error(f"Default LLM '{self.default_llm}' is not configured. Available LLMs: {available_llms}", module_name="llm")
            if available_llms:
                self.default_llm = available_llms[0]
                tomlogger.warning(f"Falling back to first available LLM: {self.default_llm}", module_name="llm")
            else:
                tomlogger.critical("No LLMs configured! Agent will not function properly.", module_name="llm")
        
        # Check TTS LLM
        if self.tts_llm not in self.llms_dict:
            tomlogger.warning(f"TTS LLM '{self.tts_llm}' not configured, falling back to default LLM", module_name="llm")
            self.tts_llm = self.default_llm
        
        # Log final configuration
        tomlogger.info(f"✅ Default LLM: {self.default_llm}", module_name="llm")
        tomlogger.info(f"✅ TTS LLM: {self.tts_llm}", module_name="llm")


class MCPClient:
    """MCP (Model Context Protocol) Client for managing user-specific MCP services"""
    
    def __init__(self, username: str, config: Dict[str, Any]):
        self.username = username
        self.config = config
        self.mcp_services = {}
        self.load_user_services()
    
    def load_user_services(self):
        """Load MCP services configuration for the user from config.yml"""
        users_config = self.config.get('users', [])
        user_config = None
        
        # Find the user configuration
        for user in users_config:
            if user.get('username') == self.username:
                user_config = user
                break
        
        if not user_config:
            tomlogger.warning(f"No configuration found for user '{self.username}'", self.username, module_name="mcp")
            return
        
        # Load personal context
        self.personal_context = user_config.get('personal_context', '')
        if self.personal_context:
            tomlogger.info(f"✅ Personal context loaded for user '{self.username}'", self.username, module_name="mcp")
        
        # Load services configuration
        services = user_config.get('services', {})
        if not services:
            tomlogger.info(f"No MCP services configured for user '{self.username}'", self.username, module_name="mcp")
            return
        
        # Validate and store each service
        for service_name, service_config in services.items():
            if not isinstance(service_config, dict):
                tomlogger.warning(f"Invalid service configuration for '{service_name}', skipping", self.username, module_name="mcp")
                continue
            
            # Validate required fields
            url = service_config.get('url')
            if not url:
                tomlogger.warning(f"Service '{service_name}' missing required 'url' field, skipping", self.username, module_name="mcp")
                continue
            
            # Extract optional fields
            headers = service_config.get('headers', {})
            description = service_config.get('description', '')
            llm = service_config.get('llm', '')
            enable = service_config.get('enable', True)  # Default to True if not specified
            
            # Validate headers is a dict
            if not isinstance(headers, dict):
                tomlogger.warning(f"Service '{service_name}' has invalid headers (must be dict), using empty headers", self.username, module_name="mcp")
                headers = {}
            
            # Skip disabled services
            if not enable:
                tomlogger.info(f"⚠️ MCP service '{service_name}' is disabled, skipping", self.username, module_name="mcp")
                continue
            
            # Store service configuration
            self.mcp_services[service_name] = {
                'url': url,
                'headers': headers,
                'description': description,
                'llm': llm,
                'enable': enable
            }
            
            tomlogger.info(f"✅ Loaded MCP service '{service_name}' at {url}", self.username, module_name="mcp")
        
        tomlogger.info(f"Loaded {len(self.mcp_services)} MCP services for user '{self.username}'", self.username, module_name="mcp")
    
    def get_services(self) -> Dict[str, Dict]:
        """Get all configured MCP services for the user"""
        return self.mcp_services
    
    def get_service(self, service_name: str) -> Optional[Dict]:
        """Get configuration for a specific MCP service"""
        return self.mcp_services.get(service_name)
    
    def get_personal_context(self) -> str:
        """Get the personal context for the user"""
        return getattr(self, 'personal_context', '')


class TomAgent:
    """Individual Tom agent service"""
    
    def __init__(self, username: str, config: Dict[str, Any]):
        self.username = username
        self.config = config
        
        # Initialize LLM configuration
        self.llm_config = LLMConfig(config)
        tomlogger.info(f"Agent initialized for {username} with LLMs: {list(self.llm_config.llms_dict.keys())}", username, "sys", "agent")
        
        # Initialize MCP client
        self.mcp_client = MCPClient(username, config)
        
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    @cherrypy.tools.json_out()
    def notifications(self):
        """Handle notifications requests"""
        tomlogger.info("GET /notifications", self.username, "api", "agent")
        return {"status": "OK", "message": "Notifications endpoint"}
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_out()
    def reset(self):
        """Handle reset requests"""
        tomlogger.info("POST /reset", self.username, "api", "agent")
        return {"status": "OK"}
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    @cherrypy.tools.json_out()
    def tasks(self):
        """Handle tasks requests"""
        tomlogger.info("GET /tasks", self.username, "api", "agent")
        return {
            "status": "OK", 
            "message": "Tasks endpoint",
            "background_tasks": [],
            "id": 0
        }
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def process(self):
        """Handle process requests"""
        # Echo back the received data for POST requests
        request_data = getattr(cherrypy.request, 'json', None)
        tomlogger.info(f"POST /process with data: {request_data}", self.username, "api", "agent")
        return {
            "status": "OK",
            "message": "Process endpoint", 
            "received_data": request_data,
            "response": "This is a test response from the agent"
        }


def main():
    """Main application entry point"""
    # Get username from environment variable
    username = os.environ.get('TOM_USERNAME', 'unknown')
    
    # Load configuration
    config = init_config('/data/config.yml')
    
    # Initialize logging
    log_level = config.get('global', {}).get('log_level', 'INFO')
    tom_logger = init_logger(log_level)
    tom_logger.startup(f"Starting Tom Agent for user: {username}")
    tom_logger.startup(f"Log level: {log_level}")
    
    # Configure CherryPy logging to use our tomlogger
    # Disable default CherryPy logging
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8080,
        'log.screen': False,  # Disable default screen logging
        'log.access_file': '',  # Disable access log file
        'log.error_file': '',   # Disable error log file
    })
    
    # Replace CherryPy's loggers with our tomlogger
    cherrypy.log.access_log.handlers.clear()
    cherrypy.log.error_log.handlers.clear()
    
    # Add our handler to CherryPy logs
    tom_handler = tom_logger.logger.handlers[0]  # Get our console handler
    cherrypy.log.access_log.addHandler(tom_handler)
    cherrypy.log.error_log.addHandler(tom_handler)
    
    # Set CherryPy logs to INFO level (will be handled by our formatter)
    cherrypy.log.access_log.setLevel(logging.INFO)
    cherrypy.log.error_log.setLevel(logging.INFO)
    
    # Create agent instance
    agent = TomAgent(username, config)
    
    tom_logger.startup(f"Tom Agent server starting on port 8080 for user {username}...")
    
    try:
        cherrypy.quickstart(agent, '/')
    except KeyboardInterrupt:
        tom_logger.shutdown("Agent shutting down...")
    except Exception as e:
        tom_logger.error(f"Agent error: {str(e)}", module_name="system")
        sys.exit(1)


if __name__ == "__main__":
    main()