#!/usr/bin/env python3
"""
Claude Code MCP Server
Provides Claude Code project management functionality via MCP protocol
"""

import json
import os
import sys
import asyncio
from datetime import datetime
from typing import Any, Dict, List
import threading
import time

import cherrypy
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent
from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions

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
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Claude Code MCP Server starting with log level: {log_level}", module_name="claude_code")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for managing Claude Code projects and their execution status."

# Claude Code execution prompt template
CLAUDE_CODE_PROMPT = """@project_plan.md contains the request to be fulfilled.
Instructions:

- You will start by initializing a file named CLAUDE.md, which will contain all the information you need to complete this project.
- After each step, you will update the CLAUDE.md file.
- Throughout the project's progress (after each step), you will keep a JSON file project_status.json up to date.

The format of the @project_status.json file will be as follows:
```json
{
  "project_name": "NAME_OF_THE_PROJECT",
  "current_status": "STATUS",
  "last_status_update": "YYYY-MM-dd hh:mm:ss",
  "project_steps": [
    {"description": "TASK_DESCRIPTION", "start_at": "YYYY-MM-dd hh:mm:ss", "finished_at", null},
    {"description": "TASK_DESCRIPTION", "start_at": "YYYY-MM-dd hh:mm:ss", "finished_at", "YYYY-MM-dd hh:mm:ss"}
  ]
 }
 ```

 STATUS can take the following values:

 - "init": When you initialize the project (creation of the CLAUDE.md file)
 - "executing": When you are performing the project tasks
 - "error": When you are not able to finish the project and cannot go further
 - "finished": When the user's request is fully completed

If the request involves a website or any other web-based site, you will expose it using Python (ideally via the command `python3 -m http.server PORT --bind 127.0.0.1`).
IMPORTANT: If the development project you need to carry out involves exposing an application or a website, you must expose it over HTTP on one of the ports between 15000 and 15010, and only on localhost.
You can use the ss command if you want to check whether any of these ports are already in use. BE CAREFUL to always run `python -m http.server PORT` from inside the directory of the project (where the webpages resides)

In all cases where you expose a website, you must specify the port you used in the description of the corresponding task in the project_status.json file.

"""

# Initialize FastMCP server
server = FastMCP(name="code", stateless_http=True, host="0.0.0.0", port=80)


