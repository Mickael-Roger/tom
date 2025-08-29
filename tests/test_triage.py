#!/usr/bin/env python3
"""
Tom Triage Testing Suite
1. Extracts service descriptions from all MCP servers by static analysis
2. Tests triage functionality across multiple LLM models with various prompts
3. Measures performance and accuracy of module selection across different LLMs
"""

import json
import os
import sys
import time
import yaml
import statistics
import importlib.util
import inspect
import argparse
import ast
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add lib and mcp directories to path
sys.path.insert(0, '/app/lib')
sys.path.insert(0, '/app/mcp')

# --- Live Report Generation ---
STATUS_FILE = '/app/tests/triage_status.json'
_status_data = {}

def _write_status():
    """Writes the current status data to the JSON file."""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(_status_data, f, indent=2)
    except Exception as e:
        print(f"CRITICAL: Could not write to status file {STATUS_FILE}: {e}", file=sys.stderr)

def init_live_report():
    """Initializes the live report file."""
    global _status_data
    _status_data = {
        'status': 'initializing',
        'start_time': datetime.now().isoformat(),
        'end_time': None,
        'progress': {
            'overall': {'current': 0, 'total': 0, 'text': 'Initializing...'},
            'test_case': {'current': 0, 'total': 0, 'text': ''}
        },
        'results': {},
        'logs': [],
        'error': None
    }
    _write_status()

def update_live_report(status=None, overall_progress=None, test_case_progress=None, results=None, log=None, end_time=False, error=None):
    """Updates the live report file with new data."""
    global _status_data
    if status:
        _status_data['status'] = status
    if overall_progress:
        _status_data['progress']['overall'].update(overall_progress)
    if test_case_progress is not None:
        _status_data['progress']['test_case'] = test_case_progress
    if results:
        _status_data['results'] = results
    if log:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': log.get('level', 'INFO'),
            'message': log.get('message', '').strip()
        }
        _status_data['logs'].append(log_entry)
        _status_data['logs'] = _status_data['logs'][-100:]
        print(f"[{log_entry['level']}] {log_entry['message']}")
        sys.stdout.flush()
    if end_time:
        _status_data['end_time'] = datetime.now().isoformat()
    if error:
        _status_data['error'] = error
    
    _write_status()
# --- End of Live Report Generation ---

# Global debug flag
DEBUG = False


def debug_print(message: str, level: str = "DEBUG"):
    """Print debug message if debug mode is enabled"""
    if DEBUG:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}", file=sys.stderr)


