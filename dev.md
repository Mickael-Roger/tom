# Module Development Guide

This document outlines the process for developing new modules for the Tom LLM chatbot. Modules extend Tom's capabilities by providing new tools and functionalities that the LLM can utilize.

## Module Structure

Each module resides in its own Python file (`.py`) within the `modules/` directory. A typical module file will have the following structure:

```python
import functools
# Import any other necessary libraries

# Module configuration - REQUIRED
tom_config = {
  "module_name": "your_module_name",
  "class_name": "YourModuleClassName",
  "description": "A brief description of what this module does."
}

class YourModuleClassName:
  def __init__(self, config, llm) -> None:
    # Initialize module-specific configurations and resources
    # 'config' will contain the module's specific configuration from config.yml
    # 'llm' is the TomLLM instance, which can be used for LLM-related operations if needed.
    self.module_setting = config.get('some_setting', 'default_value')
    self.llm = llm

    # Define the tools (functions) that the LLM can call
    # These follow the OpenAI function calling schema
    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "your_function_name",
          "description": "Description of what this function does and when to use it.",
          "strict": True, # Optional: Set to True for strict parameter validation
          "parameters": {
            "type": "object",
            "properties": {
              "param1": {
                "type": "string",
                "description": "Description of param1.",
              },
              "param2": {
                "type": "integer",
                "description": "Description of param2.",
              },
            },
            "required": ["param1"], # List of required parameters
            "additionalProperties": False, # Optional: Set to False to disallow extra parameters
          },
        },
      },
      # Add more tools as needed
    ]

    # System context for the LLM (optional, but recommended)
    # This string provides additional instructions or context to the LLM about the module's behavior.
    self.systemContext = "This module is designed to help with specific tasks related to [your module's domain]."

    # Module complexity (integer, typically 0 or 1)
    # This might be used for prioritization or filtering by the LLM.
    self.complexity = 0

    # Map tool names to their corresponding Python functions within this class
    self.functions = {
      "your_function_name": {
        "function": functools.partial(self.your_function_implementation)
      },
      # Map other functions here
    }

  # Implement the functions defined in self.tools
  def your_function_implementation(self, param1, param2=None):
    """
    Implementation of your_function_name.
    This method will be called when the LLM decides to use this tool.
    """
    # Your module logic here
    result = f"Function called with param1: {param1}, param2: {param2}"
    return result

  # Add other helper methods as needed
  def _private_helper_method(self):
    pass
```

## Key Components Explained

### `tom_config` Dictionary

This dictionary is crucial for Tom to discover and load your module. It must be defined at the top level of your module file.

*   `module_name` (string): A unique identifier for your module. This name will be used in `config.yml` to enable the module for a user.
*   `class_name` (string): The exact name of the main class within your module file.
*   `description` (string): A concise description of the module's purpose. This description is used by Tom to inform the LLM about the module's capabilities.

### Main Module Class (`YourModuleClassName`)

This class encapsulates all the logic and tools for your module.

*   **`__init__(self, config, llm)`**:
    *   `config`: A dictionary containing the module-specific configuration loaded from `config.yml`. You should define any configurable parameters for your module here.
    *   `llm`: An instance of the `TomLLM` class. You can use this object to interact with the LLM, for example, to generate responses or call other LLM-related functionalities if your module requires it.

