# Module Development Guide

This document outlines the process for developing new modules for the Tom LLM chatbot. Modules extend Tom's capabilities by providing new tools and functionalities that the LLM can utilize.

## Module Structure

Each module resides in its own Python file (`.py`) within the `modules/` directory. A typical module file will have the following structure:

```python
import functools
import os
import sys
# Import any other necessary libraries

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

# Module configuration - REQUIRED
tom_config = {
  "module_name": "your_module_name",
  "class_name": "YourModuleClassName",
  "description": "A brief description of what this module does.",
  "type": "global"  # "global" or "personal" - Optional, defaults to "global"
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
*   `type` (string, optional): Defines the module type - either "global" or "personal". Global modules have the same configuration for all users (e.g., weather module), while personal modules have user-specific configurations (e.g., email reader). Defaults to "global" if not specified.

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
import os
import sys

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

tom_config = {
  "module_name": "example",
  "class_name": "TomExample",
  "description": "A simple example module to demonstrate module development.",
  "type": "global"
}

class TomExample:
  def __init__(self, config, llm) -> None:
    self.greeting_message = config.get('greeting', 'Hello from Example Module!')
    self.llm = llm # In case you need to interact with the LLM from your module
    
    logger.info("Example module initialized successfully")

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
    logger.debug("Getting greeting message")
    return self.greeting_message

  def echo(self, message):
    """Echoes back the provided message."""
    logger.debug(f"Echoing message: {message}")
    return f"You said: {message}"
```

## Logging Guidelines

All modules must use the centralized logging system for consistent and properly formatted output. The logging system provides structured logs with timestamps, log levels, usernames, and client types.

### Required Logging Setup

All modules must include the following import at the top of the file:

```python
# Logging
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger
```

### Logging Methods

Use the appropriate logging level for different types of messages:

- `logger.debug("Debug message")` - Detailed information for debugging
- `logger.info("Information message")` - General information about operations
- `logger.warning("Warning message")` - Warning messages
- `logger.error("Error message")` - Error messages
- `logger.critical("Critical message")` - Critical error messages

### Important Rules

1. **NEVER use `print()` statements** - All output must use the logging system
2. **Choose appropriate log levels** - Use debug for detailed info, info for general operations, error for issues
3. **Log format is automatic** - The logger automatically adds timestamps, usernames, and client types
4. **Context is preserved** - The logging system maintains user context across function calls

### Example Usage

```python
# Good - Using logger
logger.info("Module initialized successfully")
logger.debug(f"Processing data: {data}")
logger.error(f"Failed to connect to service: {error}")

# Bad - Using print
print("Module initialized successfully")  # Don't do this!
```

## Development Workflow

1.  **Create your module file**: Place your new `.py` file in the `modules/` directory.
2.  **Define `tom_config`**: Ensure `module_name`, `class_name`, and `description` are correctly set.
3.  **Add logging import**: Include the required logging import at the top of your file.
4.  **Implement your module class**:
    *   Define the `__init__` method to handle configuration and LLM instance.
    *   Populate `self.tools` with the functions your module exposes to the LLM.
    *   Set `self.systemContext` and `self.complexity`.
    *   Map your tool names to their Python implementations in `self.functions`.
5.  **Implement your functions**: Write the Python methods that perform the actual work for each tool.
6.  **Use proper logging**: Replace any debug output with appropriate logger calls.
7.  **Update `config.yml`**: Add your module to the `services` section for the desired users, including any module-specific configuration.
8.  **Restart the server**: For changes to take effect, you will need to restart the `server.py` application.

By following these guidelines, you can effectively extend Tom's capabilities with new, custom modules.

## Testing

### Unit Testing Framework

The project uses Python's built-in `unittest` framework for unit testing, with optional `pytest` support. All tests are located in the `tests/` directory.

### Test Structure