class ClaudeCodeService:
    """Claude Code service class for project management"""
    
    def __init__(self):
        # Ensure projects directory exists
        self.projects_dir = '/data/projects'
        os.makedirs(self.projects_dir, exist_ok=True)
        
        if tomlogger:
            tomlogger.info(f"Claude Code service initialized with projects directory: {self.projects_dir}", module_name="claude_code")
            tomlogger.debug(f"Projects directory exists: {os.path.exists(self.projects_dir)}", module_name="claude_code")
    
    def create_project(self, project_name: str, project_plan: str) -> Dict[str, Any]:
        """Create a new project with given name and plan"""
        try:
            if tomlogger:
                tomlogger.debug(f"create_project called with name='{project_name}', plan length={len(project_plan)}", module_name="claude_code")
                
            # Sanitize project name for filesystem
            safe_project_name = "".join(c for c in project_name if c.isalnum() or c in ('-', '_', ' ')).strip()
            if not safe_project_name:
                if tomlogger:
                    tomlogger.error(f"Invalid project name after sanitization: '{project_name}' -> '{safe_project_name}'", module_name="claude_code")
                return {"error": "Invalid project name"}
            
            project_path = os.path.join(self.projects_dir, safe_project_name)
            
            if tomlogger:
                tomlogger.debug(f"Project path: {project_path}", module_name="claude_code")
            
            # Create project directory
            os.makedirs(project_path, exist_ok=True)
            
            if tomlogger:
                tomlogger.debug(f"Created project directory: {project_path}", module_name="claude_code")
            
            # Write project plan as markdown
            plan_file = os.path.join(project_path, 'project_plan.md')
            with open(plan_file, 'w', encoding='utf-8') as f:
                f.write(f"# {project_name}\n\n")
                f.write(project_plan)
                
            if tomlogger:
                tomlogger.debug(f"Created project plan file: {plan_file}", module_name="claude_code")
            
            # Create initial project status
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_file = os.path.join(project_path, 'project_status.json')
            
            if tomlogger:
                tomlogger.debug(f"Creating initial status with timestamp: {current_time}", module_name="claude_code")
            initial_status = {
                "project_name": project_name,
                "current_status": "init",
                "last_status_update": current_time,
                "project_steps": [
                    {
                        "description": f"Initialize project '{project_name}'",
                        "start_at": current_time,
                        "finished_at": current_time
                    }
                ]
            }
            
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(initial_status, f, ensure_ascii=False, indent=2)
            
            if tomlogger:
                tomlogger.info(f"Project '{project_name}' created successfully at {project_path}", module_name="claude_code")
            
            if tomlogger:
                tomlogger.debug(f"Starting Claude Code SDK execution for project: {project_name}", module_name="claude_code")
                
            # Start Claude Code SDK execution in background
            import asyncio
            loop = asyncio.get_event_loop()
            task = loop.create_task(self._execute_claude_code_project(project_path))
            
            # Don't wait for completion - return immediately
            execution_result = {
                "success": True, 
                "status": "background_started",
                "message": "Claude Code execution started in background"
            }
            
            return {
                "success": True,
                "project_name": project_name,
                "project_path": project_path,
                "message": f"Project '{project_name}' created successfully",
                "claude_execution": execution_result
            }
            
        except Exception as e:
            error_msg = f"Error creating project '{project_name}': {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="claude_code")
            return {"error": error_msg}
    
    async def _execute_claude_code_project(self, project_path: str) -> Dict[str, Any]:
        """Execute Claude Code SDK in the project directory"""
        try:
            project_name = os.path.basename(project_path)
            if tomlogger:
                tomlogger.debug(f"_execute_claude_code_project called for: {project_path}", module_name="claude_code")
            
            # Setup debug logging file if in DEBUG mode
            debug_log_file = None
            log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO').upper()
            if log_level == 'DEBUG':
                debug_log_file = f"/tmp/debug_{project_name}.log"
                if tomlogger:
                    tomlogger.debug(f"Debug mode enabled, Claude output will be logged to: {debug_log_file}", module_name="claude_code")
            
            # Update project status to executing
            await self._update_project_status(project_path, "executing", "Starting Claude Code execution")
            
            if tomlogger:
                tomlogger.info(f"Starting Claude Code execution in {project_path}", module_name="claude_code")
                tomlogger.debug(f"Using Claude Code prompt length: {len(CLAUDE_CODE_PROMPT)}", module_name="claude_code")
            
            # Configure Claude Code SDK with full permissions
            options = ClaudeCodeOptions(
                system_prompt="You are a development assistant helping to execute project plans.",
                permission_mode="bypassPermissions",  # Allow all tools without prompting
                allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "LS", "WebFetch", "curl", "wget", "jq"]
            )
            
            if tomlogger:
                tomlogger.debug(f"Claude SDK configured with {len(options.allowed_tools)} tools", module_name="claude_code")
            
            async with ClaudeSDKClient(options=options) as client:
                if tomlogger:
                    tomlogger.debug(f"Claude SDK client created, sending query", module_name="claude_code")
                    
                # Change to project directory and send the prompt
                full_query = f"cd {project_path} && {CLAUDE_CODE_PROMPT}"
                
                if tomlogger:
                    tomlogger.debug(f"Sending query to Claude SDK: cd {project_path} && [PROMPT...]", module_name="claude_code")
                    
                await client.query(full_query)
                
                if tomlogger:
                    tomlogger.debug(f"Starting to collect Claude SDK response", module_name="claude_code")
                
                # Initialize debug file if enabled
                debug_file_handle = None
                if debug_log_file:
                    try:
                        debug_file_handle = open(debug_log_file, 'w', encoding='utf-8')
                        debug_file_handle.write(f"=== Claude Code Debug Log for {project_name} ===\n")
                        debug_file_handle.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        debug_file_handle.write(f"Project path: {project_path}\n")
                        debug_file_handle.write("=" * 50 + "\n\n")
                        debug_file_handle.flush()
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Failed to create debug log file: {e}", module_name="claude_code")
                        debug_file_handle = None
                
                # Collect response
                response_parts = []
                message_count = 0
                async for message in client.receive_response():
                    message_count += 1
                    if tomlogger and message_count % 10 == 0:
                        tomlogger.debug(f"Processed {message_count} response messages", module_name="claude_code")
                        
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if hasattr(block, 'text'):
                                text_content = block.text
                                response_parts.append(text_content)
                                
                                # Write to debug file if enabled
                                if debug_file_handle:
                                    try:
                                        debug_file_handle.write(text_content)
                                        debug_file_handle.flush()
                                    except Exception as e:
                                        if tomlogger:
                                            tomlogger.error(f"Failed to write to debug log: {e}", module_name="claude_code")
                
                # Close debug file
                if debug_file_handle:
                    try:
                        debug_file_handle.write(f"\n\n=== Execution completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                        debug_file_handle.close()
                        if tomlogger:
                            tomlogger.debug(f"Claude output saved to debug file: {debug_log_file}", module_name="claude_code")
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Failed to close debug log file: {e}", module_name="claude_code")
                
                full_response = "".join(response_parts)
                
                if tomlogger:
                    tomlogger.debug(f"Collected {len(response_parts)} response parts, total length: {len(full_response)}", module_name="claude_code")
                
                # Update project status to finished
                await self._update_project_status(project_path, "finished", "Claude Code execution completed")
                
                if tomlogger:
                    tomlogger.info(f"Claude Code execution completed for {project_path}", module_name="claude_code")
                
                return {
                    "success": True,
                    "response_length": len(full_response),
                    "status": "completed",
                    "message_count": message_count,
                    "debug_log_file": debug_log_file if debug_log_file else None
                }
                
        except Exception as e:
            error_msg = f"Error executing Claude Code: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="claude_code")
            
            # Update project status to error
            await self._update_project_status(project_path, "error", f"Execution failed: {str(e)}")
            
            return {"error": error_msg}
    
    async def _update_project_status(self, project_path: str, status: str, description: str):
        """Update project status file"""
        try:
            if tomlogger:
                tomlogger.debug(f"Updating project status to '{status}': {description}", module_name="claude_code")
                
            status_file = os.path.join(project_path, 'project_status.json')
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if tomlogger:
                tomlogger.debug(f"Status file: {status_file}, timestamp: {current_time}", module_name="claude_code")
            
            # Read current status
            if os.path.exists(status_file):
                with open(status_file, 'r', encoding='utf-8') as f:
                    project_status = json.load(f)
                    if tomlogger:
                        tomlogger.debug(f"Read existing status file with {len(project_status.get('project_steps', []))} steps", module_name="claude_code")
            else:
                if tomlogger:
                    tomlogger.debug("Creating new project status structure", module_name="claude_code")
                project_status = {
                    "project_name": os.path.basename(project_path),
                    "current_status": "init",
                    "last_status_update": current_time,
                    "project_steps": []
                }
            
            # Update status
            project_status["current_status"] = status
            project_status["last_status_update"] = current_time
            
            # Add new step if not already in progress
            if not project_status["project_steps"] or project_status["project_steps"][-1].get("finished_at"):
                new_step = {
                    "description": description,
                    "start_at": current_time,
                    "finished_at": None if status == "executing" else current_time
                }
                project_status["project_steps"].append(new_step)
            else:
                # Update last step
                project_status["project_steps"][-1]["finished_at"] = current_time
            
            # Write updated status
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(project_status, f, ensure_ascii=False, indent=2)
                
            if tomlogger:
                tomlogger.debug(f"Project status updated successfully to '{status}'", module_name="claude_code")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating project status: {str(e)}", module_name="claude_code")
    
    def get_projects_status(self) -> Dict[str, Any]:
        """Get status of all projects"""
        try:
            if tomlogger:
                tomlogger.debug(f"get_projects_status called, checking directory: {self.projects_dir}", module_name="claude_code")
                
            projects_status = []
            
            if not os.path.exists(self.projects_dir):
                if tomlogger:
                    tomlogger.debug(f"Projects directory does not exist: {self.projects_dir}", module_name="claude_code")
                return {"projects": projects_status, "total_projects": 0}
            
            # Iterate through all project directories
            project_items = os.listdir(self.projects_dir)
            if tomlogger:
                tomlogger.debug(f"Found {len(project_items)} items in projects directory", module_name="claude_code")
                
            for item in project_items:
                project_path = os.path.join(self.projects_dir, item)
                
                if tomlogger:
                    tomlogger.debug(f"Processing item: {item}, is_dir: {os.path.isdir(project_path)}", module_name="claude_code")
                
                if os.path.isdir(project_path):
                    status_file = os.path.join(project_path, 'project_status.json')
                    
                    if os.path.exists(status_file):
                        if tomlogger:
                            tomlogger.debug(f"Reading status file for project '{item}': {status_file}", module_name="claude_code")
                        try:
                            with open(status_file, 'r', encoding='utf-8') as f:
                                project_status = json.load(f)
                                projects_status.append(project_status)
                                if tomlogger:
                                    tomlogger.debug(f"Successfully loaded status for project '{item}'", module_name="claude_code")
                        except (json.JSONDecodeError, IOError) as e:
                            if tomlogger:
                                tomlogger.error(f"Error reading status file for project '{item}': {str(e)}", module_name="claude_code")
                            # Add a fallback status for corrupted files
                            projects_status.append({
                                "project_name": item,
                                "status": "error",
                                "error": f"Could not read status file: {str(e)}"
                            })
                    else:
                        if tomlogger:
                            tomlogger.debug(f"No status file found for project '{item}'", module_name="claude_code")
            
            if tomlogger:
                tomlogger.info(f"Retrieved status for {len(projects_status)} projects", module_name="claude_code")
            
            return {
                "projects": projects_status,
                "total_projects": len(projects_status)
            }
            
        except Exception as e:
            error_msg = f"Error retrieving projects status: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="claude_code")
            return {"error": error_msg, "projects": [], "total_projects": 0}


# Initialize Claude Code service
claude_code_service = ClaudeCodeService()


class ClaudeCodeHTTPServer:
    """HTTP server for project status endpoints"""
    
    def __init__(self, claude_service: ClaudeCodeService):
        self.claude_service = claude_service
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def status(self, project_name=None):
        """Get project status by name"""
        if not project_name:
            cherrypy.response.status = 400
            return {"error": "Project name is required"}
        
        if tomlogger:
            tomlogger.debug(f"HTTP status request for project: {project_name}", module_name="claude_code")
        
        try:
            # Sanitize project name (same logic as in create_project)
            safe_project_name = "".join(c for c in project_name if c.isalnum() or c in ('-', '_', ' ')).strip()
            if not safe_project_name:
                cherrypy.response.status = 400
                return {"error": "Invalid project name"}
            
            project_path = os.path.join(self.claude_service.projects_dir, safe_project_name)
            status_file = os.path.join(project_path, 'project_status.json')
            
            if tomlogger:
                tomlogger.debug(f"Looking for status file: {status_file}", module_name="claude_code")
            
            if not os.path.exists(status_file):
                cherrypy.response.status = 404
                return {"error": f"Project '{project_name}' not found"}
            
            # Read and validate JSON with retry for race condition protection
            max_retries = 3
            retry_delay = 0.1
            
            for attempt in range(max_retries):
                try:
                    with open(status_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        
                    if not content:
                        if tomlogger:
                            tomlogger.debug(f"Empty status file on attempt {attempt + 1}", module_name="claude_code")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        else:
                            cherrypy.response.status = 500
                            return {"error": "Status file is empty"}
                    
                    # Parse JSON to validate integrity
                    project_status = json.loads(content)
                    
                    # Validate required fields
                    required_fields = ["project_name", "current_status", "last_status_update", "project_steps"]
                    for field in required_fields:
                        if field not in project_status:
                            if tomlogger:
                                tomlogger.warning(f"Missing required field '{field}' in status file", module_name="claude_code")
                            # Add default value for missing field
                            if field == "project_name":
                                project_status[field] = safe_project_name
                            elif field == "current_status":
                                project_status[field] = "unknown"
                            elif field == "last_status_update":
                                project_status[field] = ""
                            elif field == "project_steps":
                                project_status[field] = []
                    
                    # Validate project_steps structure
                    if not isinstance(project_status["project_steps"], list):
                        project_status["project_steps"] = []
                    
                    if tomlogger:
                        tomlogger.debug(f"Successfully returned status for project '{project_name}'", module_name="claude_code")
                    
                    return project_status
                    
                except json.JSONDecodeError as e:
                    if tomlogger:
                        tomlogger.debug(f"JSON decode error on attempt {attempt + 1}: {str(e)}", module_name="claude_code")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        cherrypy.response.status = 500
                        return {"error": f"Invalid JSON in status file: {str(e)}"}
                        
                except IOError as e:
                    if tomlogger:
                        tomlogger.debug(f"IO error on attempt {attempt + 1}: {str(e)}", module_name="claude_code")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        cherrypy.response.status = 500
                        return {"error": f"Failed to read status file: {str(e)}"}
            
        except Exception as e:
            error_msg = f"Unexpected error getting project status: {str(e)}"
            if tomlogger:
                tomlogger.error(error_msg, module_name="claude_code")
            cherrypy.response.status = 500
            return {"error": error_msg}
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self):
        """Root endpoint - return available endpoints"""
        return {
            "service": "Claude Code Project Status API",
            "endpoints": {
                "/status/PROJECT_NAME": "Get status for specific project"
            },
            "version": "1.0"
        }


@server.tool()
def create_project(
    project_name: str,
    project_plan: str
) -> str:
    """Create a new Claude Code project. Call this function when user wants to create a new project or start working on a new task that requires project planning and execution tracking.
    
    Args:
        project_name: Name of the project to create
        project_plan: Detailed project plan in text format (will be saved as markdown)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: create_project with name='{project_name}'", module_name="claude_code")
        tomlogger.debug(f"Project plan preview: {project_plan[:100]}{'...' if len(project_plan) > 100 else ''}", module_name="claude_code")
    
    result = claude_code_service.create_project(project_name, project_plan)
    
    if tomlogger:
        tomlogger.debug(f"create_project result: {result.get('success', False)}", module_name="claude_code")
    
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def get_projects_status() -> str:
    """Get the current status of all Claude Code projects. Call this function when user asks about existing projects, their status, or wants to see all current projects.
    """
    if tomlogger:
        tomlogger.info("Tool call: get_projects_status", module_name="claude_code")
    
    result = claude_code_service.get_projects_status()
    return json.dumps(result, ensure_ascii=False)


def start_http_server():
    """Start CherryPy HTTP server in a separate thread"""
    try:
        if tomlogger:
            tomlogger.info("🚀 Starting Claude Code HTTP Server on port 8080", module_name="claude_code")
        
        # Configure CherryPy
        cherrypy.config.update({
            'server.socket_host': '0.0.0.0',
            'server.socket_port': 8080,
            'log.screen': False,
            'log.access_file': '',
            'log.error_file': ''
        })
        
        # Mount the HTTP server
        http_server = ClaudeCodeHTTPServer(claude_code_service)
        cherrypy.tree.mount(http_server, '/')
        
        # Start the server
        cherrypy.engine.start()
        
        if tomlogger:
            tomlogger.info("✅ Claude Code HTTP Server started successfully", module_name="claude_code")
            
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"Failed to start HTTP server: {str(e)}", module_name="claude_code")
        else:
            print(f"Failed to start HTTP server: {str(e)}")


def main():
    """Main function to run both MCP and HTTP servers"""
    if tomlogger:
        tomlogger.info("🚀 Starting Claude Code Services", module_name="claude_code")
        tomlogger.debug(f"TOM_LOG_LEVEL environment variable: {os.environ.get('TOM_LOG_LEVEL', 'NOT_SET')}", module_name="claude_code")
        tomlogger.debug(f"Claude Code service initialized: {claude_code_service is not None}", module_name="claude_code")
    else:
        print("Starting Claude Code Services")
    
    # Start HTTP server in background thread
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Small delay to let HTTP server start
    time.sleep(1)
    
    if tomlogger:
        tomlogger.info("🚀 Starting Claude Code MCP Server on port 80", module_name="claude_code")
    else:
        print("Starting Claude Code MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport (blocking)
    server.run(transport="streamable-http")


@server.resource("description://code")
def description() -> str:
    """Returns the description of the server."""
    return SERVER_DESCRIPTION


@server.resource("description://prompt_consign")
def prompt_consign() -> str:
    """Returns upstream instructions for Claude Code project management optimization."""
    
    # Get current projects for context
    projects_data = claude_code_service.get_projects_status()
    
    consign_data = {
        "description": "Claude Code project management optimization instructions",
        "current_projects": {
            "total_projects": projects_data.get("total_projects", 0),
            "projects_available": len(projects_data.get("projects", [])) > 0
        },
        "available_projects": [
            {
                "name": project.get("project_name", "Unknown"),
                "status": project.get("status", "Unknown"),
                "progress": project.get("progress", 0)
            }
            for project in projects_data.get("projects", [])
        ],
        "usage_instructions": {
            "project_creation": "Use create_project when user wants to start a new development project or task",
            "status_checking": "Use get_projects_status to show current projects and their progress",
            "project_naming": "Use descriptive, filesystem-safe names for projects",
            "plan_format": "Project plans should be detailed and include clear objectives and steps"
        },
        "workflow_guidance": [
            "1. Check existing projects first with get_projects_status",
            "2. Create new project only if it doesn't exist",
            "3. Use meaningful project names that reflect the actual work",
            "4. Include comprehensive project plans with clear goals and steps"
        ]
    }
    
    return json.dumps(consign_data, ensure_ascii=False, separators=(',', ':'))


@server.resource("description://response_consign")
def response_consign() -> str:
    """Returns response formatting instructions for Claude Code project responses."""
    
    response_data = {
        "description": "Claude Code project response formatting instructions",
        "formatting_guidelines": {
            "project_creation": "Confirm project creation with clear success message and next steps",
            "status_display": "Present project status in organized, readable format with clear status indicators",
            "project_listing": "Show projects in order of recent activity or creation date",
            "progress_indication": "Use clear progress indicators (percentages, status badges, etc.)"
        },
        "response_structure": {
            "project_creation_success": "Confirm creation, show project path, suggest next actions",
            "status_overview": "Provide summary first, then detailed project list",
            "error_handling": "Provide clear error messages with suggested solutions",
            "empty_state": "Guide users on how to create their first project"
        },
        "user_experience": {
            "emoji_usage": "Use project-appropriate emojis (🚀 for new projects, ✅ for completed, 🔄 for in progress)",
            "actionable_responses": "Always suggest relevant next steps or actions",
            "conversational_tone": "Maintain helpful and encouraging tone for project management"
        },
        "presentation_tips": {
            "group_by_status": "Group projects by status when showing multiple projects",
            "highlight_active": "Emphasize currently active or in-progress projects",
            "show_context": "Provide relevant context about project purpose and goals"
        }
    }
    
    return json.dumps(response_data, ensure_ascii=False, separators=(',', ':'))


if __name__ == "__main__":
    main()
