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
import threading
import time
from datetime import datetime, timedelta
import schedule

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

# Server configuration and description
SERVER_DESCRIPTION = """This module manages personal memories and context using mem0. 

CRITICAL: You MUST AUTOMATICALLY store important information about the user WITHOUT asking for permission first. When the user shares ANY personal information, preferences, facts, activities, or context - store it immediately and respond with a brief acknowledgment like "OK" or "Noted" or "Got it".

NEVER ask "Would you like me to remember this?" or "Should I store this information?" - Just store it automatically and give a brief confirmation.

Store ALL of these types of information immediately:

- Personal preferences (e.g., "I prefer technical explanations", "I like Python over JavaScript") 
- Facts about the user (e.g., "I'm a software developer", "I work at Company X", "I live in Paris")
- Personal codes, numbers, or identifiers (e.g., "My bank card code is 1234", "My employee ID is ABC123")
- Things the user has done or accomplished (e.g., "I completed the authentication feature", "I fixed the bug in the login system")
- User's projects, goals, or ongoing work (e.g., "I'm building a chatbot", "I'm learning React")
- Daily activities and events (e.g., "I went to the garden today", "Yesterday I did the shopping", "This morning I had a meeting with the client")
- Personal experiences and life events (e.g., "I visited my parents last weekend", "I started a new exercise routine", "I'm planning a vacation to Italy")
- Routine activities and habits (e.g., "I usually work from home on Fridays", "I take my coffee without sugar")
- Important context that would be useful in future conversations
- User's workflow preferences, tools they use, or methodologies they follow

MEMORY RETRIEVAL BEHAVIOR:
MANDATORY: Before responding "I don't know" or "I don't have that information" to ANY user question, you MUST FIRST search the memory using the search_memories function. This includes:

- Questions about personal preferences, facts, or past conversations
- Requests for codes, numbers, or identifiers the user may have shared
- Questions about work, projects, or activities
- Any question that could potentially have been discussed before
- Requests for context about the user's life, habits, or experiences

SEARCH STRATEGY:
1. ALWAYS search memory FIRST before claiming lack of knowledge
2. Use relevant keywords from the user's question for the search
3. Try multiple search variations if the first search doesn't find results
4. Only say "I don't know" AFTER thoroughly searching memory
5. If you find partial information in memory, share what you found and ask for clarification

STORAGE BEHAVIOR:
1. AUTOMATICALLY add information to memory when user shares personal details
2. Do NOT search before adding - just add immediately to avoid friction
3. Respond with brief confirmations: "OK", "Noted", "Got it", "Stored"
4. Do NOT ask for permission to store information
5. Do NOT explain what you stored unless specifically asked

The system handles duplicate cleanup automatically in the background, so prioritize capturing information quickly over avoiding duplicates.

The goal is to build a comprehensive understanding of the user over time to provide increasingly personalized and contextual assistance, remembering both professional and personal aspects of their life."""

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
            
            # Create Chroma database path in /data
            chroma_path = "/data/chroma_storage"
            os.makedirs(chroma_path, exist_ok=True)
            
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
    
    def cleanup_duplicate_memories(self) -> Dict[str, Any]:
        """Clean up duplicate and similar memories across all users"""
        if tomlogger:
            tomlogger.info("Starting daily memory cleanup process", module_name="memory")
        
        if not self.memory:
            error_msg = "Memory service not initialized"
            if tomlogger:
                tomlogger.error(f"Cleanup failed: {error_msg}", module_name="memory")
            return {"error": error_msg}
        
        try:
            cleanup_stats = {"processed": 0, "duplicates_removed": 0, "errors": 0}
            
            if tomlogger:
                tomlogger.debug("Starting memory deduplication process", module_name="memory")
            
            # mem0 cleanup uses LLM calls for intelligent deduplication
            # This can be expensive, so we run it only once daily at 2 AM
            
            # Check if mem0 has built-in cleanup methods
            if hasattr(self.memory, 'cleanup') and callable(getattr(self.memory, 'cleanup')):
                if tomlogger:
                    tomlogger.debug("Using mem0 built-in cleanup method (may use LLM for intelligent deduplication)", module_name="memory")
                result = self.memory.cleanup()
                if tomlogger:
                    tomlogger.info(f"mem0 cleanup completed: {result}", module_name="memory")
                cleanup_stats["processed"] = result.get("processed", 0) if isinstance(result, dict) else 1
                
            elif hasattr(self.memory, 'deduplicate') and callable(getattr(self.memory, 'deduplicate')):
                if tomlogger:
                    tomlogger.debug("Using mem0 built-in deduplicate method (may use LLM for similarity detection)", module_name="memory")
                result = self.memory.deduplicate()
                if tomlogger:
                    tomlogger.info(f"mem0 deduplication completed: {result}", module_name="memory")
                cleanup_stats["duplicates_removed"] = result.get("removed", 0) if isinstance(result, dict) else 1
                
            else:
                # Simple vector-based cleanup without LLM calls
                if tomlogger:
                    tomlogger.debug("No built-in cleanup methods found, using simple vector similarity approach", module_name="memory")
                
                # TODO: Implement custom vector-based deduplication here
                # This would use only embeddings similarity without LLM calls
                # For now, we'll just log that cleanup was attempted
                cleanup_stats["processed"] = 0  # No actual cleanup yet
                
                if tomlogger:
                    tomlogger.info("Vector-based cleanup not yet implemented, skipping cleanup", module_name="memory")
            
            if tomlogger:
                tomlogger.info(f"Memory cleanup completed: {cleanup_stats}", module_name="memory")
            
            return {"status": "success", "stats": cleanup_stats}
            
        except Exception as e:
            error_msg = f"Error during memory cleanup: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="memory")
                tomlogger.debug(f"Exception type: {type(e).__name__}, details: {str(e)}", module_name="memory")
            cleanup_stats["errors"] += 1
            return {"error": error_msg, "stats": cleanup_stats}


