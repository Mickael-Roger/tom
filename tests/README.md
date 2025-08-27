# Tom Tests Documentation

This directory contains testing tools and scripts for the Tom chatbot system.

## Available Tests

### 1. Combined MCP & Triage Testing (`test_triage.py`)

A comprehensive testing script that performs two main operations:

#### **Phase 1: MCP Server Analysis**
- Extracts descriptions, tools, and resources from all MCP servers in `/app/mcp/`
- Analyzes server structure by static code parsing
- Retrieves the triage prompt and tools from `tomllm.py` using AST parsing
- Outputs detailed JSON with server capabilities

#### **Phase 2: Triage Performance Testing**
- Tests triage functionality across multiple LLM models
- Uses test cases from `triage_test_cases.yaml`
- Measures execution times and success rates
- Validates module selection accuracy

## Usage

### Web Dashboard (Recommended)
The easiest way to run tests and view results is through the web dashboard:

```bash
# Build and run the container with web interface
docker build -t tom-test -f dockerfiles/test/Dockerfile .
docker run -it --rm -p 8080:80 -v /path/to/data:/data tom-test

# Open your browser to http://localhost:8080
```

The web dashboard provides:
- ✨ **Interactive Interface**: Start/stop tests with buttons
- 📊 **Real-time Logs**: Watch test progress live
- 📈 **Visual Results**: Charts and graphs of LLM performance  
- 🔍 **Filtering**: Filter results by LLM, success rate, etc.
- 📥 **Downloads**: Download result files directly

### Command Line Usage
You can still run tests directly from command line:

```bash
# Inside the container
python /app/tests/test_triage.py

# With debug mode
python /app/tests/test_triage.py --debug
```

## Files Structure

```
tests/
├── README.md                          # This documentation
├── test_triage.py                     # Main testing script (CLI)
├── web_dashboard.py                   # Web dashboard server
├── templates/
│   └── dashboard.html                 # Web interface template
├── triage_test_cases.yaml            # Test cases and LLM configurations
├── combined_test_report_*.yaml       # Generated combined reports
└── mcp_descriptions_*.json           # Generated MCP analysis
```

## Configuration Files

### `triage_test_cases.yaml`

Defines test scenarios and LLM configurations:

```yaml
llms:
  - llm: deepseek
    model: deepseek/deepseek-chat
    price:
      cache_hit: 0.07
      cache_miss: 0.56
      output: 1.68

test_cases:
  - prompt: "What's on my schedule for tomorrow?"
    expected_modules: ["calendar"]
    description: "Basic calendar query"
```

#### Test Case Structure
- `prompt`: User input to test
- `expected_modules`: List of modules that should be triggered
- `description`: Human-readable test description

#### LLM Configuration
- `llm`: LLM name (must match main config.yml)
- `model`: Model identifier for litellm
- `price`: Cost information (cache_hit, cache_miss, output per 1M tokens)

## Requirements

### Environment Setup
The script requires:
1. Access to `/data/config.yml` with LLM configurations
2. API keys properly configured in environment variables
3. Access to MCP server files in `/app/mcp/`
4. Python packages: `litellm`, `yaml`, `statistics`, `ast`, `mcp`, `fastmcp`

### Docker Container
The test container includes a web dashboard and CLI tools. All source files (mcp/, lib/, tests/) are copied during build.

#### Web Dashboard Mode (Default)
```bash
# Build and run with web interface
docker build -t tom-test -f dockerfiles/test/Dockerfile .
docker run -it --rm -p 8080:80 -v /path/to/data:/data tom-test

# Access dashboard at http://localhost:8080
```

#### Interactive CLI Mode
```bash
# Run container with bash for manual testing
docker run -it --rm -v /path/to/data:/data tom-test bash

# Inside the container
python /app/tests/test_triage.py --debug
```

#### Background Service Mode
```bash
# Run as detached service
docker run -d --name tom-test -p 8080:80 -v /path/to/data:/data tom-test

# View logs
docker logs -f tom-test

# Stop service
docker stop tom-test && docker rm tom-test
```

## Web Dashboard Features

### Main Interface
- **Test Control Panel**: Start/stop tests with debug mode option
- **Live Logs**: Real-time test execution logs with color coding
- **Quick Stats**: Overview of latest test results and performance
- **Status Indicator**: Visual indication of test running state

### Results Visualization
- **Performance Charts**: 
  - Response Time Chart: Comparative bar chart showing min/max/median response times for successful requests
  - Success Rate Chart: Color-coded bars showing LLM accuracy with performance-based coloring (red to green)
- **Results Grid**: Card-based view of all test runs
- **LLM Filtering**: Filter results by specific LLM providers
- **Detailed View**: Modal with comprehensive test data, failure analysis, and per-LLM statistics
- **Download Links**: Direct access to generated report files

### Interactive Features
- **Real-time Updates**: Auto-refresh during test execution
- **Responsive Design**: Works on desktop and mobile devices
- **Error Handling**: Graceful handling of test failures and API errors
- **Log Management**: Automatic log rotation and archiving

