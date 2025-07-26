import json
from datetime import datetime, timedelta
import functools
import time
import paramiko
import threading
import sys
import os
import uuid
import re

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

################################################################################################
#                                                                                              #
#                                   Technical Capabilities                                     #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "techcapabilities",
  "class_name": "TomTechCapabilities",
  "description": "This module provides technical capabilities for development, code execution, and complex computing tasks. It allows you to execute commands, develop software, analyze code, and perform technical tasks asynchronously. The module provides an access to a Debian Linux virtual machine with internet access.",
  "type": "personal",
  "complexity": 1,
  "configuration_parameters": {
    "tasks_dir": {
      "type": "string",
      "description": "Directory path for storing task markdown files",
      "required": True
    },
    "host": {
      "type": "string",
      "description": "SSH hostname or IP address of the execution environment",
      "required": True
    },
    "username": {
      "type": "string",
      "description": "SSH username for connecting to the execution environment",
      "required": True
    },
    "ssh_key_path": {
      "type": "string",
      "description": "Path to the SSH private key file for connecting to the execution environment",
      "required": True
    }
  }
}

class TomTechCapabilities:

  def __init__(self, config, llm) -> None:
    
    # Debug config type and content
    logger.debug(f"Config type: {type(config)}, Content: {config}")
    
    # Ensure config is a dictionary
    if not isinstance(config, dict):
      raise ValueError(f"Config must be a dictionary, got {type(config)}")
    
    self.tasks_dir = config.get('tasks_dir', '/data/techcapabilities/')
    self.llm = llm
    self.background_status = {"ts": int(time.time()), "status": None}
    
    # Create tasks directory if it doesn't exist
    os.makedirs(self.tasks_dir, exist_ok=True)
    
    # Initialize SSH connection
    try:
      self.client = paramiko.SSHClient()
      self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      
      # Validate required SSH parameters
      required_params = ['host', 'username', 'ssh_key_path']
      for param in required_params:
        if param not in config:
          raise ValueError(f"Missing required SSH parameter: {param}")
      
      self.client.connect(
        config['host'], 
        port=22, 
        username=config['username'], 
        key_filename=config['ssh_key_path']
      )
      logger.info(f"SSH connection established to {config['host']}")
      
    except Exception as e:
      logger.error(f"Failed to establish SSH connection: {str(e)}")
      raise

    logger.debug("Creating tools configuration...")
    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "create_tech_task",
          "description": "Create a new technical task for asynchronous processing",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "request": {
                "type": "string",
                "description": "Description of the technical task to be performed",
              },
              "priority": {
                "type": "string",
                "enum": ["low", "normal", "high"],
                "description": "Priority level of the task"
              }
            },
            "required": ["request"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "list_tech_tasks",
          "description": "List all technical tasks with their current status",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "status_filter": {
                "type": "string",
                "enum": ["all", "pending", "in_progress", "completed", "failed"],
                "description": "Filter tasks by status"
              }
            },
            "required": [],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_task_details",
          "description": "Get detailed information about a specific task",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "task_id": {
                "type": "string",
                "description": "ID of the task to retrieve details for",
              }
            },
            "required": ["task_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_task_results",
          "description": "Get ONLY the final results of a completed task (not the full session log)",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "task_id": {
                "type": "string",
                "description": "ID of the task to get results for",
              }
            },
            "required": ["task_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "cancel_task",
          "description": "Cancel a pending or in-progress task",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "task_id": {
                "type": "string",
                "description": "ID of the task to cancel",
              }
            },
            "required": ["task_id"],
            "additionalProperties": False,
          },
        },
      }
    ]

    logger.debug("Setting up system context...")
    self.systemContext = """You have access to technical capabilities for asynchronous processing of complex tasks.

IMPORTANT: This module works ASYNCHRONOUSLY. When a user requests technical work:
1. Use create_tech_task() to create and start the task in background
2. Immediately respond that the task has been created and is being processed
3. DO NOT attempt to solve the task yourself in the conversation
4. When users ask about task progress or results, ALWAYS use the appropriate functions

Available operations:
- create_tech_task(): Start a new background task for development, analysis, installation, etc.
- list_tech_tasks(): Show all tasks and their status (use status_filter="completed" for finished tasks)
- get_task_details(): Get the FULL detailed session log of a specific task including results
- get_task_results(): Get ONLY the final results of a completed task
- cancel_task(): Cancel a running task

IMPORTANT: When users ask "what are the results of task X" or "show me the results", use get_task_results() or get_task_details() to retrieve the actual content from the markdown files. The results are stored in detailed markdown files with analysis, execution logs, and final results.

The background tasks have access to a Debian Linux VM with internet access and can execute commands, install software, develop code, perform analysis, etc."""
    
    logger.debug("Setting up complexity and functions...")
    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "create_tech_task": {
        "function": functools.partial(self.create_tech_task)
      },
      "list_tech_tasks": {
        "function": functools.partial(self.list_tech_tasks)
      },
      "get_task_details": {
        "function": functools.partial(self.get_task_details)
      },
      "get_task_results": {
        "function": functools.partial(self.get_task_results)
      },
      "cancel_task": {
        "function": functools.partial(self.cancel_task)
      }
    }
    
    # Resume pending/in-progress tasks after module restart (at the end)
    try:
      logger.debug("Starting to resume incomplete tasks...")
      self._resume_incomplete_tasks()
      logger.debug("Incomplete tasks resume completed")
    except Exception as e:
      logger.error(f"Error during task resume: {str(e)}")
      # Don't raise here, just log the error
    
    logger.debug("TomTechCapabilities initialization completed successfully")

  def _get_tasks_index_file(self):
    """Get path to the tasks index markdown file"""
    return os.path.join(self.tasks_dir, "tasks_index.md")

  def _get_task_file(self, task_id):
    """Get path to a specific task markdown file"""
    return os.path.join(self.tasks_dir, f"task_{task_id}.md")

  def _resume_incomplete_tasks(self):
    """Resume incomplete tasks after module restart"""
    index_file = self._get_tasks_index_file()
    logger.debug(f"Checking for tasks index at: {index_file}")
    if not os.path.exists(index_file):
      logger.debug("No tasks index found, skipping task resume")
      return
    
    try:
      with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      # Find tasks with pending or in_progress status
      incomplete_tasks = []
      for line in content.split('\n'):
        if '|' in line and ('pending' in line or 'in_progress' in line):
          parts = [part.strip() for part in line.split('|')]
          if len(parts) >= 2:
            task_id = parts[1].strip()
            if task_id and task_id != 'Task ID':  # Skip header
              incomplete_tasks.append(task_id)
      
      # Resume each incomplete task
      for task_id in incomplete_tasks:
        request = self._extract_request_from_task_file(task_id)
        if request:
          logger.info(f"Resuming incomplete task {task_id}")
          # Reset status to pending and restart
          self._update_task_status_in_index(task_id, "pending")
          self._update_task_file(task_id, {
            "status": "pending",
            "status_update": "🔄 Task resumed after module restart"
          })
          
          # Start processing in background
          thread = threading.Thread(target=self._process_task, args=(task_id, request))
          thread.daemon = True
          thread.start()
          
    except Exception as e:
      logger.error(f"Error resuming incomplete tasks: {str(e)}")

  def _extract_request_from_task_file(self, task_id):
    """Extract the original request from a task markdown file"""
    task_file = self._get_task_file(task_id)
    if not os.path.exists(task_file):
      return None
    
    try:
      with open(task_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      # Extract request from between ``` markers in the Original Request section
      import re
      pattern = r"## 🎯 Original Request\n```\n(.*?)\n```"
      match = re.search(pattern, content, re.DOTALL)
      if match:
        return match.group(1).strip()
      
      return None
    except Exception as e:
      logger.error(f"Error extracting request from task {task_id}: {str(e)}")
      return None

  def _create_tasks_index_if_not_exists(self):
    """Create the tasks index file if it doesn't exist"""
    index_file = self._get_tasks_index_file()
    if not os.path.exists(index_file):
      with open(index_file, 'w', encoding='utf-8') as f:
        f.write("# Technical Tasks Index\n\n")
        f.write("This file contains a list of all technical tasks and their current status.\n\n")
        f.write("| Task ID | Status | Priority | Created | Description | Task File |\n")
        f.write("|---------|--------|----------|---------|-------------|----------|\n")

  def _add_task_to_index(self, task_id, status, priority, created, description):
    """Add a new task to the index file"""
    self._create_tasks_index_if_not_exists()
    index_file = self._get_tasks_index_file()
    
    # Read current content
    with open(index_file, 'r', encoding='utf-8') as f:
      content = f.read()
    
    # Add new task row
    task_file = f"task_{task_id}.md"
    new_row = f"| {task_id} | {status} | {priority} | {created} | {description[:50]}... | [{task_file}](./{task_file}) |\n"
    
    # Append to the end of the file
    with open(index_file, 'a', encoding='utf-8') as f:
      f.write(new_row)

  def _update_task_status_in_index(self, task_id, new_status):
    """Update task status in the index file"""
    index_file = self._get_tasks_index_file()
    if not os.path.exists(index_file):
      return
    
    with open(index_file, 'r', encoding='utf-8') as f:
      content = f.read()
    
    # Update the status in the table row
    pattern = rf"(\| {re.escape(task_id)} \| )[^|]+(\| .+)"
    replacement = rf"\g<1>{new_status}\g<2>"
    updated_content = re.sub(pattern, replacement, content)
    
    with open(index_file, 'w', encoding='utf-8') as f:
      f.write(updated_content)

  def _create_task_file(self, task_id, request, priority):
    """Create a detailed task markdown file"""
    task_file = self._get_task_file(task_id)
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"""# Technical Task Session: {task_id}

## 📋 Task Overview
- **Task ID**: `{task_id}`
- **Status**: 🟡 Pending
- **Priority**: {priority}
- **Created**: {created}
- **Started**: -
- **Completed**: -

## 🎯 Original Request
```
{request}
```

## 🤔 Initial Analysis
*Waiting for task processing to begin...*

## 📝 Execution Plan
*Task plan will be generated when processing starts...*

## 🛠 Implementation Steps
*Implementation steps will be tracked here...*

## 💻 Command Execution Log
*All commands and their outputs will be logged here in real-time...*

### Commands Executed:
*No commands executed yet.*

## 🧠 Reasoning & Decisions
*Decision-making process and reasoning will be documented here...*

## 📊 Progress Tracking
- [ ] Task analysis completed
- [ ] Execution plan created  
- [ ] Implementation started
- [ ] Testing performed
- [ ] Task completed

## 🎉 Final Results
*Final results and deliverables will appear here...*

## 📈 Status History
- `{created}`: ✅ Task created and queued for processing

---
*This document is automatically updated throughout the task execution process*
"""
    
    with open(task_file, 'w', encoding='utf-8') as f:
      f.write(content)

  def _update_task_file(self, task_id, updates):
    """Update a task file with new information"""
    task_file = self._get_task_file(task_id)
    if not os.path.exists(task_file):
      return False
    
    with open(task_file, 'r', encoding='utf-8') as f:
      content = f.read()
    
    # Update specific sections based on the updates dict
    for key, value in updates.items():
      if key == "status":
        # Update status with emoji
        status_emoji = {"pending": "🟡", "in_progress": "🔵", "completed": "🟢", "failed": "🔴", "cancelled": "⚫"}
        emoji = status_emoji.get(value, "🟡")
        content = re.sub(r"- \*\*Status\*\*: .*", f"- **Status**: {emoji} {value.title()}", content)
      elif key == "started":
        content = re.sub(r"- \*\*Started\*\*: .*", f"- **Started**: {value}", content)
      elif key == "completed":
        content = re.sub(r"- \*\*Completed\*\*: .*", f"- **Completed**: {value}", content)
      elif key == "analysis":
        # Update initial analysis section
        analysis_pattern = r"(## 🤔 Initial Analysis\n).*?(\n## 📝 Execution Plan)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(analysis_pattern, replacement, content, flags=re.DOTALL)
      elif key == "plan":
        # Update execution plan section
        plan_pattern = r"(## 📝 Execution Plan\n).*?(\n## 🛠 Implementation Steps)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(plan_pattern, replacement, content, flags=re.DOTALL)
      elif key == "implementation":
        # Update implementation steps section
        impl_pattern = r"(## 🛠 Implementation Steps\n).*?(\n## 💻 Command Execution Log)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(impl_pattern, replacement, content, flags=re.DOTALL)
      elif key == "command_log":
        # Update command execution log
        cmd_pattern = r"(### Commands Executed:\n).*?(\n## 🧠 Reasoning & Decisions)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(cmd_pattern, replacement, content, flags=re.DOTALL)
      elif key == "reasoning":
        # Update reasoning section
        reasoning_pattern = r"(## 🧠 Reasoning & Decisions\n).*?(\n## 📊 Progress Tracking)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(reasoning_pattern, replacement, content, flags=re.DOTALL)
      elif key == "progress":
        # Update progress checkboxes
        progress_pattern = r"(## 📊 Progress Tracking\n).*?(\n## 🎉 Final Results)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(progress_pattern, replacement, content, flags=re.DOTALL)
      elif key == "results":
        # Update final results section
        results_pattern = r"(## 🎉 Final Results\n).*?(\n## 📈 Status History)"
        replacement = rf"\g<1>{value}\g<2>"
        content = re.sub(results_pattern, replacement, content, flags=re.DOTALL)
      elif key == "status_update":
        # Append to status history
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content += f"\n- `{timestamp}`: {value}"
    
    with open(task_file, 'w', encoding='utf-8') as f:
      f.write(content)
    
    return True

  def execute_command(self, command):
    """Execute a command ONLY on the remote VM via SSH connection"""
    # Security check: ensure SSH connection is active
    if not self.client or not self.client.get_transport() or not self.client.get_transport().is_active():
      logger.error(f"🚨 SECURITY: SSH connection not active - cannot execute command: {command}")
      return {"return_code": -1, "stdout": "", "stderr": "SSH connection not active"}
    
    # Log the command execution for security audit
    logger.info(f"🔐 Executing on remote VM via SSH: {command[:100]}...")
    
    try:
      stdin, stdout, stderr = self.client.exec_command(command)
      output = stdout.read().decode('utf-8')
      error = stderr.read().decode('utf-8')
      return_code = stdout.channel.recv_exit_status()
      
      logger.debug(f"✅ Command executed successfully with return code: {return_code}")
      return {"return_code": return_code, "stdout": output, "stderr": error}
      
    except Exception as e:
      logger.error(f"❌ SSH command execution failed: {str(e)}")
      return {"return_code": -1, "stdout": "", "stderr": f"SSH execution error: {str(e)}"}

  def create_tech_task(self, request, priority="normal"):
    """Create a new technical task for asynchronous processing"""
    task_id = str(uuid.uuid4())[:8]
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info(f"🆕 Creating new technical task {task_id} with priority {priority}")
    logger.info(f"📝 Task request: {request[:200]}...")
    
    # Create task file
    self._create_task_file(task_id, request, priority)
    logger.debug(f"📄 Created task file for {task_id}")
    
    # Add to index
    self._add_task_to_index(task_id, "pending", priority, created, request)
    logger.debug(f"📋 Added task {task_id} to index")
    
    # Start processing in background
    thread = threading.Thread(target=self._process_task, args=(task_id, request))
    thread.daemon = True
    thread.start()
    
    logger.info(f"🚀 Started background processing thread for task {task_id}")
    
    return f"✅ Technical task created with ID: {task_id}. The task is now being processed in the background on the secure VM. You can check its status using list_tech_tasks or get_task_details."

  def list_tech_tasks(self, status_filter="all"):
    """List all technical tasks with their current status"""
    index_file = self._get_tasks_index_file()
    if not os.path.exists(index_file):
      return "No tasks found. The tasks index file doesn't exist yet."
    
    with open(index_file, 'r', encoding='utf-8') as f:
      content = f.read()
    
    if status_filter != "all":
      # Filter by status
      lines = content.split('\n')
      filtered_lines = []
      for line in lines:
        if '|' in line and status_filter in line:
          filtered_lines.append(line)
        elif not '|' in line or 'Task ID' in line or '----' in line:
          filtered_lines.append(line)
      content = '\n'.join(filtered_lines)
    
    # Add helpful instructions for completed tasks
    if status_filter == "completed" or status_filter == "all":
      if "completed" in content.lower():
        content += "\n\n💡 **Tip:** For completed tasks, use:\n"
        content += "- `get_task_results(task_id)` to see ONLY the final results\n"
        content += "- `get_task_details(task_id)` to see the full execution session with commands and logs"
    
    return content

  def get_task_details(self, task_id):
    """Get detailed information about a specific task"""
    task_file = self._get_task_file(task_id)
    if not os.path.exists(task_file):
      return f"Task {task_id} not found."
    
    with open(task_file, 'r', encoding='utf-8') as f:
      content = f.read()
    
    return content

  def get_task_results(self, task_id):
    """Get ONLY the final results of a completed task"""
    task_file = self._get_task_file(task_id)
    if not os.path.exists(task_file):
      return f"Task {task_id} not found."
    
    with open(task_file, 'r', encoding='utf-8') as f:
      content = f.read()
    
    # Extract only the results section
    import re
    
    # First check if task is completed
    if "🟢 Completed" not in content and "completed" not in content.lower():
      return f"Task {task_id} is not yet completed. Current status can be checked with get_task_details()."
    
    # Extract the Final Results section
    results_pattern = r"## 🎉 Final Results\n(.*?)(?:\n## 📈 Status History|$)"
    match = re.search(results_pattern, content, re.DOTALL)
    
    if match:
      results = match.group(1).strip()
      if results and results != "*Final results and deliverables will appear here...*":
        return f"**Results for Task {task_id}:**\n\n{results}"
      else:
        return f"Task {task_id} is completed but no final results were recorded."
    else:
      # Fallback: try to find any results in the file
      if "completed successfully" in content.lower():
        return f"Task {task_id} completed successfully. Use get_task_details() for the full session log including analysis, commands executed, and detailed progress."
      else:
        return f"Could not extract results for task {task_id}. Use get_task_details() for the complete task information."

  def cancel_task(self, task_id):
    """Cancel a pending or in-progress task"""
    # Update status in both index and task file
    self._update_task_status_in_index(task_id, "cancelled")
    self._update_task_file(task_id, {
      "status": "cancelled",
      "status_update": "Task cancelled by user request"
    })
    
    logger.info(f"Cancelled technical task {task_id}")
    return f"Task {task_id} has been cancelled."

  def _process_task(self, task_id, request):
    """Process a task in the background"""
    logger.info(f"🏃 Starting background processing for task {task_id}")
    
    try:
      # Update status to in_progress
      logger.info(f"🔄 Marking task {task_id} as in_progress")
      self._update_task_status_in_index(task_id, "in_progress")
      started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      self._update_task_file(task_id, {
        "status": "in_progress",
        "started": started,
        "status_update": "Task processing started"
      })
      
      # Process the request using LLM
      logger.info(f"🧠 Starting LLM-based execution for task {task_id}")
      result = self._execute_task_with_llm(task_id, request)
      
      # Update with results
      completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      logger.info(f"✅ Task {task_id} completed successfully")
      self._update_task_status_in_index(task_id, "completed")
      self._update_task_file(task_id, {
        "status": "completed",
        "completed": completed,
        "results": result,
        "status_update": "Task completed successfully"
      })
      
      logger.info(f"💾 Task {task_id} results saved to file")
      
    except Exception as e:
      # Update status to failed
      logger.error(f"❌ Task {task_id} failed with error: {str(e)}")
      self._update_task_status_in_index(task_id, "failed")
      self._update_task_file(task_id, {
        "status": "failed",
        "results": f"Task failed with error: {str(e)}",
        "status_update": f"Task failed: {str(e)}"
      })
      
      logger.error(f"🚨 Failed to process technical task {task_id}: {str(e)}")

  def _execute_task_with_llm(self, task_id, request):
    """Execute the task using LLM with command execution capabilities"""
    logger.info(f"🔍 Phase 1: Starting analysis for task {task_id}")
    
    # Phase 1: Analysis and Planning
    analysis_prompt = [{
      "role": "system",
      "content": """You are a technical task analyst. Your job is to analyze the user's request and create a structured approach.

      IMPORTANT: You will be working on a SECURE DEBIAN LINUX VM accessed via SSH. All commands will be executed ONLY on this remote VM, never on the local system.

      Respond with a structured analysis containing:
      1. **Task Understanding**: What exactly needs to be done
      2. **Requirements**: What tools, libraries, or resources might be needed
      3. **Approach**: High-level strategy to accomplish this task
      4. **Potential Challenges**: What difficulties might arise

      Be concise but thorough in your analysis."""
    }, {
      "role": "user", 
      "content": f"Analyze this technical task request: {request}"
    }]
    
    analysis_response = self.llm.callLLM(messages=analysis_prompt, complexity=2, llm="deepseek-chat")
    analysis = analysis_response.choices[0].message.content if analysis_response else "Analysis failed"
    logger.info(f"📊 Phase 1 completed: Analysis generated for task {task_id}")
    
    # Update task file with analysis
    self._update_task_file(task_id, {
      "analysis": analysis,
      "status_update": "📋 Initial analysis completed"
    })
    
    # Phase 2: Create execution plan
    logger.info(f"📝 Phase 2: Creating execution plan for task {task_id}")
    plan_prompt = [{
      "role": "system",
      "content": """Based on the analysis, create a detailed execution plan with numbered steps.
      
      IMPORTANT: Remember you are working on a SECURE DEBIAN LINUX VM via SSH. All commands will be executed ONLY on this remote VM.
      
      Format your response as a numbered list of specific, actionable steps that will accomplish the task.
      Each step should be clear and executable. Include any setup, implementation, testing, and cleanup steps needed."""
    }, {
      "role": "user",
      "content": f"Create an execution plan for: {request}\n\nPrevious analysis:\n{analysis}"
    }]
    
    plan_response = self.llm.callLLM(messages=plan_prompt, complexity=2, llm="deepseek-chat")
    plan = plan_response.choices[0].message.content if plan_response else "Planning failed"
    logger.info(f"🗺️ Phase 2 completed: Execution plan created for task {task_id}")
    
    # Update task file with plan
    self._update_task_file(task_id, {
      "plan": plan,
      "status_update": "📝 Execution plan created"
    })
    
    # Phase 3: Execute the plan
    logger.info(f"⚙️ Phase 3: Starting command execution for task {task_id}")
    tools = [{
      "type": "function",
      "function": {
        "name": "execute_command",
        "description": "Execute a Linux command ONLY on the secure remote VM via SSH. ALL commands are executed remotely, never locally.",
        "strict": True,
        "parameters": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string",
              "description": "Linux command to execute on the remote VM (via SSH)",
            },
          },
          "required": ["command"],
          "additionalProperties": False,
        },
      },
    }]

    execution_prompt = [{
      "role": "system", 
      "content": """You are executing a technical task on a REMOTE Linux Debian system via SSH connection.

      🔒 CRITICAL SECURITY REMINDERS:
      - ALL commands are executed on the REMOTE VM via SSH
      - You are NOT on the local system - you are connected to a secure VM
      - The VM is isolated and dedicated to technical tasks
      - No commands affect the local Tom system

      IMPORTANT EXECUTION GUIDELINES:
      1. Follow the execution plan step by step
      2. Document your reasoning for each major decision
      3. Use silent mode (-q, --quiet, > /dev/null) for commands with large output
      4. Test your work as you progress
      5. Handle errors gracefully and adjust your approach if needed
      6. Provide clear progress updates

      For each command, you receive: {"return_code": X, "stdout": "...", "stderr": "..."}
      
      Work systematically through the plan, adapting as needed based on results."""
    }, {
      "role": "user", 
      "content": f"""Execute this technical task on the remote VM: {request}

Follow this execution plan:
{plan}

Previous analysis:
{analysis}"""
    }]

    command_log = []
    reasoning_log = []
    step_progress = []
    
    while True:
      response = self.llm.callLLM(messages=execution_prompt, tools=tools, complexity=2, llm="deepseek-chat")
      
      if response != False:
        if response.choices[0].finish_reason == "stop":
          final_result = response.choices[0].message.content
          
          # Update all sections with final information
          command_log_text = "\n".join([f"```bash\n{cmd['command']}\n```\n**Output:** `{cmd['result'][:100]}...`\n" for cmd in command_log])
          reasoning_text = "\n".join([f"- {reason}" for reason in reasoning_log])
          
          # Update progress checkboxes
          progress_text = """- [x] Task analysis completed
- [x] Execution plan created  
- [x] Implementation started
- [x] Commands executed
- [x] Task completed"""
          
          self._update_task_file(task_id, {
            "command_log": command_log_text or "*No commands were executed.*",
            "reasoning": reasoning_text or "*No specific reasoning logged.*",
            "progress": progress_text,
            "results": final_result,
            "status_update": "🎉 Task execution completed"
          })
          
          return final_result
          
        elif response.choices[0].finish_reason == "tool_calls":
          # Clean message from reasoning_content before adding to prompt
          message_dict = response.choices[0].message.to_dict()
          if 'reasoning_content' in message_dict:
            logger.debug(f"🧹 Cleaning reasoning_content from message for task {task_id}")
            del message_dict['reasoning_content']
          execution_prompt.append(message_dict)
          
          for tool_call in response.choices[0].message.tool_calls:
            function_name = tool_call.function.name
            function_params = json.loads(tool_call.function.arguments)
            command = function_params.get('command', 'Unknown command')
            
            logger.info(f"🖥️ Executing command on VM for task {task_id}: {command}")
            
            # Ensure command execution is via SSH (security check)
            if function_name != "execute_command":
              logger.error(f"⚠️ Invalid function call: {function_name} - only execute_command allowed")
              continue
              
            res = functools.partial(self.execute_command)(**function_params)
            execution_prompt.append({"role": 'tool', "content": json.dumps(res), "tool_call_id": tool_call.id})
            
            # Log command execution with details
            logger.info(f"📤 Command result for task {task_id}: RC={res.get('return_code', 'N/A')}, Output length={len(res.get('stdout', ''))}")
            if res.get('return_code', 0) != 0:
              logger.warning(f"⚠️ Non-zero return code for task {task_id}: {res.get('stderr', 'No error details')}")
            
            command_log.append({
              "command": command,
              "result": f"RC:{res.get('return_code', 'N/A')} | {res.get('stdout', '')[:50]}"
            })
            
            # Update command log in real-time
            if len(command_log) % 2 == 0:  # Update every 2 commands
              log_text = "\n".join([f"```bash\n{cmd['command']}\n```\n**Result:** `{cmd['result']}`\n" for cmd in command_log])
              self._update_task_file(task_id, {
                "command_log": log_text,
                "status_update": f"💻 Executed {len(command_log)} commands on remote VM"
              })
              logger.info(f"📝 Updated task {task_id} with {len(command_log)} executed commands")