def extract_server_info(server_file_path: str) -> Dict[str, Any]:
    """Extract information from a single MCP server file"""
    server_info = {
        "filename": os.path.basename(server_file_path),
        "server_name": "",
        "description": "",
        "tools": [],
        "resources": [],
        "error": None
    }
    
    try:
        # Load the module
        spec = importlib.util.spec_from_file_location("mcp_server", server_file_path)
        if spec is None or spec.loader is None:
            server_info["error"] = "Could not load module specification"
            return server_info
            
        module = importlib.util.module_from_spec(spec)
        
        # Extract static information by reading file content
        with open(server_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract SERVER_DESCRIPTION
        lines = content.split('\n')
        for line in lines:
            if 'SERVER_DESCRIPTION' in line and '=' in line:
                # Extract the description string
                parts = line.split('=', 1)
                if len(parts) == 2:
                    desc = parts[1].strip()
                    if desc.startswith('"') and desc.endswith('"'):
                        server_info["description"] = desc[1:-1]
                    elif desc.startswith('"""') and desc.endswith('"""'):
                        server_info["description"] = desc[3:-3].strip()
                break
        
        # Extract server name from FastMCP initialization
        for line in lines:
            if 'FastMCP(' in line and 'name=' in line:
                # Extract server name
                start = line.find('name="') + 6
                if start > 5:
                    end = line.find('"', start)
                    if end > start:
                        server_info["server_name"] = line[start:end]
                break
        
        # Extract tools and resources by looking for decorators
        in_function = False
        current_function = ""
        current_docstring = ""
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Look for tool decorators
            if '@server.tool(' in stripped:
                # Next non-empty line should be function definition
                for j in range(i+1, min(i+10, len(lines))):
                    next_line = lines[j].strip()
                    if next_line.startswith('def '):
                        func_name = next_line.split('(')[0].replace('def ', '')
                        
                        # Extract docstring
                        docstring = ""
                        for k in range(j+1, min(j+20, len(lines))):
                            doc_line = lines[k].strip()
                            if doc_line.startswith('"""') and doc_line.endswith('"""') and len(doc_line) > 6:
                                docstring = doc_line[3:-3]
                                break
                            elif doc_line.startswith('"""'):
                                # Multi-line docstring
                                docstring_lines = [doc_line[3:]]
                                for l in range(k+1, min(k+50, len(lines))):
                                    doc_end_line = lines[l].strip()
                                    if doc_end_line.endswith('"""'):
                                        docstring_lines.append(doc_end_line[:-3])
                                        break
                                    else:
                                        docstring_lines.append(lines[l].strip())
                                docstring = ' '.join(docstring_lines).strip()
                                break
                        
                        server_info["tools"].append({
                            "name": func_name,
                            "description": docstring
                        })
                        break
            
            # Look for resource decorators
            elif '@server.resource(' in stripped:
                # Extract resource URL
                start = stripped.find('"') + 1
                end = stripped.find('"', start)
                if start > 0 and end > start:
                    resource_url = stripped[start:end]
                    
                    # Next non-empty line should be function definition
                    for j in range(i+1, min(i+10, len(lines))):
                        next_line = lines[j].strip()
                        if next_line.startswith('def '):
                            func_name = next_line.split('(')[0].replace('def ', '')
                            
                            # Extract docstring
                            docstring = ""
                            for k in range(j+1, min(j+20, len(lines))):
                                doc_line = lines[k].strip()
                                if doc_line.startswith('"""') and doc_line.endswith('"""') and len(doc_line) > 6:
                                    docstring = doc_line[3:-3]
                                    break
                                elif doc_line.startswith('"""'):
                                    # Multi-line docstring
                                    docstring_lines = [doc_line[3:]]
                                    for l in range(k+1, min(k+50, len(lines))):
                                        doc_end_line = lines[l].strip()
                                        if doc_end_line.endswith('"""'):
                                            docstring_lines.append(doc_end_line[:-3])
                                            break
                                        else:
                                            docstring_lines.append(lines[l].strip())
                                    docstring = ' '.join(docstring_lines).strip()
                                    break
                            
                            server_info["resources"].append({
                                "url": resource_url,
                                "function": func_name,
                                "description": docstring
                            })
                            break
        
    except Exception as e:
        server_info["error"] = str(e)
    
    return server_info


def extract_triage_prompt() -> str:
    """Extract the triage prompt from tomllm.py"""
    tomllm_path = "/app/lib/tomllm.py"
    triage_prompt = ""
    
    try:
        with open(tomllm_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Look for the triage prompt in the triage_modules method
        lines = content.split('\n')
        in_triage_prompt = False
        prompt_lines = []
        
        for line in lines:
            # Start capturing when we find the prompt variable assignment
            if 'prompt = f\'\'\'' in line:
                in_triage_prompt = True
                # Get the content after the triple quotes
                prompt_start = line.split('prompt = f\'\'\'')[1]
                if prompt_start:
                    prompt_lines.append(prompt_start)
                continue
            
            # End capturing when we find the closing triple quotes
            if in_triage_prompt and line.strip().endswith('\'\'\''):
                # Get the content before the triple quotes
                prompt_end = line.replace('\'\'\'', '')
                if prompt_end.strip():
                    prompt_lines.append(prompt_end)
                break
            
            # Capture lines in between
            if in_triage_prompt:
                prompt_lines.append(line)
        
        triage_prompt = '\n'.join(prompt_lines).strip()
        
    except Exception as e:
        triage_prompt = f"Error extracting triage prompt: {str(e)}"
    
    return triage_prompt


def extract_triage_tools() -> List[Dict]:
    """Extract the triage tools from tomllm.py"""
    tomllm_path = "/app/lib/tomllm.py"
    
    try:
        with open(tomllm_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parse the Python file as AST to find the tools definition
        tree = ast.parse(content)
        
        # Find the triage_modules method and extract the tools variable
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'triage_modules':
                # Look for the tools assignment
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name) and target.id == 'tools':
                                # Found the tools assignment, evaluate it
                                # We need to handle the dynamic modules_name_list part
                                debug_print("Found tools assignment in triage_modules method")
                                
                                # For now, return a static representation of the tools structure
                                # since modules_name_list is dynamic
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
                                                        "enum": "[DYNAMIC_MODULES_LIST]",
                                                        "description": "Module name needed to answer the user's request"
                                                    }
                                                },
                                                "required": ["modules_name"],
                                                "additionalProperties": False
                                            }
                                        }
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
                                                "additionalProperties": False
                                            }
                                        }
                                    }
                                ]
                                debug_print(f"Extracted {len(tools)} triage tools")
                                return tools
        
        debug_print("Could not find tools definition in triage_modules method", "ERROR")
        return []
        
    except Exception as e:
        debug_print(f"Error extracting triage tools: {str(e)}", "ERROR")
        return []