### API Endpoints
- `POST /api/start_test` - Start new test run (with optional debug)
- `GET /api/test_status` - Get current test status and live logs
- `GET /api/results` - Get all test results summary
- `GET /api/results/<id>` - Get detailed results for specific run
- `POST /api/stop_test` - Stop currently running test
- `GET /download/<filename>` - Download result files

## Output Reports

### Combined Report (`combined_test_report_*.yaml`)

Complete analysis including:

```yaml
report_info:
  generated_at: "2025-01-XX..."
  report_type: "combined_mcp_and_triage_analysis"

mcp_analysis:
  triage_prompt: "As an AI assistant..."
  triage_tools: [
    {
      "type": "function",
      "function": {
        "name": "modules_needed_to_answer_user_prompt",
        "description": "This function is used to execute the appropriate module..."
      }
    }
  ]
  servers:
    - filename: "calendar_server.py"
      server_name: "calendar"
      description: "Calendar management service"
      tools: [...]
      resources: [...]

triage_performance:
  test_summary:
    total_llms: 7
    total_test_cases: 25
    total_tests: 175
  llm_results:
    deepseek:
      summary:
        success_rate: 0.85
        min_time_ms: 450.123
        max_time_ms: 2310.456
        median_time_ms: 870.234
        mean_time_ms: 1025.789
      failures: [...]
```

### MCP Descriptions (`mcp_descriptions_*.json`)

Standalone MCP analysis for easy consumption:

```json
{
  "triage_prompt": "As an AI assistant...",
  "triage_tools": [
    {
      "type": "function",
      "function": {
        "name": "modules_needed_to_answer_user_prompt",
        "description": "This function is used to execute the appropriate module..."
      }
    }
  ],
  "servers": [...],
  "summary": {
    "total_servers": 16,
    "successful_extractions": 15,
    "failed_extractions": 1
  }
}
```

## Debug Mode

### Enabling Debug Mode
```bash
python /app/tests/test_triage.py --debug
```

### Debug Output Features
- **Configuration Loading**: YAML parsing, available keys
- **LLM Setup**: Environment variables, API key presence
- **LLM Calls**: Detailed request/response tracing
- **Module Extraction**: Tool call analysis, argument parsing
- **Test Results**: Individual test outcomes, matching logic

### Debug Output Format
```
[HH:MM:SS.mmm] LEVEL: message
```

Levels: `DEBUG`, `TRACE`, `ERROR`
Output: `stderr` (separate from main output)

## Testing Best Practices

### Writing Test Cases
1. **Clear Intent**: Each test should have a single, clear purpose
2. **Expected Behavior**: Define exact modules that should be triggered
3. **Language Coverage**: Include both English and French prompts
4. **Edge Cases**: Test greeting detection, multi-module scenarios
5. **Realistic Prompts**: Use natural user language

### Interpreting Results
- **Success Rate**: Percentage of correct module selections
- **Timing Analysis**: Performance across different LLMs (measured in milliseconds with 3 decimal places)
- **Failure Analysis**: Review `failures` array for patterns
- **Cost Analysis**: Consider price per token for optimization

### Troubleshooting Common Issues

#### All Tests Failing
1. Enable debug mode: `--debug`
2. Check API key configuration
3. Verify `/data/config.yml` structure
4. Confirm LLM names match between files

#### Missing Dependencies Error
If you see `No module named 'litellm'`:
1. Rebuild the Docker container: `docker build -t tom-test -f dockerfiles/test/Dockerfile .`
2. Ensure you're running inside the test container, not the host system
3. Check that all required packages are installed in the container

#### Source File Changes Not Reflected
Since source files are copied into the container (not mounted), you must rebuild after changes:
1. Make your changes to `mcp/`, `lib/`, or `tests/` files
2. Rebuild the container: `docker build -t tom-test -f dockerfiles/test/Dockerfile .`
3. Run the new container to see your changes

#### Inconsistent Results
1. Review triage prompt changes
2. Check module descriptions accuracy
3. Validate test case expectations
4. Consider LLM model updates

#### Performance Issues
1. Monitor API rate limits
2. Check network connectivity
3. Verify retry logic effectiveness
4. Review timeout configurations

## Integration with Tom System

### Configuration Sync
- Test LLMs must exist in main `/data/config.yml`
- Module names must match MCP server names
- API keys must be properly configured

### Module Descriptions
- Descriptions are extracted from actual MCP servers
- Changes to MCP servers automatically reflected in tests
- Triage prompt and tools pulled from live `tomllm.py` code using AST parsing
- Tools structure includes both `modules_needed_to_answer_user_prompt` and `reset_conversation` functions

### Continuous Testing
The test suite can be integrated into CI/CD workflows:
1. Run after MCP server changes
2. Validate triage prompt modifications
3. Performance regression testing
4. LLM model comparison studies

## Maintenance

### Regular Updates
- **Test Cases**: Add new scenarios as features evolve
- **LLM Models**: Update model identifiers and pricing
- **Module Descriptions**: Sync with MCP server changes
- **Expected Results**: Validate after triage logic changes

### Version Control
- Track test case evolution
- Document expected behavior changes
- Maintain compatibility across Tom versions
- Archive historical test results for analysis