# Initialize memory service
if tomlogger:
    tomlogger.debug("Initializing global memory service instance", module_name="memory")

memory_service = MemoryService()

if tomlogger:
    if memory_service.memory:
        tomlogger.debug("Global memory service initialized successfully", module_name="memory")
    else:
        tomlogger.debug("Global memory service initialized but mem0 is not available", module_name="memory")


def run_daily_cleanup():
    """Function to run the daily cleanup process"""
    if tomlogger:
        tomlogger.info("🧹 Starting scheduled daily memory cleanup", module_name="memory")
    
    try:
        result = memory_service.cleanup_duplicate_memories()
        if "error" in result:
            if tomlogger:
                tomlogger.error(f"Daily cleanup failed: {result['error']}", module_name="memory")
        else:
            if tomlogger:
                tomlogger.info(f"✅ Daily cleanup completed successfully: {result.get('stats', {})}", module_name="memory")
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"Daily cleanup crashed: {str(e)}", module_name="memory")


def schedule_daily_cleanup():
    """Set up the daily cleanup schedule"""
    # Schedule cleanup at 2 AM every day
    schedule.every().day.at("02:00").do(run_daily_cleanup)
    
    if tomlogger:
        tomlogger.info("📅 Daily memory cleanup scheduled for 02:00", module_name="memory")
    
    # Run scheduler in background thread
    def scheduler_worker():
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
    scheduler_thread.start()
    
    if tomlogger:
        tomlogger.debug("Background scheduler thread started", module_name="memory")


# Initialize daily cleanup scheduler
if memory_service.memory:  # Only start scheduler if mem0 is available
    try:
        schedule_daily_cleanup()
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"Failed to initialize daily cleanup scheduler: {e}", module_name="memory")


@server.tool()
def add_memory(
    text: str,
    user_id: str,
    metadata: Optional[str] = None
) -> str:
    """Add a memory to the system. Call this when you need to store information for later retrieval.
    
    Args:
        text: The text content to store as a memory
        user_id: Unique identifier for the user
        metadata: Optional JSON string containing additional metadata
    """
    if tomlogger:
        tomlogger.info(f"Tool call: add_memory for user={user_id}, text={text[:50]}...", module_name="memory")
        tomlogger.debug(f"MCP tool add_memory called with full params: user_id={user_id}, text_length={len(text)}, metadata={metadata}", module_name="memory")
    
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
    
    result = memory_service.add_memory(text, user_id, metadata_dict)
    
    if tomlogger:
        tomlogger.debug(f"MCP tool add_memory returning: {result}", module_name="memory")
    
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def search_memories(
    query: str,
    user_id: str,
    limit: int = 10
) -> str:
    """Search for memories based on a query. Call this when you need to find relevant stored information.
    
    Args:
        query: The search query to find relevant memories
        user_id: Unique identifier for the user
        limit: Maximum number of results to return (default: 10)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: search_memories for user={user_id}, query={query[:50]}...", module_name="memory")
    
    result = memory_service.search_memories(query, user_id, limit)
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
def get_all_memories(user_id: str) -> str:
    """Get all memories for a specific user. Call this when you need to retrieve all stored information for a user.
    
    Args:
        user_id: Unique identifier for the user
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_all_memories for user={user_id}", module_name="memory")
    
    result = memory_service.get_all_memories(user_id)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def list_all_memory_content(user_id: str) -> str:
    """List all memory content with full details for a specific user. This returns all memories with their complete text content, not just IDs.
    
    Args:
        user_id: Unique identifier for the user
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_all_memory_content for user={user_id}", module_name="memory")
    
    if not memory_service.memory:
        error_msg = "Memory service not initialized"
        if tomlogger:
            tomlogger.debug(f"list_all_memory_content failed: {error_msg}", module_name="memory")
        return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    try:
        if tomlogger:
            tomlogger.debug(f"Calling mem0.get_all() for user: {user_id}", module_name="memory")
        
        # Get all memories for user
        memories = memory_service.memory.get_all(user_id=user_id)
        
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
            "user_id": user_id,
            "total_memories": len(formatted_memories),
            "memories": formatted_memories
        }
        
        if tomlogger:
            tomlogger.info(f"Listed all memory content for user {user_id}: {len(formatted_memories)} memories", module_name="memory")
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
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