def extract_all_mcp_descriptions() -> Dict[str, Any]:
    """Extract descriptions from all MCP servers in the mcp directory"""
    mcp_dir = "/app/mcp"
    results = {
        "triage_prompt": extract_triage_prompt(),
        "triage_tools": extract_triage_tools(),
        "servers": [],
        "summary": {
            "total_servers": 0,
            "successful_extractions": 0,
            "failed_extractions": 0
        }
    }
    
    if not os.path.exists(mcp_dir):
        results["error"] = f"MCP directory not found: {mcp_dir}"
        return results
    
    # Find all Python files in mcp directory
    server_files = []
    for file in os.listdir(mcp_dir):
        if file.endswith("_server.py"):
            server_files.append(os.path.join(mcp_dir, file))
    
    results["summary"]["total_servers"] = len(server_files)
    
    # Extract info from each server
    for server_file in sorted(server_files):
        server_info = extract_server_info(server_file)
        results["servers"].append(server_info)
        
        if server_info["error"] is None:
            results["summary"]["successful_extractions"] += 1
        else:
            results["summary"]["failed_extractions"] += 1
    
    return results


def run_triage_tests() -> Dict[str, Any]:
    """Run all triage tests"""
    update_live_report(log={'message': "Running Triage Performance Tests..."})
    
    # Load configuration
    update_live_report(log={'message': "Loading configuration from /data/config.yml..."})
    config = load_config()
    if not config:
        return {"error": "Failed to load configuration"}
    
    # Load test cases
    update_live_report(log={'message': "Loading test cases and LLM configurations..."})
    test_data = load_test_cases()
    if not test_data:
        return {"error": "Failed to load test cases"}
    
    # Get LLM configurations
    llm_configs = config.get('global', {}).get('llms', {})
    if not llm_configs:
        return {"error": "No LLM configurations found in config.yml"}
    
    # Get test configurations
    test_llms = test_data.get('llms', [])
    test_cases = test_data.get('test_cases', [])
    
    if not test_llms or not test_cases:
        return {"error": "No test LLMs or test cases found"}
    
    update_live_report(log={'message': f"Found {len(test_llms)} test LLMs and {len(test_cases)} test cases"})
    
    # Create available modules and tools
    update_live_report(log={'message': "Extracting MCP server descriptions..."})
    available_modules = create_available_modules()
    update_live_report(log={'message': "Building triage prompt and tools..."})
    triage_instructions = create_triage_prompt()
    system_message = create_json_system_message(triage_instructions, available_modules)
    tools = create_triage_tools(available_modules)
    
    # Results storage
    results = {
        "test_summary": {
            "start_time": datetime.now().isoformat(),
            "total_llms": len(test_llms),
            "total_test_cases": len(test_cases),
            "total_tests": len(test_llms) * len(test_cases)
        },
        "llm_results": {}
    }
    update_live_report(results=results)
    
    # Test each LLM
    total_llms = len(test_llms)
    update_live_report(
        overall_progress={'current': 0, 'total': total_llms, 'text': 'Initialization complete. Starting tests...'},
        log={'message': 'All initialization completed, starting LLM tests...'}
    )
    
    for llm_index, llm_config in enumerate(test_llms):
        llm_name = llm_config['llm']
        model = llm_config['model']
        
        update_live_report(
            overall_progress={'current': llm_index + 1, 'text': f'Testing {llm_name}'},
            test_case_progress={'current': 0, 'total': len(test_cases), 'text': 'Starting...'},
            log={'level': 'INFO', 'message': f"Testing LLM: {llm_name} ({model})"}
        )
        
        if llm_name not in llm_configs:
            update_live_report(log={'level': 'WARNING', 'message': f"{llm_name} not found in main configuration, skipping..."})
            continue
        
        main_llm_config = llm_configs[llm_name]
        setup_success, extra_body_options = setup_llm_environment(main_llm_config)
        if not setup_success:
            update_live_report(log={'level': 'ERROR', 'message': f"Failed to setup environment for {llm_name}"})
            continue
        
        llm_results = {
            "model": model,
            "pricing": llm_config.get('price', {}),
            "tests": [],
            "summary": {
                "total_tests": 0,
                "successful_tests": 0,
                "failed_tests": 0,
                "success_rate": 0.0,
                "execution_times": [],
                "min_time_ms": 0.0,
                "max_time_ms": 0.0,
                "median_time_ms": 0.0,
                "mean_time_ms": 0.0,
                "total_time": 0.0
            },
            "failures": []
        }
        
        total_test_cases = len(test_cases)
        for i, test_case in enumerate(test_cases):
            prompt = test_case['prompt']
            expected_modules = test_case['expected_modules']
            description = test_case['description']
            
            update_live_report(
                test_case_progress={'current': i + 1, 'total': total_test_cases, 'text': description}
            )
            
            test_result = test_single_prompt(
                llm_name, model, prompt, expected_modules, 
                system_message, tools, extra_body_options
            )
            
            test_result['prompt'] = prompt
            test_result['description'] = description
            llm_results['tests'].append(test_result)
            
            llm_results['summary']['total_tests'] += 1
            llm_results['summary']['execution_times'].append(test_result['execution_time_ms'])
            llm_results['summary']['total_time'] += test_result['execution_time_ms']
            
            if test_result['success']:
                llm_results['summary']['successful_tests'] += 1
                update_live_report(log={'level': 'SUCCESS', 'message': f"PASS ({test_result['execution_time_ms']:.1f}ms): {description}"})
            else:
                llm_results['summary']['failed_tests'] += 1
                update_live_report(log={'level': 'ERROR', 'message': f"FAIL ({test_result['execution_time_ms']:.1f}ms): {description}"})
                failure = {
                    "prompt": prompt,
                    "description": description,
                    "expected": test_result['expected'],
                    "received": test_result['received'],
                    "error": test_result.get('error')
                }
                llm_results['failures'].append(failure)
        
        execution_times = llm_results['summary']['execution_times']
        if execution_times:
            llm_results['summary']['min_time_ms'] = round(min(execution_times), 3)
            llm_results['summary']['max_time_ms'] = round(max(execution_times), 3)
            llm_results['summary']['median_time_ms'] = round(statistics.median(execution_times), 3)
            llm_results['summary']['mean_time_ms'] = round(statistics.mean(execution_times), 3)
        
        total_tests = llm_results['summary']['total_tests']
        successful_tests = llm_results['summary']['successful_tests']
        if total_tests > 0:
            llm_results['summary']['success_rate'] = successful_tests / total_tests
        
        results['llm_results'][llm_name] = llm_results
        update_live_report(results=results)
        
        summary_text = f"Results for {llm_name}: {successful_tests}/{total_tests} passed ({llm_results['summary']['success_rate']:.2%})"
        update_live_report(log={'level': 'INFO', 'message': summary_text})

    results['test_summary']['end_time'] = datetime.now().isoformat()
    update_live_report(results=results, overall_progress={'current': total_llms, 'text': 'Tests completed'})
    
    return results


