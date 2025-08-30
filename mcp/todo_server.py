#!/usr/bin/env python3
"""
Todo MCP Server
Provides todo and grocery list management functionality via MCP protocol
Based on the original tomtodo.py module
"""

import json
import os
import sys
import yaml
import functools
from datetime import datetime
from typing import Any, Dict, Optional, List

import caldav
import pytz
from caldav.elements import dav
from icalendar import Todo, Calendar as iCalendar
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

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
    tomlogger.info(f"🚀 Todo MCP Server starting with log level: {log_level}", module_name="todo")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module manages various types of task lists including TODO lists, grocery/shopping lists, and custom lists. It provides comprehensive list management capabilities for organizing different types of tasks and items. Common list names include: 'TODO', 'Tasks', 'Groceries', 'Shopping', 'Shopping List', 'Courses', 'Music', but users can create custom lists with any name."

# Initialize FastMCP server
server = FastMCP(name="todo-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file using TOM_USER environment variable"""
    tom_user = os.environ.get('TOM_USER', 'unknown')
    config_path = f'/data/{tom_user}/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration for user '{tom_user}' from {config_path}", module_name="todo")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="todo")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="todo")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class TodoService:
    """Todo service class based on original TomTodo"""
    
    def __init__(self, config: Dict[str, Any]):
        # Load todo configuration from config
        todo_config = config.get('todo', {})
        
        # Validate required config fields
        required_fields = ['url', 'user', 'password', 'todo_list', 'groceries_list']
        for field in required_fields:
            if field not in todo_config:
                raise KeyError(f"Missing required todo config field: {field}")
        
        self.config = todo_config
        self.date_format = "%Y-%m-%d %H:%M:%S"
        
        # Set timezone
        timezone = todo_config.get('timezone', 'Europe/Paris')
        self.tz = pytz.timezone(timezone)
        
        self.defaultTodoListName = todo_config['todo_list']
        self.defaultGroceriesListName = todo_config['groceries_list']
        
        self.todoCalendars = {}
        self.todoCal = None
        
        try:
            self.client = caldav.DAVClient(
                url=todo_config['url'],
                username=todo_config['user'],
                password=todo_config['password'],
            )
            
            principal = self.client.principal()
            self.calendars = principal.calendars()
            
            for calendar in self.calendars:
                if calendar.get_properties() is not None:
                    if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' not in calendar.get_properties().keys():
                        display_name = calendar.get_properties([dav.DisplayName()])['{DAV:}displayname']
                        self.todoCalendars[display_name] = calendar
                        if display_name == self.defaultTodoListName:
                            self.todoCal = calendar
            
            if tomlogger:
                tomlogger.info("✅ CalDAV connection established successfully", module_name="todo")
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Failed to connect to CalDAV server: {str(e)}", module_name="todo")
            # Initialize with empty state so module can still load
            self.client = None
            self.calendars = []
            self.todoCalendars = {}
            self.todoCal = None
            raise
        
        if tomlogger:
            tomlogger.info(f"✅ Todo service initialized successfully with {len(self.todoCalendars)} lists", module_name="todo")
    
    def getCalendarByName(self, list_name: Optional[str] = None):
        """Get calendar by name or return default"""
        if self.client is None:
            return None
            
        if list_name is None:
            return self.todoCal
        
        if list_name in self.todoCalendars:
            return self.todoCalendars[list_name]
        
        return None
    
    def listAvailableLists(self) -> Dict[str, Any]:
        """List all available todo lists"""
        if self.client is None:
            return {"status": "error", "message": "CalDAV connection not available"}
        
        # Refresh calendar list from server
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            self.todoCalendars = {}
            for calendar in calendars:
                if calendar.get_properties() is not None:
                    if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' not in calendar.get_properties().keys():
                        display_name = calendar.get_properties([dav.DisplayName()])['{DAV:}displayname']
                        self.todoCalendars[display_name] = calendar
                        if display_name == self.defaultTodoListName:
                            self.todoCal = calendar
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error refreshing calendar list: {str(e)}", module_name="todo")
        
        return {"status": "success", "lists": list(self.todoCalendars.keys())}
    
    def createList(self, list_name: str) -> Dict[str, Any]:
        """Create a new todo list"""
        if self.client is None:
            return {"status": "error", "message": "CalDAV connection not available"}
        
        try:
            principal = self.client.principal()
            
            new_calendar = principal.make_calendar(name=list_name)
            new_calendar.set_properties([dav.DisplayName(list_name)])
            
            self.todoCalendars[list_name] = new_calendar
            
            if tomlogger:
                tomlogger.info(f"New todo list '{list_name}' created successfully.", module_name="todo")
            return {"status": "success", "message": f"Todo list '{list_name}' created"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error creating todo list '{list_name}': {str(e)}", module_name="todo")
            return {"status": "error", "message": f"Failed to create todo list '{list_name}'"}
    
    def listItems(self, list_name: str) -> List[Dict[str, Any]]:
        """List all items in a specific list"""
        calendar = self.getCalendarByName(list_name)
        if calendar is None:
            if tomlogger:
                tomlogger.error(f"List '{list_name}' not found", module_name="todo")
            return []
        
        items = []
        try:
            for item in calendar.todos():
                due = item.icalendar_component.get('due')
                if due is not None:
                    due = due.dt.strftime("%Y-%m-%d %H:%M:%S")

                items.append({
                    "name": str(item.icalendar_component.get('summary')), 
                    "due": due,
                    "priority": item.icalendar_component.get('priority'),
                    "id": str(item.icalendar_component.get('uid'))
                })
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error retrieving list '{list_name}': {str(e)}", module_name="todo")
            return []
        
        return items
    
    def addToList(self, item_name: str, list_name: str, priority: Optional[int] = None, due: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Add an item to a todo list"""
        calendar = self.getCalendarByName(list_name)
        if calendar is None:
            return {"status": "error", "message": f"List '{list_name}' not found"}

        try:
            task = Todo()
            task.add('summary', item_name)
            if priority is not None:
                task.add('priority', priority)
            if due is not None:
                task.add('due', datetime.strptime(due, self.date_format))
            if description is not None:
                task.add('description', description)

            cal = iCalendar()
            cal.add_component(task)
            calendar.save_event(cal.to_ical().decode('utf-8'))

            if tomlogger:
                tomlogger.info(f"Item '{item_name}' added to list '{list_name}'", module_name="todo")
            return {"status": "success", "message": f"Item added to {list_name}"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error adding item '{item_name}' to '{list_name}': {str(e)}", module_name="todo")
            return {"status": "error", "message": f"Failed to add item: {str(e)}"}
    
    def removeFromList(self, item_id: str, list_name: str) -> Dict[str, Any]:
        """Remove an item from a todo list"""
        calendar = self.getCalendarByName(list_name)
        if calendar is None:
            return {"status": "error", "message": f"List '{list_name}' not found"}

        try:
            task = calendar.todo_by_uid(item_id)
            if not task:
                return {"status": "error", "message": "Item not found"}

            # Get item name for logging
            if hasattr(task, 'vobject_instance') and task.vobject_instance:
                vtodo = task.vobject_instance.vtodo
                itemName = vtodo.summary.value if hasattr(vtodo, 'summary') else 'No summary'
                vtodo.add('status').value = 'COMPLETED'
                task.save()
            elif hasattr(task, 'icalendar_instance') and task.icalendar_instance:
                itemName = str(task.icalendar_component.get('summary', 'No summary'))
                task.icalendar_component['status'] = 'COMPLETED'
                task.save()
            else:
                try:
                    vtodo = task.instance.vtodo
                    itemName = vtodo.contents.get('summary', ['No summary'])[0].value
                    vtodo.add('status').value = 'COMPLETED'
                    task.save()
                except AttributeError:
                    itemName = str(task.icalendar_component.get('summary', 'No summary'))
                    task.delete()

            if tomlogger:
                tomlogger.info(f"Item '{itemName}' removed from list '{list_name}'", module_name="todo")
            return {"status": "success", "message": f"Item removed from {list_name}"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error removing item {item_id} from '{list_name}': {str(e)}", module_name="todo")
            return {"status": "error", "message": f"Failed to remove item: {str(e)}"}
    
    def updateItemPriority(self, item_id: str, list_name: str, priority: int) -> Dict[str, Any]:
        """Update the priority of an item in a todo list"""
        calendar = self.getCalendarByName(list_name)
        if calendar is None:
            return {"status": "error", "message": f"List '{list_name}' not found"}

        try:
            task = calendar.todo_by_uid(item_id)
            if not task:
                return {"status": "error", "message": "Item not found"}

            # Get item name for logging
            itemName = "Unknown item"
            
            # Handle different CalDAV API versions
            if hasattr(task, 'vobject_instance') and task.vobject_instance:
                vtodo = task.vobject_instance.vtodo
                itemName = vtodo.summary.value if hasattr(vtodo, 'summary') else 'No summary'
                
                # Set or update priority
                if hasattr(vtodo, 'priority'):
                    vtodo.priority.value = priority
                else:
                    vtodo.add('priority').value = priority
                    
                task.save()
                
            elif hasattr(task, 'icalendar_instance') and task.icalendar_instance:
                # Use icalendar API
                itemName = str(task.icalendar_component.get('summary', 'No summary'))
                
                # Set priority in icalendar component
                task.icalendar_component['priority'] = priority
                    
                task.save()
                
            else:
                # Fallback to legacy API
                try:
                    vtodo = task.instance.vtodo
                    itemName = vtodo.contents.get('summary', ['No summary'])[0].value
                    
                    # Set priority
                    if 'priority' in vtodo.contents:
                        vtodo.contents['priority'][0].value = priority
                    else:
                        vtodo.add('priority').value = priority
                        
                    task.save()
                    
                except AttributeError:
                    # Last resort: try icalendar component
                    itemName = str(task.icalendar_component.get('summary', 'No summary'))
                    
                    task.icalendar_component['priority'] = priority
                        
                    task.save()

            if tomlogger:
                tomlogger.info(f"Priority updated to {priority} for item '{itemName}' in list '{list_name}'", module_name="todo")
            return {"status": "success", "message": f"Priority updated to {priority} for item in {list_name}"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating priority for item {item_id} in '{list_name}': {str(e)}", module_name="todo")
            return {"status": "error", "message": f"Failed to update priority: {str(e)}"}


# Load configuration and initialize todo service
config = load_config()
todo_service = TodoService(config)


@server.tool()
def list_available_lists() -> str:
    """List all available lists. Use this when user asks about what lists they have."""
    if tomlogger:
        tomlogger.info("Tool call: list_available_lists", module_name="todo")
    
    result = todo_service.listAvailableLists()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def create_list(list_name: str) -> str:
    """Create a new list. Use this when user wants to create a new list.
    
    Args:
        list_name: Name of the new list to create
    """
    if tomlogger:
        tomlogger.info(f"Tool call: create_list with list_name={list_name}", module_name="todo")
    
    result = todo_service.createList(list_name)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def add_to_list(item_name: str, list_name: str, priority: Optional[int] = None, due: Optional[str] = None, description: Optional[str] = None) -> str:
    """Add an item to a list. Use this for adding tasks, products, or any items to lists.
    
    Args:
        item_name: The name/title of the item to add to the list
        list_name: Name of the list to add the item to. REQUIRED parameter.
        priority: Priority from 1-9 (1 is highest). Only for TODO tasks, not for grocery items.
        due: Due date in 'YYYY-MM-DD HH:MM:SS' format. Only for TODO tasks, not for grocery items.
        description: Additional description or notes for the item. Optional parameter.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: add_to_list with item_name={item_name}, list_name={list_name}, priority={priority}, due={due}, description={description}", module_name="todo")
    
    result = todo_service.addToList(item_name, list_name, priority, due, description)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def list_items(list_name: str) -> str:
    """List all items in a specific list. Use this to show contents of any list.
    
    Args:
        list_name: Name of the list to show items from. REQUIRED parameter.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_items with list_name={list_name}", module_name="todo")
    
    result = todo_service.listItems(list_name)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def remove_from_list(item_id: str, list_name: str) -> str:
    """Remove/close an item from a list. Use this to remove items, mark tasks as done, etc.
    
    Args:
        item_id: The ID of the item to remove. Get this from list_items function.
        list_name: Name of the list containing the item. REQUIRED parameter.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: remove_from_list with item_id={item_id}, list_name={list_name}", module_name="todo")
    
    result = todo_service.removeFromList(item_id, list_name)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def update_item_priority(item_id: str, list_name: str, priority: int) -> str:
    """Update the priority of an item in a list. Use this to change task priority (1-9, where 1 is highest priority).
    
    Args:
        item_id: The ID of the item to update. Get this from list_items function.
        list_name: Name of the list containing the item. REQUIRED parameter.
        priority: New priority: 1 (highest/urgent), 5 (medium), 9 (lowest).
    """
    if tomlogger:
        tomlogger.info(f"Tool call: update_item_priority with item_id={item_id}, list_name={list_name}, priority={priority}", module_name="todo")
    
    result = todo_service.updateItemPriority(item_id, list_name, priority)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://todo")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


@server.resource("description://prompt_consign")
def prompt_consign() -> str:
    """Returns upstream instructions with available todo lists in JSON format to optimize LLM performance."""
    
    # Get available lists
    lists_result = todo_service.listAvailableLists()
    available_lists = lists_result.get('lists', []) if lists_result.get('status') == 'success' else []
    
    # Build prompt consign in JSON format
    consign_data = {
        "description": "Available lists",
        "list_name": available_lists,
        "is_list_name_case_sensitive": True
    }
    
    return json.dumps(consign_data, ensure_ascii=False, separators=(',', ':'))


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Todo MCP Server on port 80", module_name="todo")
    else:
        print("Starting Todo MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