Each module should have a corresponding test file following the naming convention `test_<module_name>.py`. For example:
- `modules/tomweather.py` → `tests/test_tomweather.py`
- `modules/tomidfm.py` → `tests/test_tomidfm.py`

### Writing Tests

When creating unit tests for modules, follow these guidelines:

1. **Mock external dependencies**: Use `unittest.mock` to mock API calls, database connections, and file operations
2. **Mock the logger**: Since modules use the centralized logging system, mock the logger to avoid initialization issues:
   ```python
   from unittest.mock import patch
   
   # Mock logger during import
   with patch('tomweather.logger') as mock_logger:
       from tomweather import TomWeather
   
   # Or use decorator for specific tests
   @patch('tomweather.logger')
   def test_function(self, mock_logger):
       # test code here
   ```

3. **Test all public methods**: Include tests for all functions exposed in `self.functions`
4. **Use temporary files for databases**: Use `tempfile` for SQLite databases in tests
5. **Test error conditions**: Include tests for API failures, invalid inputs, and edge cases
6. **Verify tool structure**: Test that `self.tools` and `self.functions` are properly structured

### Example Test Structure

```python
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import tempfile

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before import
with patch('tomweather.logger') as mock_logger:
    from tomweather import TomWeather

class TestTomWeather(unittest.TestCase):
    
    def setUp(self):
        self.config = {'api_key': 'test_key'}
        self.llm = MagicMock()
        self.weather = TomWeather(self.config, self.llm)
    
    @patch('tomweather.requests.get')
    def test_api_call_success(self, mock_get):
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'test'}
        mock_get.return_value = mock_response
        
        result = self.weather.some_function()
        
        self.assertEqual(result, expected_result)
    
    def test_tools_structure(self):
        # Test that tools are properly structured
        self.assertIsInstance(self.weather.tools, list)
        for tool in self.weather.tools:
            self.assertIn('type', tool)
            self.assertEqual(tool['type'], 'function')
```

### Running Tests

#### Local Testing

Run tests using `unittest`:
```bash
# Run all tests
python -m unittest discover -s tests -p "test_*.py" -v

# Run specific test file
python -m unittest tests.test_tomweather -v

# Run specific test method
python -m unittest tests.test_tomweather.TestTomWeather.test_convertWMO_valid_codes -v
```

Run tests using `pytest` (if available):
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_tomweather.py -v

# Run with coverage
python -m pytest tests/ --cov=modules --cov-report=html
```

#### Docker Testing

The project includes Docker configurations for running tests in isolated environments.

##### Build Test Images

```bash
# Build test image with pytest (supports both unit and integration tests)
docker build -f Dockerfile.test -t tom-tests .

# Build test image with unittest (unit tests only)
docker build -f Dockerfile.test-unittest -t tom-tests-unittest .
```

##### Run Tests with Docker

**Unit Tests (mocked dependencies):**
```bash
# Run all unit tests with pytest
docker run --rm tom-tests

# Run specific unit test file with pytest
docker run --rm tom-tests tests/test_tomweather.py 

```

**Integration Tests (real API calls):**
```bash
# Copy and configure the test config file
cp config.yml.test-example config.yml
# Edit config.yml with your real API tokens and database paths

# Create data directory for cache databases
mkdir -p data

# Run all tests (unit + integration) with mounted config and data
docker run --rm \
  -v $(pwd)/config.yml:/config.yml:ro \
  -v $(pwd)/data:/app/data \
  tom-tests

# Run only integration tests
docker run --rm \
  -v $(pwd)/config.yml:/config.yml:ro \
  -v $(pwd)/data:/app/data \
  tom-tests tests/test_*_integration.py 

# Run specific integration test
docker run --rm \
  -v $(pwd)/config.yml:/config.yml:ro \
  -v $(pwd)/data:/app/data \
  tom-tests tests/test_tomidfm_integration.py::TestTomIdfmIntegration::test_real_search_station 
```

**Mixed Testing (unit tests without config, integration tests skipped):**
```bash
# Run all tests without config (integration tests will be skipped)
docker run --rm tom-tests