def load_config(config_path: str = '/data/config.yml') -> Dict[str, Any]:
    """Load configuration from YAML file"""
    debug_print(f"Loading configuration from: {config_path}")
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        debug_print(f"Configuration loaded successfully. Keys: {list(config.keys())}")
        if 'global' in config:
            debug_print(f"Global config keys: {list(config['global'].keys())}")
            if 'llms' in config['global']:
                debug_print(f"Available LLMs in config: {list(config['global']['llms'].keys())}")
        return config
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found: {config_path}")
        debug_print(f"Config file does not exist at: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        print(f"ERROR: Error parsing YAML configuration: {exc}")
        debug_print(f"YAML parsing error: {exc}")
        return {}


def load_test_cases(test_cases_path: str = '/app/tests/triage_test_cases.yaml') -> Dict[str, Any]:
    """Load test cases from YAML file"""
    debug_print(f"Loading test cases from: {test_cases_path}")
    try:
        with open(test_cases_path, 'r', encoding='utf-8') as file:
            test_cases = yaml.safe_load(file)
        debug_print(f"Test cases loaded successfully")
        if 'llms' in test_cases:
            debug_print(f"Test LLMs: {[llm['llm'] for llm in test_cases['llms']]}")
        if 'test_cases' in test_cases:
            debug_print(f"Total test cases: {len(test_cases['test_cases'])}")
        return test_cases
    except FileNotFoundError:
        print(f"ERROR: Test cases file not found: {test_cases_path}")
        debug_print(f"Test cases file does not exist at: {test_cases_path}")
        return {}
    except yaml.YAMLError as exc:
        print(f"ERROR: Error parsing test cases YAML: {exc}")
        debug_print(f"Test cases YAML parsing error: {exc}")
        return {}


def setup_llm_environment(llm_config: Dict[str, Any]) -> tuple[bool, Optional[Dict[str, Any]]]:
    """Setup environment variables for LLM provider and return extra_body options"""
    debug_print(f"Setting up LLM environment with config keys: {list(llm_config.keys())}")
    try:
        env_var = llm_config.get("env_var")
        api_key = llm_config.get("api")
        options = llm_config.get("options")
        
        debug_print(f"Environment variable: {env_var}")
        debug_print(f"API key present: {bool(api_key)}")
        debug_print(f"Extra body options present: {bool(options)}")
        
        if not env_var or not api_key:
            debug_print("Missing env_var or api_key")
            return False, None
        
        os.environ[env_var] = api_key
        debug_print(f"Set environment variable {env_var}")
        
        if options:
            debug_print(f"Returning extra_body options: {options}")
        
        return True, options
    except Exception as e:
        debug_print(f"Exception in setup_llm_environment: {e}")
        return False, None


def create_triage_prompt() -> str:
    """Create the triage prompt from tomllm.py"""
    # This is the exact prompt from tomllm.py lines 446-461
    return '''As an AI assistant, you have access to a wide range of functions, far more than your API allows. These functions are grouped into modules. A module is a logical grouping of functions for a specific theme.

For each new user request, you have access to the conversation history.

IMPORTANT: If the user greets you with expressions like "Hello", "Hi", "Salut", "Hi Tom", "Salut Tom", or similar greetings that indicate a fresh start to the conversation, you MUST call the 'reset_conversation' function first before processing any other request. This will clear the conversation history and provide a clean slate for the new conversation.

If you need a function that is not in your list of tools to respond to the user's request, you should call the 'modules_needed_to_answer_user_prompt' function with the necessary modules. You can call the 'modules_needed_to_answer_user_prompt' function as many times as needed.

It is very important that you do not invent module names—only the modules provided in the list exist.

Once you call the 'modules_needed_to_answer_user_prompt' function, the user's request will be sent back to you with the functions from the requested modules added to your tools. At that point, you can choose the appropriate function(s) to respond to the user's request.'''


def create_available_modules() -> List[Dict[str, str]]:
    """Create the list of available modules based on MCP servers"""
    return [
        {"name": "anki", "description": "Anki spaced repetition flashcard management"},
        {"name": "behavior", "description": "Behavior tuning and personalization"},
        {"name": "cafetaria", "description": "Cafeteria menu and food services"},
        {"name": "calendar", "description": "This module is used to manage my personal and familial calendar events, meetings and appointments."},
        {"name": "contacts", "description": "Contact management and address book"},
        {"name": "gpodder", "description": "Podcast management and playback"},
        {"name": "homeconnect", "description": "Home appliance control and automation"},
        {"name": "idfm", "description": "Paris public transport (metro, bus, RER) information and planning"},
        {"name": "kwyk", "description": "Educational platform and homework management"},
        {"name": "memory", "description": "Personal memory management and context storage"},
        {"name": "news", "description": "News aggregation and reading"},
        {"name": "notifications", "description": "Push notification management"},
        {"name": "switchparentalcontrol", "description": "Parental control management"},
        {"name": "todo", "description": "Task and todo list management including grocery lists"},
        {"name": "weather", "description": "Weather forecast and meteorological information"},
        {"name": "youtube", "description": "YouTube video management and playback"}
    ]


def create_triage_tools(available_modules: List[Dict[str, str]]) -> List[Dict]:
    """Create the triage tools for LLM"""
    modules_name_list = [module['name'] for module in available_modules]
    
    return [
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


def create_json_system_message(triage_instructions: str, available_modules: List[Dict[str, str]]) -> Dict[str, Any]:
    """Create JSON system message with triage instructions"""
    from datetime import datetime
    
    tooling = json.dumps(available_modules)
    
    json_content = {
        "description": "Define the assistant's role, style, rules, and available tools.",
        "persona": {
            "name": "Tom",
            "role": "AI assistant specialized in module triage and tool selection",
            "language_policy": "Always respond in the same language as the user (FR/EN); use informal 'tu' if the user writes in French.",
            "style": "clear, structured, markdown-friendly"
        },
        "system_context": {
            "current_date_time": datetime.now().strftime("%A %d %B %Y %H:%M:%S"),
            "week_number": datetime.now().isocalendar().week
        },
        "formatting": {
            "markdown": True,
            "language": "auto-detect to match user input",
            "no_urls_direct": True,
            "context": "Response will be displayed in a web browser or mobile app. Use markdown for better readability. Use [open:URL] tag instead of direct URLs unless explicitly asked."
        },
        "triage_instructions": f"{triage_instructions}\n\n```json\n{tooling}\n```"
    }
    
    return {
        "role": "system",
        "content": json.dumps(json_content, ensure_ascii=False, separators=(',', ':'))
    }


def call_llm_with_retry(model: str, messages: List[Dict], tools: List[Dict], max_retries: int = 2, extra_body: Optional[Dict[str, Any]] = None):
    """Call LLM with retry logic"""
    from litellm import completion
    import time
    
    debug_print(f"Calling LLM model: {model}")
    debug_print(f"Messages count: {len(messages)}")
    debug_print(f"Tools count: {len(tools)}")
    
    if DEBUG:
        debug_print(f"Full messages: {json.dumps(messages, indent=2)}", "TRACE")
        debug_print(f"Full tools: {json.dumps(tools, indent=2)}", "TRACE")
    
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            debug_print(f"LLM call attempt {retry_count + 1}/{max_retries + 1}")
            
            # Check if model is GPT-5
            is_gpt5 = model.startswith("openai/gpt-5")
            debug_print(f"Is GPT-5 model: {is_gpt5}")
            
            if is_gpt5:
                debug_print("Using GPT-5 specific parameters")
                completion_params = {
                    "model": model,
                    "verbosity": "low",
                    "reasoning_effort": "minimal",
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "allowed_openai_params": ["reasoning_effort", "verbosity"],
                }
                if extra_body:
                    completion_params["extra_body"] = extra_body
                    debug_print(f"Using extra_body options: {extra_body}")
                response = completion(**completion_params)
            else:
                debug_print("Using standard parameters")
                completion_params = {
                    "model": model,
                    "temperature": 0,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                }
                if extra_body:
                    completion_params["extra_body"] = extra_body
                    debug_print(f"Using extra_body options: {extra_body}")
                response = completion(**completion_params)
            
            debug_print(f"LLM call successful. Response finish_reason: {response.choices[0].finish_reason if response and response.choices else 'unknown'}")
            if DEBUG and response and response.choices:
                debug_print(f"Response content: {response.choices[0].message.content}", "TRACE")
                if response.choices[0].message.tool_calls:
                    debug_print(f"Tool calls: {len(response.choices[0].message.tool_calls)}")
                    for i, tool_call in enumerate(response.choices[0].message.tool_calls):
                        debug_print(f"Tool call {i+1}: {tool_call.function.name} with args {tool_call.function.arguments}", "TRACE")
            
            return response
            
        except Exception as e:
            error_str = str(e)
            debug_print(f"LLM call failed with error: {error_str}", "ERROR")
            
            is_5xx_error = any(code in error_str for code in ['500', '501', '502', '503', '504', '505', '507', '508', '510', '511'])
            is_5xx_error = is_5xx_error or any(phrase in error_str for phrase in ['Internal Server Error', 'Bad Gateway', 'Service Unavailable', 'Gateway Timeout'])
            
            debug_print(f"Is 5xx error: {is_5xx_error}")
            
            if is_5xx_error and retry_count < max_retries:
                retry_count += 1
                debug_print(f"Retrying after 0.3s (attempt {retry_count}/{max_retries})")
                time.sleep(0.3)
                continue
            else:
                debug_print(f"Not retrying. Final error: {error_str}", "ERROR")
                raise e
    
    debug_print("All retry attempts exhausted")
    return None


def extract_called_modules(response) -> List[str]:
    """Extract modules from LLM response"""
    debug_print("Extracting modules from LLM response")
    modules = []
    reset_called = False
    
    if not response:
        debug_print("No response provided")
        return modules
    
    if not response.choices:
        debug_print("No choices in response")
        return modules
    
    finish_reason = response.choices[0].finish_reason
    debug_print(f"Response finish_reason: {finish_reason}")
    
    if finish_reason == "tool_calls":
        tool_calls = response.choices[0].message.tool_calls
        debug_print(f"Found {len(tool_calls) if tool_calls else 0} tool calls")
        
        if tool_calls:
            for i, tool_call in enumerate(tool_calls):
                function_name = tool_call.function.name
                debug_print(f"Tool call {i+1}: {function_name}")
                
                if function_name == "reset_conversation":
                    debug_print("Reset conversation tool called")
                    reset_called = True
                elif function_name == "modules_needed_to_answer_user_prompt":
                    try:
                        args = json.loads(tool_call.function.arguments)
                        debug_print(f"Tool arguments: {args}")
                        module_name = args.get('modules_name')
                        if module_name:
                            debug_print(f"Module requested: {module_name}")
                            modules.append(module_name)
                        else:
                            debug_print("No modules_name in arguments")
                    except json.JSONDecodeError as e:
                        debug_print(f"Failed to parse tool arguments: {tool_call.function.arguments} - {e}", "ERROR")
                        continue
                else:
                    debug_print(f"Unknown tool function: {function_name}")
    else:
        debug_print(f"Response finish_reason is not 'tool_calls': {finish_reason}")
        if response.choices[0].message.content:
            debug_print(f"Response content: {response.choices[0].message.content}")
    
    # If reset was called, return special indicator
    if reset_called:
        debug_print("Returning reset_conversation indicator")
        return ["reset_conversation"]
    
    unique_modules = list(set(modules))  # Remove duplicates
    debug_print(f"Final extracted modules: {unique_modules}")
    return unique_modules


def test_single_prompt(llm_name: str, model: str, prompt: str, expected_modules: List[str], 
                      system_message: Dict, tools: List[Dict], extra_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Test a single prompt with a specific model"""
    import time
    
    debug_print(f"Testing prompt: '{prompt}' with {llm_name} ({model})")
    debug_print(f"Expected modules: {expected_modules}")
    
    start_time = time.perf_counter()
    
    try:
        # Create conversation
        messages = [
            system_message,
            {"role": "user", "content": prompt}
        ]
        
        debug_print(f"Created conversation with {len(messages)} messages")
        
        # Call LLM
        response = call_llm_with_retry(model, messages, tools, extra_body=extra_body)
        end_time = time.perf_counter()
        execution_time = round((end_time - start_time) * 1000, 3)  # Convert to milliseconds with 3 decimal places
        
        debug_print(f"LLM call completed in {execution_time:.2f}s")
        
        if not response:
            debug_print("No response from LLM", "ERROR")
            return {
                "success": False,
                "error": "Empty response from LLM",
                "execution_time_ms": execution_time,
                "expected": expected_modules,
                "received": []
            }
        
        # Extract called modules
        received_modules = extract_called_modules(response)
        debug_print(f"Received modules: {received_modules}")
        
        # Check if result matches expected
        expected_set = set(expected_modules)
        received_set = set(received_modules)
        
        debug_print(f"Expected set: {expected_set}")
        debug_print(f"Received set: {received_set}")
        
        # Special case for greeting detection
        if "reset_conversation" in received_modules and not expected_modules:
            success = True  # Greeting was properly detected
            debug_print("Greeting detection successful")
        elif expected_set == received_set:
            success = True
            debug_print("Module matching successful")
        else:
            success = False
            debug_print(f"Module mismatch - expected: {expected_set}, received: {received_set}")
        
        result = {
            "success": success,
            "execution_time_ms": execution_time,
            "expected": expected_modules,
            "received": received_modules,
            "generation_id": response.id if response else None,
            "response_details": {
                "finish_reason": response.choices[0].finish_reason,
                "tool_calls": len(response.choices[0].message.tool_calls) if response.choices[0].message.tool_calls else 0
            }
        }
        
        debug_print(f"Test result: {result['success']} - {result}")
        return result
        
    except Exception as e:
        end_time = time.perf_counter()
        execution_time = round((end_time - start_time) * 1000, 3)  # Convert to milliseconds with 3 decimal places
        debug_print(f"Test failed with exception: {e}", "ERROR")
        
        return {
            "success": False,
            "error": str(e),
            "execution_time_ms": execution_time,
            "expected": expected_modules,
            "received": []
        }


import requests

def fetch_and_add_cost_data(triage_results, config):
    """Fetches cost data from OpenRouter for each test and updates the results."""
    update_live_report(log={'message': "Fetching cost data from OpenRouter..."})
    
    # Wait for OpenRouter to process generations
    wait_time = 5
    update_live_report(log={'message': f"Waiting {wait_time} seconds for OpenRouter to process costs..."})
    time.sleep(wait_time)

    llm_configs = config.get('global', {}).get('llms', {})
    if not llm_configs:
        update_live_report(log={'level': 'ERROR', 'message': "No LLM configurations found in config, cannot fetch costs."})
        return triage_results

    for llm_name, llm_data in triage_results.get('llm_results', {}).items():
        if llm_name not in llm_configs:
            continue

        api_key = llm_configs[llm_name].get('api')
        if not api_key:
            update_live_report(log={'level': 'WARNING', 'message': f"No API key found for {llm_name}, cannot fetch costs."})
            continue

        total_cost = 0
        update_live_report(log={'message': f"Fetching costs for {llm_name}..."})

        for test in llm_data.get('tests', []):
            gen_id = test.get('generation_id')
            if not gen_id:
                test['cost'] = 0
                continue

            try:
                headers = {"Authorization": f"Bearer {api_key}"}
                url = f"https://openrouter.ai/api/v1/generation?id={gen_id}"
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                generation_data = response.json().get('data')

                cost = generation_data.get('total_cost')

                if cost is not None:
                    test['cost'] = cost
                    total_cost += cost
                else:
                    test['cost'] = 0
                    update_live_report(log={'level': 'WARNING', 'message': f"Cost not found for generation {gen_id}"})

            except requests.exceptions.RequestException as e:
                update_live_report(log={'level': 'ERROR', 'message': f"Could not fetch cost for {gen_id}: {e}"})
                test['cost'] = 0
        
        llm_data['summary']['total_cost'] = total_cost
        update_live_report(log={'message': f"Total cost for {llm_name}: ${total_cost:.6f}"})

    update_live_report(results=triage_results)
    return triage_results

def main():
    """Main function to extract MCP descriptions and run triage tests"""
    global DEBUG
    import statistics
    from datetime import datetime
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Extract MCP descriptions and run triage tests")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()
    
    # Set global debug flag
    DEBUG = args.debug
    
    init_live_report()
    
    if DEBUG:
        debug_print("Debug mode enabled")
    
    update_live_report(status='running', log={'message': "🔍 MCP Server Description Extraction & Triage Testing"})
    
    # Step 1: Extract MCP descriptions
    update_live_report(log={'message': "Step 1: Extracting MCP Server Descriptions..."})
    mcp_results = extract_all_mcp_descriptions()
    
    update_live_report(log={'level': 'INFO', 'message': f"Extracted descriptions from {mcp_results['summary']['total_servers']} servers"})
    update_live_report(log={'level': 'INFO', 'message': f"  - Successful: {mcp_results['summary']['successful_extractions']}"})
    update_live_report(log={'level': 'INFO', 'message': f"  - Failed: {mcp_results['summary']['failed_extractions']}"})
    
    # Step 2: Run triage tests
    update_live_report(log={'message': "Step 2: Running Triage Performance Tests..."})
    triage_results = run_triage_tests()
    
    if "error" in triage_results:
        update_live_report(status='error', error=triage_results['error'], end_time=True)
        # Still save MCP results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mcp_report_filename = f"/app/tests/mcp_descriptions_{timestamp}.json"
        
        try:
            with open(mcp_report_filename, 'w', encoding='utf-8') as f:
                json.dump(mcp_results, f, indent=2, ensure_ascii=False)
            update_live_report(log={'message': f"📄 MCP descriptions saved to: {mcp_report_filename}"})
        except Exception as e:
            update_live_report(log={'level': 'ERROR', 'message': f"❌ Error saving MCP descriptions: {e}"})
        
        return 1

    # Step 2.5: Fetch cost data
    config = load_config()
    if not config:
        update_live_report(status='error', error="Failed to load configuration for cost fetching.", end_time=True)
        return 1
    triage_results = fetch_and_add_cost_data(triage_results, config)
    
    # Step 3: Combine results and generate reports
    update_live_report(log={'message': "Step 3: Generating Combined Report..."})
    
    # Create combined results
    combined_results = {
        "report_info": {
            "generated_at": datetime.now().isoformat(),
            "report_type": "combined_mcp_and_triage_analysis"
        },
        "mcp_analysis": mcp_results,
        "triage_performance": triage_results
    }
    
    # Generate report filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_report_filename = f"/app/tests/combined_test_report_{timestamp}.yaml"
    mcp_json_filename = f"/app/tests/mcp_descriptions_{timestamp}.json"
    
    try:
        # Save combined report as YAML
        import yaml
        with open(combined_report_filename, 'w', encoding='utf-8') as f:
            yaml.dump(combined_results, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # Save MCP descriptions as separate JSON for easy reading
        with open(mcp_json_filename, 'w', encoding='utf-8') as f:
            json.dump(mcp_results, f, indent=2, ensure_ascii=False)
        
        update_live_report(log={'message': f"📊 Combined report saved to: {combined_report_filename}"})
        update_live_report(log={'message': f"📄 MCP descriptions saved to: {mcp_json_filename}"})
        
        # Print summary
        summary_lines = []
        summary_lines.append("\n📈 Final Summary:")
        summary_lines.append(f"  MCP Servers: {mcp_results['summary']['successful_extractions']}/{mcp_results['summary']['total_servers']} extracted")
        
        if 'llm_results' in triage_results:
            total_llms = len(triage_results['llm_results'])
            summary_lines.append(f"  LLM Testing: {total_llms} models tested")
            
            for llm_name, llm_result in triage_results['llm_results'].items():
                summary = llm_result['summary']
                total_cost = summary.get('total_cost', 0)
                summary_lines.append(f"    {llm_name}: {summary['success_rate']:.2%} success rate, {summary['median_time_ms']:.2f}ms median time, Total Cost: ${total_cost:.6f}")
        
        update_live_report(log={'message': '\n'.join(summary_lines)})
        update_live_report(status='completed', end_time=True)
        return 0
        
    except Exception as e:
        update_live_report(status='error', error=f"Error saving reports: {e}", end_time=True)
        return 1



if __name__ == "__main__":
    main()