*   **`self.tools`**:
    This is a list of dictionaries, where each dictionary describes a function that the LLM can call. The structure adheres to the [OpenAI function calling schema](https://platform.openai.com/docs/guides/function-calling/function-calling).

    *   `type`: Always `"function"`.
    *   `function`: A dictionary describing the function.
        *   `name` (string): The name of the function as it will be exposed to the LLM. This name must be unique across all modules.
        *   `description` (string): A detailed description of what the function does, its purpose, and when the LLM should consider calling it. This is critical for the LLM to correctly understand and utilize your tool.
        *   `strict` (boolean, optional): If `True`, the LLM must provide all required parameters, and no additional parameters are allowed. Defaults to `False`.
        *   `parameters`: A JSON Schema object defining the input parameters for the function.
            *   `type`: Always `"object"`.
            *   `properties`: A dictionary where keys are parameter names and values are their JSON Schema definitions (e.g., `{"type": "string", "description": "..."}`).
            *   `required`: A list of strings, specifying the names of parameters that are mandatory.
            *   `additionalProperties` (boolean, optional): If `False`, the LLM is not allowed to provide parameters not explicitly defined in `properties`. Defaults to `True`.

*   **`self.systemContext`**:
    A string that provides additional context or instructions to the LLM about how to use this module. This can include guidelines on when to invoke the module's functions, specific nuances of its operation, or any other information that helps the LLM make better decisions.

*   **`self.complexity`**:
    An integer value (e.g., 0 or 1) indicating the complexity of the module. This might be used internally by Tom or the LLM for various purposes, such as prioritizing tool usage or filtering.

*   **`self.functions`**:
    A dictionary that maps the `name` of each tool defined in `self.tools` to the actual Python method within your class that implements that tool's logic. It's highly recommended to use `functools.partial(self.your_method_name)` to correctly bind the method to the instance.

### Function Implementation

Each function defined in `self.tools` must have a corresponding method within your module class. The method's signature should match the parameters defined in the `parameters` schema of your tool.

```python
  def your_function_implementation(self, param1, param2=None):
    # Your logic here
    # Access module settings via self.module_setting
    # Interact with the LLM via self.llm if necessary
    return "Result of the function call"
```

## Module Configuration (`config.yml`)

To enable your module for a specific user, you need to add it to the `config.yml` file under the `services` section for that user.

Example `config.yml` entry:

```yaml
users:
  - username: your_username
    password: your_password
    services:
      your_module_name: # This must match the 'module_name' in tom_config
        some_setting: value # Module-specific configuration
        another_setting: another_value
```

## Example Module (`modules/tomexample.py`)

Here's a minimal example of a new module:

```python
import functools

tom_config = {
  "module_name": "example",
  "class_name": "TomExample",
  "description": "A simple example module to demonstrate module development."
}

class TomExample:
  def __init__(self, config, llm) -> None:
    self.greeting_message = config.get('greeting', 'Hello from Example Module!')
    self.llm = llm # In case you need to interact with the LLM from your module

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "get_example_greeting",
          "description": "Returns a predefined greeting message from the example module.",
          "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "echo_message",
          "description": "Echoes back a message provided by the user.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "message": {
                "type": "string",
                "description": "The message to echo back.",
              },
            },
            "required": ["message"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = "This module provides basic example functionalities for demonstration purposes."
    self.complexity = 0

    self.functions = {
      "get_example_greeting": {
        "function": functools.partial(self.get_greeting)
      },
      "echo_message": {
        "function": functools.partial(self.echo)
      },
    }

  def get_greeting(self):
    """Returns the configured greeting message."""
    return self.greeting_message

  def echo(self, message):
    """Echoes back the provided message."""
    return f"You said: {message}"
```

## Development Workflow

1.  **Create your module file**: Place your new `.py` file in the `modules/` directory.
2.  **Define `tom_config`**: Ensure `module_name`, `class_name`, and `description` are correctly set.
3.  **Implement your module class**:
    *   Define the `__init__` method to handle configuration and LLM instance.
    *   Populate `self.tools` with the functions your module exposes to the LLM.
    *   Set `self.systemContext` and `self.complexity`.
    *   Map your tool names to their Python implementations in `self.functions`.
4.  **Implement your functions**: Write the Python methods that perform the actual work for each tool.
5.  **Update `config.yml`**: Add your module to the `services` section for the desired users, including any module-specific configuration.
6.  **Restart the server**: For changes to take effect, you will need to restart the `server.py` application.

By following these guidelines, you can effectively extend Tom's capabilities with new, custom modules.