# This will run unit tests normally and skip integration tests that require config
```

##### Docker Test Files

- `Dockerfile.test`: Uses pytest for running all tests (unit and integration)
- `Dockerfile.test-unittest`: Uses unittest for running unit tests only

The main test image is based on the same Python environment as the main application and includes all necessary dependencies. It can run both unit tests (with mocked dependencies) and integration tests (with real API calls) depending on whether configuration is mounted.

### Test Coverage

Aim for comprehensive test coverage including:

- **Success cases**: Normal operation with valid inputs
- **Error cases**: API failures, network issues, invalid responses
- **Edge cases**: Empty data, boundary values, malformed inputs
- **Configuration**: Different config values and missing configs
- **Integration**: How functions work together within the module

### Integration Tests

Some modules (like IDFM) require real API calls and configuration. For these modules, create separate integration test files following the pattern `test_<module_name>_integration.py`.

#### Integration Test Requirements

1. **Configuration**: Integration tests require a real `config.yml` file with valid API tokens
2. **External Dependencies**: Tests make real API calls and may require internet connectivity
3. **Database Access**: Tests may require read/write access to cache databases
4. **Slower Execution**: Integration tests are slower than unit tests due to network calls

#### Example Integration Test Structure

```python
class TestTomIdfmIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Load real configuration once for all tests"""
        try:
            with open('/config.yml', 'r') as file:
                config = yaml.safe_load(file)
                cls.idfm_config = config['idfm']
                cls.config_loaded = True
        except:
            cls.config_loaded = False
    
    def setUp(self):
        if not self.config_loaded:
            self.skipTest("Config file not available")
        self.idfm = TomIdfm(self.idfm_config, None)
    
    def test_real_api_call(self):
        """Test with real API call"""
        result = self.idfm.search_station("Châtelet")
        if result is not False:  # API might fail, that's OK
            self.assertIsInstance(result, list)
```

#### Running Integration Tests

Integration tests require additional setup:

1. **Create configuration file**: Copy `config.yml.test-example` to `config.yml` and add real API tokens and service credentials
2. **Mount volumes**: When running in Docker, mount the config file and data directories  
3. **Handle API failures**: Integration tests should gracefully handle API failures and network issues
4. **External service dependencies**: Some modules require external services:
   - **IDFM module**: Requires IDFM API token and internet connectivity
   - **TODO module**: Requires CalDAV server access (e.g., Nextcloud, ownCloud)

#### Configuration Examples

**IDFM Module:**
```yaml
idfm:
  token: "your_idfm_api_token"
  cache_db: "/app/data/idfm_cache.db"
```

**TODO Module:**
```yaml
todo:
  list: "Todo"  # Name of your CalDAV todo list
  password: "your_caldav_password"  
  url: "https://your-server.com/remote.php/dav/"
  user: "your_caldav_username"
```

### Continuous Integration

When setting up CI/CD pipelines, use the Docker test images for consistent testing environments:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    docker build -f Dockerfile.test -t tom-tests .
    docker run --rm tom-tests
```

### Test Dependencies

The following packages are available for testing:
- `unittest` (built-in)
- `pytest` (optional, added to requirements.txt)
- `unittest.mock` (built-in)
- `tempfile` (built-in)

### Best Practices

1. **Keep tests independent**: Each test should be able to run in isolation
2. **Use descriptive test names**: Test names should clearly indicate what is being tested
3. **Mock external services**: Never make real API calls or database connections in tests
4. **Test both positive and negative cases**: Include tests for expected failures
5. **Use setUp and tearDown**: Clean up resources (like temporary files) after tests
6. **Mock the logger**: Always mock the logger to avoid dependency issues
7. **Test tool definitions**: Verify that `self.tools` and `self.functions` are properly structured

By following these testing guidelines, you can ensure that your modules are robust, reliable, and maintainable.
