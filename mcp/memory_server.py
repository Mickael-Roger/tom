#!/usr/bin/env python3
"""
Memory MCP Server
Provides memory management functionality via MCP protocol using mem0
Based on the weather_server.py structure
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional
import yaml
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Memory library import (may fail if not installed)
try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    Memory = None
    MEM0_AVAILABLE = False

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO').strip() or 'INFO'
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Memory MCP Server starting with log level: {log_level}", module_name="memory")
    tomlogger.debug(f"Environment TOM_LOG_LEVEL: '{os.environ.get('TOM_LOG_LEVEL', 'not set')}'", module_name="memory")
else:
    logger = logging.getLogger(__name__)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

# Validate required environment variables
TOM_USER = os.environ.get('TOM_USER')
if not TOM_USER or not TOM_USER.strip():
    error_msg = "❌ TOM_USER environment variable is required but not set. Memory service cannot start."
    if tomlogger:
        tomlogger.error(error_msg, module_name="memory")
    else:
        print(error_msg)
    sys.exit(1)

TOM_USER = TOM_USER.strip()
if tomlogger:
    tomlogger.info(f"✅ Memory service initialized for user: {TOM_USER}", module_name="memory")

# Server configuration and description
SERVER_DESCRIPTION = """This module manages personal memories and context using mem0. Only load this module when the user explicitly requests memory-related operations such as storing information, searching memories, or managing stored data.

