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
import asyncio
import httpx
from typing import Dict, Any, Optional, List
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# Add lib directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from tomlogger import init_logger
import tomlogger
from tomllm import TomLLM

import asyncio
import traceback
from datetime import datetime
import pytz

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




class MCPClient:
    """MCP (Model Context Protocol) Client for managing user-specific MCP services"""
    
    def __init__(self, username: str, config: Dict[str, Any]):
        self.username = username
        self.config = config
        self.mcp_services = {}
        self.mcp_connections = {}  # Dict: service_name -> {object, description, complexity, tools}
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
            enable = service_config.get('enable', True)  # Default to True if not specified
            
            # Extract config section for description, complexity, and llm
            config_section = service_config.get('config', {})
            description = config_section.get('description', '')
            complexity = config_section.get('complexity', 0)  # Default to 0 if not specified
            
            # Get LLM with fallback to global default
            llm = config_section.get('llm', '')
            if not llm:
                # Fallback to global.llm if not specified in service config
                llm = self.config.get('global', {}).get('llm', 'openai')
            
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
                'complexity': complexity,
                'enable': enable
            }
            
            tomlogger.info(f"✅ Loaded MCP service '{service_name}' at {url}", self.username, module_name="mcp")
        
        tomlogger.info(f"Loaded {len(self.mcp_services)} MCP services for user '{self.username}'", self.username, module_name="mcp")
        
        # Initialize MCP connections structure with config values
        for service_name, service_config in self.mcp_services.items():
            self.mcp_connections[service_name] = {
                'object': None,
                'description': service_config['description'],
                'complexity': service_config['complexity'],
                'tools': []
            }
        
        # Debug logging for MCP connections if in DEBUG mode
        log_level = self.config.get('global', {}).get('log_level', 'INFO')
        if log_level.upper() == 'DEBUG':
            # Log structure without the actual session objects to avoid serialization issues
            debug_connections = {}
            for name, conn in self.mcp_connections.items():
                debug_connections[name] = {
                    'description': conn['description'],
                    'server_description': conn.get('server_description', ''),
                    'config_description': conn.get('config_description', ''),
                    'complexity': conn['complexity'],
                    'object_type': type(conn['object']).__name__ if conn['object'] else 'None',
                    'tools_count': len(conn['tools'])
                }
            tomlogger.debug(f"MCP connections structure: {debug_connections}", self.username, module_name="mcp")
    
    async def initialize_mcp_connections(self):
        """Initialize MCP connections for all enabled services with retry logic"""
        max_retries = 10  # Maximum number of retry cycles
        retry_delay = 60  # Wait 1 minute between retry cycles
        
        failed_services = list(self.mcp_services.keys())  # Start with all services
        retry_count = 0
        
        while failed_services and retry_count < max_retries:
            if retry_count > 0:
                tomlogger.info(f"Retrying MCP connections (attempt {retry_count + 1}/{max_retries}) for {len(failed_services)} services", self.username, module_name="mcp")
                await asyncio.sleep(retry_delay)
            
            # Try to connect to all failed services
            newly_failed = []
            for service_name in failed_services:
                service_config = self.mcp_services[service_name]
                try:
                    success = await self.connect_to_mcp_service(service_name, service_config)
                    if not success:
                        newly_failed.append(service_name)
                except Exception as e:
                    tomlogger.error(f"Failed to connect to MCP service '{service_name}': {str(e)}", self.username, module_name="mcp")
                    newly_failed.append(service_name)
            
            # Update the list of failed services
            failed_services = newly_failed
            retry_count += 1
            
            if failed_services:
                tomlogger.warning(f"Still {len(failed_services)} failed MCP services: {failed_services}", self.username, module_name="mcp")
            else:
                tomlogger.info(f"✅ All MCP services connected successfully", self.username, module_name="mcp")
                break
        
        if failed_services:
            tomlogger.error(f"❌ Failed to connect to {len(failed_services)} MCP services after {max_retries} retries: {failed_services}", self.username, module_name="mcp")
    
    async def connect_to_mcp_service(self, service_name: str, service_config: Dict[str, Any]) -> bool:
        """Connect to a specific MCP service and retrieve its tools
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        url = service_config['url']
        headers = service_config.get('headers', {})
        
        tomlogger.info(f"🔌 Attempting connection to MCP service '{service_name}' at {url}", self.username, module_name="mcp")
        tomlogger.debug(f"Connection details - URL: {url}, Headers: {headers}", self.username, module_name="mcp")
        
        try:
            # Skip GET test for stateless HTTP MCP servers (they only accept POST)
            tomlogger.debug(f"Skipping GET test for stateless HTTP MCP endpoint: {url}", self.username, module_name="mcp")
            
            # Try full MCP streamable HTTP connection directly
            tomlogger.debug(f"Attempting streamable-http MCP connection to '{service_name}'", self.username, module_name="mcp")
            try:
                # Use streamable HTTP client for MCP over HTTP
                async with streamablehttp_client(url) as (read_stream, write_stream, _):
                    tomlogger.debug(f"Streamable HTTP connection established for '{service_name}'", self.username, module_name="mcp")
                    
                    try:
                        async with ClientSession(read_stream, write_stream) as session:
                            tomlogger.debug(f"MCP ClientSession created for '{service_name}'", self.username, module_name="mcp")
                            
                            # Initialize the MCP session
                            tomlogger.debug(f"Initializing MCP session for '{service_name}'", self.username, module_name="mcp")
                            await session.initialize()
                            tomlogger.debug(f"MCP session initialized for '{service_name}'", self.username, module_name="mcp")
                            
                            # Get server description via resource endpoint
                            tomlogger.debug(f"Requesting server description from '{service_name}'", self.username, module_name="mcp")
                            server_description = ''
                            
                            # Try to get description via resource endpoint first
                            try:
                                # Try different possible resource URIs for description
                                resource_uris = [
                                    f"description://{service_name.lower()}",
                                    f"description://{service_name}",
                                    "description://server",
                                    "description://description"
                                ]
                                
                                for resource_uri in resource_uris:
                                    try:
                                        tomlogger.debug(f"Trying resource URI '{resource_uri}' for '{service_name}'", self.username, module_name="mcp")
                                        resource_result = await session.read_resource(resource_uri)
                                        if resource_result and resource_result.contents:
                                            # Get the first content item
                                            content = resource_result.contents[0]
                                            if hasattr(content, 'text'):
                                                server_description = content.text
                                                tomlogger.debug(f"✅ Got description from resource '{resource_uri}' for '{service_name}': {server_description[:100]}...", self.username, module_name="mcp")
                                                break
                                            elif hasattr(content, 'data'):
                                                server_description = str(content.data)
                                                tomlogger.debug(f"✅ Got description from resource '{resource_uri}' for '{service_name}': {server_description[:100]}...", self.username, module_name="mcp")
                                                break
                                    except Exception as resource_error:
                                        tomlogger.debug(f"Resource '{resource_uri}' not available for '{service_name}': {resource_error}", self.username, module_name="mcp")
                                        continue
                                        
                            except Exception as resource_error:
                                tomlogger.debug(f"Could not get description via resources from '{service_name}': {resource_error}", self.username, module_name="mcp")
                            
                            # Fallback to server info if no description found via resources
                            if not server_description:
                                try:
                                    tomlogger.debug(f"Fallback: requesting server info from '{service_name}'", self.username, module_name="mcp")
                                    server_info = await session.get_server_info()
                                    if server_info:
                                        # Try 'instructions' first (FastMCP parameter)
                                        server_description = getattr(server_info, 'instructions', '')
                                        if not server_description:
                                            # Fallback to 'description'
                                            server_description = getattr(server_info, 'description', '')
                                except Exception as info_error:
                                    tomlogger.debug(f"Could not get server info from '{service_name}': {info_error}", self.username, module_name="mcp")
                            
                            if server_description:
                                tomlogger.debug(f"Final server description for '{service_name}': {server_description}", self.username, module_name="mcp")
                            
                            # Get available tools from the MCP server
                            tomlogger.debug(f"Requesting tools list from '{service_name}'", self.username, module_name="mcp")
                            tools_result = await session.list_tools()
                            tomlogger.debug(f"Received {len(tools_result.tools)} tools from '{service_name}'", self.username, module_name="mcp")
                            
                            # Convert MCP tools to OpenAI format
                            openai_tools = []
                            for tool in tools_result.tools:
                                # Get and validate the input schema
                                if hasattr(tool, 'inputSchema') and tool.inputSchema:
                                    schema = tool.inputSchema
                                    # Ensure additionalProperties is set to False for all objects
                                    schema = self._fix_schema_additional_properties(schema)
                                else:
                                    schema = {
                                        "type": "object",
                                        "properties": {},
                                        "required": [],
                                        "additionalProperties": False
                                    }
                                
                                openai_tool = {
                                    "type": "function",
                                    "function": {
                                        "name": tool.name,
                                        "description": tool.description,
                                        "parameters": schema
                                    }
                                }
                                openai_tools.append(openai_tool)
                                
                                # Debug log the schema to verify it's correct
                                tomlogger.debug(f"Converted tool '{tool.name}' schema: {json.dumps(schema, indent=2)}", 
                                              self.username, module_name="mcp")
                            
                            # Store tools and connection info, but don't keep the session object
                            # The session will be recreated when needed for actual tool calls
                            if service_name in self.mcp_connections:
                                self.mcp_connections[service_name]['object'] = None  # Don't store session
                                self.mcp_connections[service_name]['tools'] = openai_tools
                                self.mcp_connections[service_name]['url'] = url  # Store URL for reconnection
                                self.mcp_connections[service_name]['headers'] = headers
                                
                                # Store both descriptions and use config description if available, otherwise server description
                                config_description = service_config.get('description', '')
                                self.mcp_connections[service_name]['server_description'] = server_description
                                self.mcp_connections[service_name]['config_description'] = config_description
                                
                                if config_description:
                                    self.mcp_connections[service_name]['description'] = config_description
                                    tomlogger.info(f"✅ Using config description for '{service_name}'", self.username, module_name="mcp")
                                    tomlogger.debug(f"Config description for '{service_name}': {config_description}", self.username, module_name="mcp")
                                elif server_description:
                                    self.mcp_connections[service_name]['description'] = server_description
                                    tomlogger.info(f"✅ Using server description for '{service_name}' (no config description)", self.username, module_name="mcp")
                                    tomlogger.debug(f"Server description for '{service_name}': {server_description}", self.username, module_name="mcp")
                                else:
                                    tomlogger.warning(f"No description available for '{service_name}' (config: '{config_description}', server: '{server_description}')", self.username, module_name="mcp")
                                # If neither, description remains as set from config during initialization
                                # complexity is already set from config
                            
                            tomlogger.info(f"✅ Successfully connected to MCP service '{service_name}' with {len(openai_tools)} tools", self.username, module_name="mcp")
                            tomlogger.debug(f"Available tools for '{service_name}': {[tool['function']['name'] for tool in openai_tools]}", self.username, module_name="mcp")
                            
                            # Session will be closed automatically by the context manager
                            return True
                    
                    except Exception as session_error:
                        tomlogger.error(f"MCP session error for '{service_name}': {type(session_error).__name__}: {str(session_error)}", self.username, module_name="mcp")
                        tomlogger.debug(f"Session error traceback for '{service_name}': {traceback.format_exc()}", self.username, module_name="mcp")
                        return False
                        
            except Exception as http_error:
                tomlogger.error(f"Streamable HTTP connection error for '{service_name}': {type(http_error).__name__}: {str(http_error)}", self.username, module_name="mcp")
                tomlogger.debug(f"HTTP error traceback for '{service_name}': {traceback.format_exc()}", self.username, module_name="mcp")
                return False
            
        except Exception as e:
            tomlogger.error(f"❌ Unexpected error connecting to MCP service '{service_name}': {type(e).__name__}: {str(e)}", self.username, module_name="mcp")
            tomlogger.debug(f"Full error traceback for '{service_name}': {traceback.format_exc()}", self.username, module_name="mcp")
            return False
        
    
    def get_services(self) -> Dict[str, Dict]:
        """Get all configured MCP services for the user"""
        return self.mcp_services
    
    def get_service(self, service_name: str) -> Optional[Dict]:
        """Get configuration for a specific MCP service"""
        return self.mcp_services.get(service_name)
    
    def get_mcp_connections(self) -> Dict[str, Dict]:
        """Get all MCP connections with their objects, descriptions, complexity and tools"""
        return self.mcp_connections
    
    def get_mcp_connection(self, service_name: str) -> Optional[Dict]:
        """Get MCP connection object for a specific service"""
        return self.mcp_connections.get(service_name)
    
    def get_personal_context(self) -> str:
        """Get the personal context for the user"""
        return getattr(self, 'personal_context', '')
    
    async def create_mcp_session(self, service_name: str):
        """Create a new MCP session for a service when needed"""
        if service_name not in self.mcp_connections:
            return None
        
        connection_info = self.mcp_connections[service_name]
        url = connection_info.get('url')
        headers = connection_info.get('headers', {})
        
        if not url:
            return None
        
        try:
            # Create new session for tool calls
            async with streamablehttp_client(url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return session
        except Exception as e:
            tomlogger.error(f"Failed to create MCP session for '{service_name}': {str(e)}", self.username, module_name="mcp")
            return None
    
    def init_connections_sync(self):
        """Synchronous wrapper to initialize MCP connections"""
        if self.mcp_services:
            tomlogger.info(f"Starting MCP connections initialization for {len(self.mcp_services)} services", self.username, module_name="mcp")
            # Run the async initialization in a new event loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.initialize_mcp_connections())
                finally:
                    # Ensure all pending tasks are properly cancelled
                    pending_tasks = asyncio.all_tasks(loop)
                    if pending_tasks:
                        tomlogger.debug(f"Cancelling {len(pending_tasks)} pending tasks", self.username, module_name="mcp")
                        for task in pending_tasks:
                            task.cancel()
                        # Wait for tasks to be cancelled
                        loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                    loop.close()
            except Exception as e:
                tomlogger.error(f"Failed to initialize MCP connections: {str(e)}", self.username, module_name="mcp")
        else:
            tomlogger.info("No MCP services configured for initialization", self.username, module_name="mcp")
    
    def _fix_schema_additional_properties(self, schema):
        """
        Recursively fix JSON schema to ensure all objects have additionalProperties: false
        This is required for OpenAI's strict mode
        """
        if not isinstance(schema, dict):
            return schema
        
        # Create a copy to avoid modifying the original
        fixed_schema = schema.copy()
        
        # If this is an object type, ensure additionalProperties is false
        if fixed_schema.get("type") == "object":
            fixed_schema["additionalProperties"] = False
        
        # Recursively fix nested schemas
        if "properties" in fixed_schema and isinstance(fixed_schema["properties"], dict):
            fixed_properties = {}
            for prop_name, prop_schema in fixed_schema["properties"].items():
                fixed_properties[prop_name] = self._fix_schema_additional_properties(prop_schema)
            fixed_schema["properties"] = fixed_properties
        
        # Fix array items schema
        if "items" in fixed_schema:
            fixed_schema["items"] = self._fix_schema_additional_properties(fixed_schema["items"])
        
        # Fix anyOf, oneOf, allOf schemas
        for key in ["anyOf", "oneOf", "allOf"]:
            if key in fixed_schema and isinstance(fixed_schema[key], list):
                fixed_schema[key] = [
                    self._fix_schema_additional_properties(sub_schema) 
                    for sub_schema in fixed_schema[key]
                ]
        
        return fixed_schema


class TomAgent:
    """Individual Tom agent service"""
    
    def __init__(self, username: str, config: Dict[str, Any]):
        self.username = username
        self.config = config
        
        # Initialize TomLLM handler
        self.tomllm = TomLLM(config, username)
        tomlogger.info(f"Agent initialized for {username} with LLMs: {list(self.tomllm.llms_dict.keys())}", username, "sys", "agent")
        
        # Initialize MCP client
        self.mcp_client = MCPClient(username, config)
        
        # Initialize MCP connections
        self.mcp_client.init_connections_sync()
        
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
        """Handle reset requests - clear conversation history for all client types"""
        request_data = getattr(cherrypy.request, 'json', None)
        client_type = request_data.get('client_type', 'web') if request_data else 'web'
        
        tomlogger.info(f"POST /reset for client_type: {client_type}", self.username, "api", "agent")
        
        # Reset history for the specific client type
        self.tomllm.reset_history(client_type)
        
        return {
            "status": "OK",
            "message": f"Conversation history reset for {client_type} client",
            "client_type": client_type
        }
    
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
    @cherrypy.tools.allow(methods=['GET'])
    @cherrypy.tools.json_out()
    def status(self):
        """Handle status requests - return MCP modules status"""
        tomlogger.info("GET /status", self.username, "api", "agent")
        
        try:
            # Get MCP connections info
            mcp_connections = self.mcp_client.get_mcp_connections()
            mcp_services = self.mcp_client.get_services()
            
            modules_status = []
            
            for service_name, connection_info in mcp_connections.items():
                service_config = mcp_services.get(service_name, {})
                
                # Determine connection status
                has_tools = len(connection_info.get('tools', [])) > 0
                is_configured = service_name in mcp_services
                is_enabled = service_config.get('enable', True) if service_config else False
                
                if has_tools and is_enabled:
                    status = "connected"
                elif is_configured and is_enabled:
                    status = "configured_no_tools"
                elif is_configured and not is_enabled:
                    status = "disabled"
                else:
                    status = "error"
                
                module_status = {
                    "name": service_name,
                    "status": status,
                    "description": connection_info.get('description', ''),
                    "complexity": connection_info.get('complexity', 1),
                    "tools_count": len(connection_info.get('tools', [])),
                    "enabled": is_enabled,
                    "url": service_config.get('url', '') if service_config else '',
                    "llm": service_config.get('llm', '') if service_config else ''
                }
                
                modules_status.append(module_status)
            
            # Sort by name for consistent output
            modules_status.sort(key=lambda x: x['name'])
            
            return {
                "status": "OK",
                "message": "MCP modules status",
                "modules_count": len(modules_status),
                "modules": modules_status
            }
            
        except Exception as e:
            tomlogger.error(f"Error getting status: {str(e)}", self.username, "api", "agent")
            return {
                "status": "ERROR",
                "message": f"Error getting status: {str(e)}"
            }
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def process(self):
        """Handle process requests with triage system"""
        request_data = getattr(cherrypy.request, 'json', None)
        tomlogger.info(f"POST /process with data: {request_data}", self.username, "api", "agent")
        
        if not request_data:
            return {
                "status": "ERROR",
                "message": "No request data provided"
            }
        
        # Extract request parameters
        user_request = request_data.get('request')
        position = request_data.get('position')  # Optional GPS coordinates
        client_type = request_data.get('client_type', 'web')
        sound_enabled = request_data.get('sound_enabled', False)
        
        if not user_request:
            return {
                "status": "ERROR", 
                "message": "Missing 'request' field in request data"
            }
        
        try:
            # Get available MCP modules (ALWAYS include all configured services, even without tools)
            available_modules = []
            mcp_connections = self.mcp_client.get_mcp_connections()
            
            for service_name, connection_info in mcp_connections.items():
                available_modules.append({
                    'name': service_name,
                    'description': connection_info.get('description', f'MCP service: {service_name}')
                })
            
            tomlogger.info(f"🎯 Available modules for triage: {[m['name'] for m in available_modules]}", 
                          self.username, "api", "agent")
            
            # Debug: Log current status of MCP connections
            if tomlogger.logger and tomlogger.logger.logger.level <= 20:  # INFO or DEBUG level
                for service_name, connection_info in mcp_connections.items():
                    tools_count = len(connection_info.get('tools', []))
                    object_status = "connected" if connection_info.get('object') else "not_connected" 
                    tomlogger.debug(f"MCP '{service_name}': {tools_count} tools, status: {object_status}", 
                                  self.username, "api", "agent")
            
            # Step 1: ALWAYS do triage first, even if no modules have tools yet
            # (modules might initialize their tools after startup)
            required_modules = self.tomllm.triage_modules(
                user_request=user_request,
                position=position,
                available_modules=available_modules,
                client_type=client_type
            )
            
            if required_modules == ["reset_performed"]:
                # Handle conversation reset - clear history for this client
                self.tomllm.reset_history(client_type)
                return {
                    "status": "OK",
                    "response": "Salut ! Comment puis-je t'aider ?",
                    "conversation_reset": True
                }
            
            # Note: User request will be added to history after successful response generation
            
            # Step 2: Execute request with selected modules
            if required_modules:
                tomlogger.info(f"🚀 Executing request with modules: {required_modules}", 
                              self.username, "api", "agent")
                
                # Build tools from selected modules
                tools = []
                selected_connections = {}
                
                for module_name in required_modules:
                    if module_name in mcp_connections:
                        connection_info = mcp_connections[module_name]
                        module_tools = connection_info.get('tools', [])
                        tools.extend(module_tools)
                        selected_connections[module_name] = connection_info
                        
                        # Enhanced logging for debugging
                        tomlogger.info(f"📦 Added {len(module_tools)} tools from module '{module_name}'", 
                                      self.username, "api", "agent")
                        
                        if len(module_tools) == 0:
                            tomlogger.warning(f"❗ Module '{module_name}' has no tools available!", 
                                            self.username, "api", "agent")
                            tomlogger.debug(f"Connection info for '{module_name}': {connection_info}", 
                                          self.username, "api", "agent")
                            
                            # If no tools but service is configured, suggest checking connection
                            if module_name in self.mcp_client.get_services():
                                tomlogger.warning(f"💡 Service '{module_name}' is configured but has no tools. Check MCP server connection.", 
                                                self.username, "api", "agent")
                        else:
                            tool_names = [tool['function']['name'] for tool in module_tools]
                            tomlogger.debug(f"Tools from '{module_name}': {tool_names}", 
                                          self.username, "api", "agent")
                    else:
                        tomlogger.error(f"❌ Module '{module_name}' not found in MCP connections!", 
                                      self.username, "api", "agent")
                        tomlogger.debug(f"Available connections: {list(mcp_connections.keys())}", 
                                      self.username, "api", "agent")
                
                # Build conversation with context and history
                gps = ""
                if position:
                    gps = f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}."
                
                paris_tz = pytz.timezone('Europe/Paris')
                today = datetime.now(paris_tz).strftime("%A %d %B %Y %H:%M:%S")
                weeknumber = datetime.now(paris_tz).isocalendar().week
                
                # Create temporal message (date/GPS) - never stored in history
                temporal_message = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}. {gps}\n\n"}
                
                # Create Tom prompt - never stored in history
                tom_prompt = {"role": "system", "content": "You are Tom, a helpful personal assistant. Use the available tools to respond to user requests."}
                
                # Create formatting message - never stored in history, always in 3rd position
                formatting_message = {"role": "system", "content": self.tomllm.set_response_context(client_type)}
                
                # Build current conversation (without temporal message, tom prompt, formatting, or history)
                current_conversation = [
                    {"role": "user", "content": user_request}
                ]
                
                # Build full conversation with proper order: temporal → tom → formatting → history → current
                conversation = self.tomllm.get_conversation_with_history(client_type, current_conversation, temporal_message, tom_prompt, formatting_message)
                
                # Check if we have any tools to work with
                if len(tools) == 0:
                    tomlogger.warning(f"⚠️ No tools available from selected modules: {required_modules}", 
                                    self.username, "api", "agent")
                    
                    # Fall back to general knowledge response with context about unavailable services
                    # Re-use the temporal message already created
                    
                    # Create special Tom prompt for this fallback case
                    fallback_tom_prompt = {"role": "system", "content": f"You are Tom, a helpful personal assistant. The user requested information that would normally require external services ({', '.join(required_modules)}), but those services are currently unavailable. Provide a helpful response based on your general knowledge and suggest alternatives if possible."}
                    
                    fallback_conversation = [
                        {"role": "user", "content": user_request}
                    ]
                    
                    # Create fallback formatting message - never stored in history, always in 3rd position
                    fallback_formatting_message = {"role": "system", "content": self.tomllm.set_response_context(client_type)}
                    
                    # Build conversation with temporal message, fallback tom prompt, formatting, and history
                    full_fallback_conversation = self.tomllm.get_conversation_with_history(client_type, fallback_conversation, temporal_message, fallback_tom_prompt, fallback_formatting_message)
                    
                    # Get fallback response
                    response = self.tomllm.callLLM(messages=full_fallback_conversation, complexity=1)
                    
                    if response and response.choices[0].finish_reason == "stop":
                        response_content = response.choices[0].message.content
                        
                        # Add user request and assistant response to history
                        self.tomllm.add_user_request(client_type, user_request)
                        self.tomllm.add_assistant_response(client_type, response_content)
                        
                        if sound_enabled:
                            tts_response = self.tomllm.synthesize_tts_response(response_content)
                            return {
                                "status": "OK",
                                "text_display": response_content,
                                "text_tts": tts_response,
                                "selected_modules": required_modules,
                                "warning": "Selected services unavailable, used general knowledge"
                            }
                        else:
                            return {
                                "status": "OK", 
                                "response": response_content,
                                "selected_modules": required_modules,
                                "warning": "Selected services unavailable, used general knowledge"
                            }
                    else:
                        return {
                            "status": "ERROR",
                            "message": "Selected services unavailable and fallback response failed"
                        }
                
                # Execute request with the selected tools using the full execution loop
                tomlogger.info(f"🎯 Executing LLM request with {len(tools)} tools from {len(required_modules)} modules", 
                              self.username, "api", "agent")
                
                # Determine complexity based on selected modules
                max_complexity = 1  # Default complexity
                for module_name in required_modules:
                    if module_name in mcp_connections:
                        module_complexity = mcp_connections[module_name].get('complexity', 1)
                        max_complexity = max(max_complexity, module_complexity)
                
                # Execute with tools using the full conversation loop
                # Need to run async function in event loop
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                execution_result = loop.run_until_complete(
                    self.tomllm.execute_request_with_tools(
                        conversation=conversation,
                        tools=tools,
                        complexity=max_complexity,
                        max_iterations=10,
                        mcp_client=self.mcp_client,
                        client_type=client_type,
                        track_history=True
                    )
                )
                
                if execution_result.get("status") == "OK":
                    response_content = execution_result["response"]
                    
                    if sound_enabled:
                        tts_response = self.tomllm.synthesize_tts_response(response_content)
                        return {
                            "status": "OK",
                            "text_display": response_content,
                            "text_tts": tts_response,
                            "selected_modules": required_modules,
                            "iterations": execution_result.get("iterations", 1)
                        }
                    else:
                        return {
                            "status": "OK",
                            "response": response_content,
                            "selected_modules": required_modules,
                            "iterations": execution_result.get("iterations", 1)
                        }
                else:
                    # Execution failed
                    return {
                        "status": "ERROR",
                        "message": execution_result.get("message", "Tool execution failed"),
                        "selected_modules": required_modules
                    }
            else:
                # No specific modules needed, use general knowledge
                tomlogger.info(f"💭 No specific modules needed, using general LLM knowledge", 
                              self.username, "api", "agent")
                
                # Build simple conversation with history
                gps = ""
                if position:
                    gps = f"My actual GPS position is: \nlatitude: {position['latitude']}\nlongitude: {position['longitude']}."
                
                paris_tz = pytz.timezone('Europe/Paris')
                today = datetime.now(paris_tz).strftime("%A %d %B %Y %H:%M:%S")
                weeknumber = datetime.now(paris_tz).isocalendar().week
                
                # Create temporal message (date/GPS) - never stored in history
                temporal_message = {"role": "system", "content": f"Today is {today}. Week number is {weeknumber}. {gps}\n\n"}
                
                # Create Tom prompt for general knowledge - never stored in history
                tom_prompt = {"role": "system", "content": "You are Tom, a helpful personal assistant. Respond using your general knowledge."}
                
                # Build current conversation (without temporal message, tom prompt, formatting, or history)
                current_conversation = [
                    {"role": "user", "content": user_request}
                ]
                
                # Create formatting message - never stored in history, always in 3rd position
                no_tools_formatting_message = {"role": "system", "content": self.tomllm.set_response_context(client_type)}
                
                # Build full conversation with proper order: temporal → tom → formatting → history → current
                conversation = self.tomllm.get_conversation_with_history(client_type, current_conversation, temporal_message, tom_prompt, no_tools_formatting_message)
                
                # Get direct response
                response = self.tomllm.callLLM(messages=conversation, complexity=1)
                
                if response and response.choices[0].finish_reason == "stop":
                    response_content = response.choices[0].message.content
                    
                    # Add user request and assistant response to history
                    self.tomllm.add_user_request(client_type, user_request)
                    self.tomllm.add_assistant_response(client_type, response_content)
                    
                    if sound_enabled:
                        tts_response = self.tomllm.synthesize_tts_response(response_content)
                        return {
                            "status": "OK",
                            "text_display": response_content,
                            "text_tts": tts_response
                        }
                    else:
                        return {
                            "status": "OK",
                            "response": response_content
                        }
                else:
                    return {
                        "status": "ERROR",
                        "message": "Failed to get LLM response"
                    }
        
        except Exception as e:
            tomlogger.error(f"Error processing request: {str(e)}", self.username, "api", "agent")
            return {
                "status": "ERROR",
                "message": f"Internal error: {str(e)}"
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