It provides functions to store, search, delete, and manage user memories. The memory system automatically processes conversations to extract and store relevant information about users."""

# Initialize FastMCP server
server = FastMCP(name="memory-server", stateless_http=True, host="0.0.0.0", port=80)


class MemoryService:
    """Memory service class using mem0"""
    
    def __init__(self):
        self.config = self._load_config()
        self.memory = None
        self._initialize_memory()
        
        if tomlogger:
            tomlogger.info("Memory service initialized with mem0", module_name="memory")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from /config.yml"""
        config_path = '/config.yml'
        if tomlogger:
            tomlogger.debug(f"Attempting to load config from: {config_path}", module_name="memory")
        
        try:
            if os.path.exists(config_path):
                if tomlogger:
                    tomlogger.debug(f"Config file exists, reading contents", module_name="memory")
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if tomlogger:
                        tomlogger.info(f"Configuration loaded from {config_path}", module_name="memory")
                        tomlogger.debug(f"Config keys found: {list(config.keys()) if config else 'None'}", module_name="memory")
                        if config and 'memory' in config:
                            memory_config = config['memory']
                            tomlogger.debug(f"Memory config keys: {list(memory_config.keys())}", module_name="memory")
                        else:
                            tomlogger.debug("No 'memory' section found in config", module_name="memory")
                    return config
            else:
                if tomlogger:
                    tomlogger.debug(f"Config file does not exist at {config_path}", module_name="memory")
        except (yaml.YAMLError, IOError) as e:
            if tomlogger:
                tomlogger.error(f"Error loading config: {e}", module_name="memory")
            else:
                print(f"Error loading config: {e}")
        return {}
    
    def _initialize_memory(self):
        """Initialize mem0 with configuration"""
        if tomlogger:
            tomlogger.debug("Starting mem0 initialization", module_name="memory")
        
        try:
            # Check if mem0 is available
            if tomlogger:
                tomlogger.debug(f"Checking mem0 availability: {MEM0_AVAILABLE}", module_name="memory")
            
            if not MEM0_AVAILABLE or Memory is None:
                raise ImportError("mem0 library not available")
            
            # Set up environment variables from config
            memory_config = self.config.get('memory', {})
            if tomlogger:
                tomlogger.debug(f"Memory config section: {memory_config}", module_name="memory")
            
            # Set up environment variables that mem0 recognizes
            openai_key = memory_config.get('openai_api_key')
            if openai_key:
                os.environ['OPENAI_API_KEY'] = openai_key
                if tomlogger:
                    tomlogger.debug("OpenAI API key set from config", module_name="memory")
            elif 'OPENAI_API_KEY' in os.environ:
                if tomlogger:
                    tomlogger.debug("Using existing OPENAI_API_KEY from environment", module_name="memory")
            else:
                if tomlogger:
                    tomlogger.debug("No OpenAI API key found in config or environment", module_name="memory")
            
            openrouter_key = memory_config.get('openrouter_api_key')
            if openai_key:
                os.environ['OPENROUTER_API_KEY'] = openrouter_key
                if tomlogger:
                    tomlogger.debug("Openrouter API key set from config", module_name="memory")
            elif 'OPENROUTER_API_KEY' in os.environ:
                if tomlogger:
                    tomlogger.debug("Using existing OPENROUTER_API_KEY from environment", module_name="memory")
            else:
                if tomlogger:
                    tomlogger.debug("No Openrouer API key found in config or environment", module_name="memory")
            
            # Create Chroma database path in /data
            chroma_path = "/data/chroma_storage"
            os.makedirs(chroma_path, exist_ok=True)
            kuzu_dir_path = "/data/kuzu_storage"
            os.makedirs(kuzu_dir_path, exist_ok=True)
            kuzu_path=kuzu_dir_path + "/kuzu.db"
            
            # Get LLM and embedder configuration
            llm_provider = memory_config.get('llm_provider', 'openai')
            llm_model = memory_config.get('llm_model', 'gpt-4o-mini')
            embedder_provider = memory_config.get('embedder_provider', 'openai')
            embedder_model = memory_config.get('embedder_model', 'text-embedding-ada-002')
            
            # Create mem0 configuration using official documentation structure
            config_dict = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "memories",
                        "path": chroma_path
                    }
                },
                "llm": {
                    "provider": llm_provider,
                    "config": {
                        "model": llm_model
                    }
                },
                "embedder": {
                    "provider": embedder_provider,
                    "config": {
                        "model": embedder_model
                    }
                },
                "graph_store": {
                    "provider": "kuzu",
                    "config": {
                        "db": kuzu_path
                    }
                }
            }
            
            if tomlogger:
                tomlogger.debug(f"LLM config: provider={llm_provider}, model={llm_model}", module_name="memory")
                tomlogger.debug(f"Embedder config: provider={embedder_provider}, model={embedder_model}", module_name="memory")
                tomlogger.debug(f"Chroma path: {chroma_path}", module_name="memory")
                tomlogger.debug(f"Full mem0 config: {config_dict}", module_name="memory")
            
            # Initialize mem0 using from_config method as per documentation
            if tomlogger:
                tomlogger.debug("Initializing mem0 with Chroma using Memory.from_config()", module_name="memory")
            
            self.memory = Memory.from_config(config_dict)
            
            if tomlogger:
                tomlogger.debug("mem0 initialized successfully with Chroma configuration", module_name="memory")
                
                # Check where mem0 is actually storing data
                try:
                    if hasattr(self.memory, 'vector_store'):
                        vs = self.memory.vector_store
                        tomlogger.debug(f"Vector store type: {type(vs).__name__}", module_name="memory")
                        
                        # Check for storage path
                        for attr in ['path', '_path', 'persist_directory', '_persist_directory', 'collection_path']:
                            if hasattr(vs, attr):
                                path_value = getattr(vs, attr)
                                tomlogger.debug(f"Vector store {attr}: {path_value}", module_name="memory")
                except Exception as e:
                    tomlogger.debug(f"Could not inspect vector store: {e}", module_name="memory")
            
            if tomlogger:
                tomlogger.info(f"Mem0 initialized with provider: {llm_provider}, model: {llm_model}", module_name="memory")
                tomlogger.debug(f"Memory object created successfully", module_name="memory")
                
        except ImportError as e:
            if tomlogger:
                tomlogger.error(f"mem0 not installed: {e}", module_name="memory")
                tomlogger.debug(f"ImportError details: {str(e)}", module_name="memory")
            else:
                print(f"mem0 not installed: {e}")
            self.memory = None
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing mem0: {e}", module_name="memory")
                tomlogger.debug(f"Exception type: {type(e).__name__}", module_name="memory")
                tomlogger.debug(f"Exception details: {str(e)}", module_name="memory")
            else:
                print(f"Error initializing mem0: {e}")
            self.memory = None
    
    def add_memory(self, text: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add a memory to the system"""
        if tomlogger:
            tomlogger.debug(f"add_memory called with user_id={user_id}, text_length={len(text)}, metadata={metadata}", module_name="memory")
        
        if not self.memory:
            error_msg = "Memory service not initialized"
            if tomlogger:
                tomlogger.debug(f"add_memory failed: {error_msg}", module_name="memory")
            return {"error": error_msg}
        
        try:
            if tomlogger:
                tomlogger.debug(f"Calling mem0.add() with text: '{text[:100]}...' for user: {user_id}", module_name="memory")
            
            # Add memory with user_id
            result = self.memory.add(text, user_id=user_id, metadata=metadata)
            
            if tomlogger:
                tomlogger.info(f"Memory added for user {user_id}: {text[:50]}...", module_name="memory")
                tomlogger.debug(f"mem0.add() result: {result}", module_name="memory")
                
                # Check where data is stored
                try:
                    # List files in /data for verification
                    data_files = []
                    for root, dirs, files in os.walk("/data"):
                        for file in files:
                            data_files.append(os.path.join(root, file))
                        for dir in dirs:
                            data_files.append(f"{os.path.join(root, dir)}/")
                    tomlogger.debug(f"Contents in /data after add_memory: {data_files}", module_name="memory")
                    
                except Exception as e:
                    tomlogger.debug(f"Could not check file system: {e}", module_name="memory")
            
            return {"status": "success", "result": result}
            
        except Exception as e:
            error_msg = f"Error adding memory: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="memory")
                tomlogger.debug(f"Exception type: {type(e).__name__}, details: {str(e)}", module_name="memory")
            return {"error": error_msg}
    
    def search_memories(self, query: str, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Search memories for a user"""
        if tomlogger:
            tomlogger.debug(f"search_memories called with user_id={user_id}, query='{query[:50]}...', limit={limit}", module_name="memory")
        
        if not self.memory:
            error_msg = "Memory service not initialized"
            if tomlogger:
                tomlogger.debug(f"search_memories failed: {error_msg}", module_name="memory")
            return {"error": error_msg}
        
        try:
            if tomlogger:
                tomlogger.debug(f"Calling mem0.search() for user: {user_id}", module_name="memory")
            
            # Search memories
            results = self.memory.search(query=query, user_id=user_id, limit=limit)
            
            if tomlogger:
                tomlogger.info(f"Memory search for user {user_id}: {query[:50]}... (found {len(results)} results)", module_name="memory")
                tomlogger.debug(f"Search results: {results}", module_name="memory")
            
            return {"status": "success", "results": results, "count": len(results)}
            
        except Exception as e:
            error_msg = f"Error searching memories: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="memory")
                tomlogger.debug(f"Exception type: {type(e).__name__}, details: {str(e)}", module_name="memory")
            return {"error": error_msg}
    
    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Delete a specific memory by ID"""
        if tomlogger:
            tomlogger.debug(f"delete_memory called with memory_id={memory_id}", module_name="memory")
        
        if not self.memory:
            error_msg = "Memory service not initialized"
            if tomlogger:
                tomlogger.debug(f"delete_memory failed: {error_msg}", module_name="memory")
            return {"error": error_msg}
        
        try:
            if tomlogger:
                tomlogger.debug(f"Calling mem0.delete() for memory_id: {memory_id}", module_name="memory")
            
            # Delete memory
            result = self.memory.delete(memory_id=memory_id)
            
            if tomlogger:
                tomlogger.info(f"Memory deleted: {memory_id}", module_name="memory")
                tomlogger.debug(f"Delete result: {result}", module_name="memory")
            
            return {"status": "success", "result": result}
            
        except Exception as e:
            error_msg = f"Error deleting memory: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="memory")
                tomlogger.debug(f"Exception type: {type(e).__name__}, details: {str(e)}", module_name="memory")
            return {"error": error_msg}
    
    def get_all_memories(self, user_id: str) -> Dict[str, Any]:
        """Get all memories for a user"""
        if tomlogger:
            tomlogger.debug(f"get_all_memories called with user_id={user_id}", module_name="memory")
        
        if not self.memory:
            error_msg = "Memory service not initialized"
            if tomlogger:
                tomlogger.debug(f"get_all_memories failed: {error_msg}", module_name="memory")
            return {"error": error_msg}
        
        try:
            if tomlogger:
                tomlogger.debug(f"Calling mem0.get_all() for user: {user_id}", module_name="memory")
            
            # Get all memories for user
            results = self.memory.get_all(user_id=user_id)
            
            if tomlogger:
                tomlogger.info(f"Retrieved all memories for user {user_id}: {len(results)} memories", module_name="memory")
                tomlogger.debug(f"get_all results: {results}", module_name="memory")
            
            return {"status": "success", "results": results, "count": len(results)}
            
        except Exception as e:
            error_msg = f"Error getting all memories: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="memory")
                tomlogger.debug(f"Exception type: {type(e).__name__}, details: {str(e)}", module_name="memory")
            return {"error": error_msg}
    


# Initialize memory service
if tomlogger:
    tomlogger.debug("Initializing global memory service instance", module_name="memory")

memory_service = MemoryService()

if tomlogger:
    if memory_service.memory:
        tomlogger.debug("Global memory service initialized successfully", module_name="memory")
    else:
        tomlogger.debug("Global memory service initialized but mem0 is not available", module_name="memory")




@server.tool()
def add_memory(
    text: str,
    metadata: Optional[str] = None
) -> str:
    """Add a memory to the system. Call this when you need to store information for later retrieval.
    
    Args:
        text: The text content to store as a memory
        metadata: Optional JSON string containing additional metadata
    """
    if tomlogger:
        tomlogger.info(f"Tool call: add_memory for user={TOM_USER}, text={text[:50]}...", module_name="memory")
        tomlogger.debug(f"MCP tool add_memory called with full params: user_id={TOM_USER}, text_length={len(text)}, metadata={metadata}", module_name="memory")
    
    metadata_dict = None
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
            if tomlogger:
                tomlogger.debug(f"Metadata parsed successfully: {metadata_dict}", module_name="memory")
        except json.JSONDecodeError:
            if tomlogger:
                tomlogger.error(f"Invalid metadata JSON: {metadata}", module_name="memory")
            return json.dumps({"error": "Invalid metadata JSON format"})
    
    result = memory_service.add_memory(text, TOM_USER, metadata_dict)
    
    if tomlogger:
        tomlogger.debug(f"MCP tool add_memory returning: {result}", module_name="memory")
    
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def search_memories(
    query: str,
    limit: int = 10
) -> str:
    """Search for memories based on a query. Call this when you need to find relevant stored information.
    
    Args:
        query: The search query to find relevant memories
        limit: Maximum number of results to return (default: 10)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: search_memories for user={TOM_USER}, query={query[:50]}...", module_name="memory")
    
    result = memory_service.search_memories(query, TOM_USER, limit)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def delete_memory(memory_id: str) -> str:
    """Delete a specific memory by its ID. Call this when you need to remove stored information.
    
    Args:
        memory_id: The unique identifier of the memory to delete
    """
    if tomlogger:
        tomlogger.info(f"Tool call: delete_memory with id={memory_id}", module_name="memory")
    
    result = memory_service.delete_memory(memory_id)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def get_all_memories() -> str:
    """Get all memories for the current user. Call this when you need to retrieve all stored information.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_all_memories for user={TOM_USER}", module_name="memory")
    
    result = memory_service.get_all_memories(TOM_USER)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def analyze_and_store_conversation(
    conversation: str
) -> str:
    """Analyze conversation history and automatically store relevant memories.
    
    Args:
        conversation: JSON string containing conversation history in format [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    """
    if tomlogger:
        tomlogger.info(f"Tool call: analyze_and_store_conversation for user={TOM_USER}", module_name="memory")
    
    try:
        import json
        
        # Parse the conversation JSON
        conversation_data = json.loads(conversation)
        
        if not isinstance(conversation_data, list):
            return json.dumps({"error": "Conversation must be a list of messages"}, ensure_ascii=False)
        
        # Filter to only user and assistant messages with content
        filtered_conversation = []
        for msg in conversation_data:
            if (isinstance(msg, dict) and 
                msg.get('role') in ['user', 'assistant'] and 
                isinstance(msg.get('content'), str) and 
                msg['content'].strip()):
                filtered_conversation.append(msg)
        
        if not filtered_conversation:
            return json.dumps({"status": "success", "message": "No meaningful conversation to analyze"}, ensure_ascii=False)
        
        # Convert conversation to text format for mem0
        conversation_text = ""
        for msg in filtered_conversation:
            role = msg['role']
            content = msg['content'].strip()
            conversation_text += f"{role}: {content}\n"
        
        if tomlogger:
            tomlogger.debug(f"Analyzing conversation text: {conversation_text[:200]}...", module_name="memory")
        
        # Add the conversation to mem0 - let mem0 handle the analysis and extraction
        result = memory_service.add_memory(conversation_text, TOM_USER)
        
        if tomlogger:
            tomlogger.info(f"Conversation analysis completed for user {TOM_USER}", module_name="memory")
        
        return json.dumps(result, ensure_ascii=False)
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid conversation JSON format: {str(e)}"
        if tomlogger:
            tomlogger.error(error_msg, module_name="memory")
        return json.dumps({"error": error_msg}, ensure_ascii=False)
    except Exception as e:
        error_msg = f"Error analyzing conversation: {str(e)}"
        if tomlogger:
            tomlogger.error(error_msg, module_name="memory")
        return json.dumps({"error": error_msg}, ensure_ascii=False)


# HTTP Server for REST API
import cherrypy
from threading import Thread

class MemoryRestAPI:
    """REST API for memory management using CherryPy"""
    
    def __init__(self, memory_service, tom_user):
        self.memory_service = memory_service
        self.tom_user = tom_user
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.allow(methods=['GET'])
    def memories(self):
        """GET /memories - Get all memories"""
        if tomlogger:
            tomlogger.info(f"REST API: GET /memories for user={self.tom_user}", module_name="memory")
        
        result = self.memory_service.get_all_memories(self.tom_user)
        
        if "error" in result:
            cherrypy.response.status = 500
        
        return result
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.tools.allow(methods=['POST'])
    def search(self):
        """POST /search - Search memories"""
        try:
            request_data = cherrypy.request.json
            
            if tomlogger:
                query_preview = request_data.get('query', '')[:50] if request_data.get('query') else ''
                tomlogger.info(f"REST API: POST /search for user={self.tom_user}, query={query_preview}...", module_name="memory")
            
            query = request_data.get("query")
            limit = request_data.get("limit", 10)
            
            if not query:
                cherrypy.response.status = 400
                return {"error": "Query parameter is required"}
            
            result = self.memory_service.search_memories(query, self.tom_user, limit)
            
            if "error" in result:
                cherrypy.response.status = 500
            
            return result
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"REST API search error: {str(e)}", module_name="memory")
            cherrypy.response.status = 500
            return {"error": f"Search failed: {str(e)}"}
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.tools.allow(methods=['POST'])
    def add(self):
        """POST /add - Add a new memory"""
        try:
            request_data = cherrypy.request.json
            
            if tomlogger:
                tomlogger.info(f"REST API: POST /add for user={self.tom_user}", module_name="memory")
            
            text = request_data.get("text")
            metadata = request_data.get("metadata")
            
            if not text:
                cherrypy.response.status = 400
                return {"error": "Text parameter is required"}
            
            result = self.memory_service.add_memory(text, self.tom_user, metadata)
            
            if "error" in result:
                cherrypy.response.status = 500
            else:
                cherrypy.response.status = 201
            
            return result
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"REST API add memory error: {str(e)}", module_name="memory")
            cherrypy.response.status = 500
            return {"error": f"Add memory failed: {str(e)}"}
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.allow(methods=['GET'])
    def memory(self, memory_id):
        """GET /memory/{id} - Get single memory by ID"""
        if tomlogger:
            tomlogger.info(f"REST API: GET /memory/{memory_id}", module_name="memory")
        
        try:
            # Get all memories and find the specific one
            all_memories_result = self.memory_service.get_all_memories(self.tom_user)
            
            if "error" in all_memories_result:
                cherrypy.response.status = 500
                return {"error": all_memories_result["error"]}
            
            # Find the memory with the specified ID
            memories = all_memories_result.get("results", [])
            target_memory = None
            
            for memory in memories:
                if memory.get("id") == memory_id:
                    target_memory = memory
                    break
            
            if not target_memory:
                cherrypy.response.status = 404
                return {"error": f"Memory with ID '{memory_id}' not found"}
            
            return {
                "status": "success",
                "result": target_memory
            }
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"REST API get memory error: {str(e)}", module_name="memory")
            cherrypy.response.status = 500
            return {"error": f"Get memory failed: {str(e)}"}
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.allow(methods=['DELETE'])
    def delete(self, memory_id):
        """DELETE /delete/{id} - Delete memory by ID"""
        if tomlogger:
            tomlogger.info(f"REST API: DELETE /delete/{memory_id}", module_name="memory")
        
        result = self.memory_service.delete_memory(memory_id)
        
        if "error" in result:
            cherrypy.response.status = 500
        
        return result


def start_rest_api(memory_service, tom_user, port=8080):
    """Start the REST API server in a separate thread"""
    try:
        if tomlogger:
            tomlogger.info(f"Starting REST API server on port {port}", module_name="memory")
        
        # Configure CherryPy
        cherrypy.config.update({
            'server.socket_host': '0.0.0.0',
            'server.socket_port': port,
            'log.screen': False,
            'log.access_file': '',
            'log.error_file': '',
            'engine.autoreload.on': False
        })
        
        # Create API instance
        api = MemoryRestAPI(memory_service, tom_user)
        
        # Mount the API
        cherrypy.tree.mount(api, '/', {
            '/': {
                'tools.response_headers.on': True,
                'tools.response_headers.headers': [('Content-Type', 'application/json')],
            }
        })
        
        # Start the server
        cherrypy.engine.start()
        cherrypy.engine.wait(cherrypy.engine.states.STARTED)
        
        if tomlogger:
            tomlogger.info(f"✅ REST API server started successfully on port {port}", module_name="memory")
            
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"❌ Failed to start REST API server: {str(e)}", module_name="memory")


# Start REST API server in background thread
def init_rest_api_background():
    """Initialize REST API in background thread"""
    api_thread = Thread(target=start_rest_api, args=(memory_service, TOM_USER), daemon=True)
    api_thread.start()
    if tomlogger:
        tomlogger.info("REST API initialization thread started in background", module_name="memory")


@server.tool()
def list_all_memory_content() -> str:
    """List all memory content with full details for the current user. This returns all memories with their complete text content, not just IDs.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_all_memory_content for user={TOM_USER}", module_name="memory")
    
    if not memory_service.memory:
        error_msg = "Memory service not initialized"
        if tomlogger:
            tomlogger.debug(f"list_all_memory_content failed: {error_msg}", module_name="memory")
        return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    try:
        if tomlogger:
            tomlogger.debug(f"Calling mem0.get_all() for user: {TOM_USER}", module_name="memory")
        
        # Get all memories for user
        memories = memory_service.memory.get_all(user_id=TOM_USER)
        
        # Format the output to show all content clearly
        formatted_memories = []
        for i, memory in enumerate(memories, 1):
            formatted_memory = {
                "index": i,
                "id": memory.get("id", "unknown"),
                "content": memory.get("memory", memory.get("text", "No content")),
                "created_at": memory.get("created_at", "Unknown"),
                "updated_at": memory.get("updated_at", "Unknown"),
                "metadata": memory.get("metadata", {})
            }
            formatted_memories.append(formatted_memory)
        
        result = {
            "status": "success",
            "user_id": TOM_USER,
            "total_memories": len(formatted_memories),
            "memories": formatted_memories
        }
        
        if tomlogger:
            tomlogger.info(f"Listed all memory content for user {TOM_USER}: {len(formatted_memories)} memories", module_name="memory")
            tomlogger.debug(f"Memory content result: {result}", module_name="memory")
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_msg = f"Error listing all memory content: {str(e)}"
        if tomlogger:
            tomlogger.error(error_msg, module_name="memory")
            tomlogger.debug(f"Exception type: {type(e).__name__}, details: {str(e)}", module_name="memory")
        return json.dumps({"error": error_msg}, ensure_ascii=False)




@server.resource("description://memory")
def description() -> str:
    """Return server description"""
    return SERVER_DESCRIPTION


@server.resource("description://tom_notification")
def get_notification_status() -> str:
    """Return current memory service status for Tom's /tasks endpoint"""
    if not memory_service.memory:
        return "Memory service not initialized"
    
    # Return empty string when service is ready
    return ""


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Memory MCP Server on port 80", module_name="memory")
    else:
        print("Starting Memory MCP Server on port 80")
    
    # Start REST API in background
    init_rest_api_background()
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
