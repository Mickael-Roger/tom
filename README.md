# Tom Chatbot Server

Tom is a multi-user chatbot server application with per-user agent isolation, LLM configuration management, and MCP (Model Context Protocol) support.

## Architecture Overview

### Components

1. **Main Server (`tom.py`)** - HTTPS web server handling authentication and routing
2. **Agent Service (`agent.py`)** - Individual user agent instances with LLM and MCP capabilities
3. **Centralized Logging (`lib/tomlogger.py`)** - Thread-safe logging system with structured output
4. **Configuration Management** - YAML-based configuration with per-user settings

### System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Client    │────│   Tom Server     │────│   User Agent    │
│   (HTTPS)       │    │   (Port 443)     │    │   (Port 8080)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │                         │
                              │                         │
                       ┌──────▼──────┐           ┌──────▼──────┐
                       │  Config.yml │           │   MCP       │
                       │  Sessions   │           │   Servers   │
                       │  TLS Certs  │           │   LLMs      │
                       └─────────────┘           └─────────────┘
```

## Installation

### Prerequisites

- Python 3.13+
- Docker (for containerized deployment)
- TLS certificates for HTTPS
- Configuration files in `/data/`

### Directory Structure

```
/data/
├── config.yml              # Main configuration (includes user MCP services)
├── tls/                     # TLS certificates
│   ├── cert.pem
│   └── key.pem
└── users/                   # (Optional user-specific data directory)
```

### Dependencies

Install Python dependencies:

```bash
pip install cherrypy PyYAML litellm
```

## Configuration

### Main Configuration (`/data/config.yml`)

```yaml
global:
  log_level: INFO
  sessions: /tmp/tom_sessions
  
  # Firebase configuration for push notifications
  firebase:
    apiKey: "your-firebase-api-key"
    authDomain: "your-project.firebaseapp.com"
    projectId: "your-project-id"
    storageBucket: "your-project.appspot.com"
    messagingSenderId: "123456789"
    appId: "1:123456789:web:abcdefghijklmnop"
    vapidkey: "your-vapid-key"
  
  all_datadir: /data/all/
  
  # LLM Configuration
  llm: openai                    # Default LLM
  llm_tts: openrouter-gemini     # TTS LLM
  llms:
    openai:
      api: "sk-proj-..."
      env_var: OPENAI_API_KEY
      models:
        - openai/gpt-4o-mini     # Complexity level 0
        - openai/gpt-4.1         # Complexity level 1
        - openai/gpt-4.1         # Complexity level 2
    gemini:
      api: "AIzaSy..."
      env_var: GEMINI_API_KEY
      models:
        - gemini/gemini-1.5-flash
        - gemini/gemini-1.5-flash
        - gemini/gemini-1.5-flash

users:
  - username: alice
    password: alice123
    personal_context: "Alice is a software developer who prefers technical responses"
    services:
      weather:
        url: "http://weather-service/mcp"
        headers:
          Authorization: "Bearer token123"
          Content-Type: "application/json"
        description: "Weather forecast service"
        llm: "openai"
        enable: true
      calculator:
        url: "http://calc-service/mcp"
        enable: true
  - username: bob
    password: bob456
    personal_context: "Bob prefers concise answers and works in marketing"
    services:
      analytics:
        url: "http://analytics/mcp"
        description: "Marketing analytics service"
        enable: false
```

## Services

### Tom Server (`tom.py`)

**Purpose**: Main HTTPS web server with authentication and reverse proxy capabilities.

**Key Features**:
- HTTPS-only with TLS certificate validation
- Session-based authentication
- Reverse proxy to user-specific agent containers
- Firebase push notification support

**Routes**:
- `/` - Main index page
- `/auth` - Authentication endpoint
- `/login` - User login
- `/logout` - User logout
- `/notificationconfig` - Firebase notification configuration
- `/firebase_messaging_sw_js` - Firebase service worker
- `/fcmtoken` - FCM token management
- `/notifications` - Proxy to user agent
- `/reset` - Proxy to user agent
- `/process` - Proxy to user agent
- `/tasks` - Proxy to user agent

**Configuration**: Reads from `/data/config.yml`

**Logging**: Uses centralized tomlogger with module context

### Agent Service (`agent.py`)

**Purpose**: Per-user agent instances with LLM and MCP capabilities.

**Key Features**:
- Multi-LLM support with complexity-based model selection
- MCP client for external tool integration
- User-specific configuration loading
- Centralized logging integration

**Components**:

1. **LLMConfig Class**:
   - Manages multiple LLM providers
   - Environment variable configuration
   - Model complexity mapping
   - Fallback mechanisms

2. **MCPClient Class**:
   - User-specific MCP service configuration from config.yml
   - URL-based service support with optional headers
   - Personal context management
   - Service enable/disable functionality
   - Configuration validation

3. **TomAgent Class**:
   - CherryPy web service on port 8080
   - Request handling and processing
   - Integration with LLM and MCP systems

**Routes**:
- `/notifications` (GET) - Notifications endpoint
- `/reset` (POST) - Reset user session
- `/tasks` (GET) - Background tasks status
- `/process` (POST) - Main processing endpoint

### Logging System (`lib/tomlogger.py`)

**Purpose**: Centralized, thread-safe logging with structured output.

**Features**:
- Thread-safe singleton pattern
- Custom log formatting with context
- CherryPy integration
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**Log Format**:
```
2025-01-15 10:30:45 | INFO     | alice        | llm             | ✅ Configured LLM 'openai' with models: ['openai/gpt-4o-mini', 'openai/gpt-4.1', 'openai/gpt-4.1']
```

**Context Fields**:
- Timestamp
- Log level
- Username (max 12 chars)
- Module name (max 15 chars)
- Message

## Docker Deployment

### Tom Server Container

```dockerfile
FROM python:3.13-alpine
WORKDIR /app
RUN pip install cherrypy PyYAML
RUN addgroup -g 1000 tom && adduser -u 1000 -G tom -s /bin/sh -D tom
COPY tom.py lib/ /app/
RUN chown -R tom:tom /app
USER 1000
EXPOSE 443
ENTRYPOINT ["python", "tom.py"]
```

### Agent Container

```dockerfile
FROM python:3.13-alpine
WORKDIR /app
RUN pip install cherrypy PyYAML litellm
RUN addgroup -g 1000 tom && adduser -u 1000 -G tom -s /bin/sh -D tom
COPY agent.py lib/ /app/
RUN chown -R tom:tom /app
USER 1000
EXPOSE 8080
ENTRYPOINT ["python", "agent.py"]
```

### Environment Variables

**Agent Container**:
- `TOM_USERNAME` - Username for the agent instance
- LLM API keys as configured in config.yml

## Usage

### Starting the Services

1. **Prepare configuration**:
   ```bash
   # Create configuration directory
   mkdir -p /data/tls /data/users
   
   # Copy TLS certificates
   cp cert.pem /data/tls/
   cp key.pem /data/tls/
   
   # Create main configuration
   cp config.yml /data/
   ```

2. **Start Tom Server**:
   ```bash
   python tom.py
   ```

3. **Start Agent for user**:
   ```bash
   export TOM_USERNAME=alice
   python agent.py
   ```

### Docker Compose Example

```yaml
version: '3.8'
services:
  tom-server:
    build:
      context: .
      dockerfile: dockerfiles/tom/Dockerfile
    ports:
      - "443:443"
    volumes:
      - /data:/data
    
  tom-agent-alice:
    build:
      context: .
      dockerfile: dockerfiles/agent/Dockerfile
    environment:
      - TOM_USERNAME=alice
    volumes:
      - /data:/data
    depends_on:
      - tom-server
```

## Security Features

- **HTTPS Only**: No HTTP fallback, TLS required
- **Session Management**: File-based session storage
- **User Isolation**: Per-user agent containers
- **API Key Management**: Environment variable isolation
- **Non-root Execution**: All containers run as UID 1000

## Monitoring and Debugging

### Log Analysis

All services use structured logging with the following format:
- Timestamp with millisecond precision
- Consistent log levels
- User context tracking
- Module-specific categorization

### Health Checking

Each service exposes endpoints that can be used for health monitoring:
- Tom Server: GET requests to authenticated routes
- Agent Service: GET `/tasks` endpoint

### Configuration Validation

- YAML syntax validation on startup
- LLM configuration validation with fallbacks
- MCP server configuration checking
- TLS certificate validation

## Development

### Adding New LLM Providers

1. Add configuration to `config.yml`:
   ```yaml
   llms:
     new-provider:
       api: "api-key"
       env_var: NEW_PROVIDER_API_KEY
       models:
         - provider/model-simple
         - provider/model-standard
         - provider/model-complex
   ```

2. Set environment variable in agent container

### Adding New MCP Services

1. Add service configuration to user in `config.yml`:
   ```yaml
   users:
     - username: alice
       password: alice123
       services:
         new-service:
           url: "http://new-service/mcp"
           headers:
             Authorization: "Bearer your-token"
           description: "Description of the new service"
           llm: "openai"
           enable: true
   ```

2. The agent will automatically detect and log the new service on startup

## MCP Services

### Response Consign Resource

MCP services can implement an optional `response_consign` resource to provide LLM instructions for formatting final responses after tool execution. This resource is automatically collected from services that were used during tool calls and combined into system messages to guide the LLM's response formatting.

#### Resource URI
`description://response_consign`

#### Implementation

Add the following resource to your MCP server:

```python
@server.resource("description://response_consign")
def response_consign() -> str:
    """
    Returns response formatting instructions for this MCP service.
    These instructions are provided to the LLM after tool execution 
    to guide response formatting and style.
    """
    response_data = {
        "description": "Response formatting instructions for [service_name]",
        "formatting_guidelines": {
            "response_style": "Define how responses should be formatted",
            "data_presentation": "Specify how to present data from this service",
            "tone": "Define the desired conversational tone"
        },
        "response_structure": {
            "required_elements": "Elements that must be included in responses",
            "optional_elements": "Elements that can be included if relevant"
        },
        "restrictions": {
            "avoid": "Things the LLM should avoid in responses",
            "focus": "What the LLM should focus on"
        }
    }
    
    return json.dumps(response_data, ensure_ascii=False, separators=(',', ':'))
```

#### Example Implementation (Weather Service)

```python
@server.resource("description://response_consign")
def response_consign() -> str:
    """Returns response formatting instructions for weather responses."""
    
    response_data = {
        "description": "Weather response formatting instructions",
        "formatting_guidelines": {
            "response_style": "Keep responses concise and factual",
            "temperature_display": "Always show temperature in Celsius with degree symbol (e.g., 22°C)",
            "weather_conditions": "Use descriptive weather conditions from WMO codes",
            "time_format": "Display dates and times in user-friendly format"
        },
        "response_structure": {
            "current_weather": "Start with current conditions if requested",
            "forecast": "Present forecast in chronological order",
            "no_recommendations": "Do NOT include practical advice like 'Take an umbrella'"
        },
        "strict_instructions": {
            "avoid_advice": "NEVER provide clothing suggestions or activity recommendations",
            "stick_to_facts": "Only provide weather conditions, temperatures, and forecast data",
            "be_concise": "Keep responses short and to the point"
        }
    }
    
    return json.dumps(response_data, ensure_ascii=False, separators=(',', ':'))
```

#### How It Works

1. **Automatic Collection**: When tools are executed, Tom tracks which MCP services were used
2. **Resource Retrieval**: After all tool results are processed, Tom collects `response_consign` resources from used services
3. **System Message**: Combined instructions are added as a system message before the final LLM call
4. **No History Storage**: Response consign messages are never stored in conversation history
5. **Multiple Services**: If multiple services are used, their response consigns are combined automatically

#### Usage Notes

- **Optional**: Services work perfectly without implementing this resource
- **Error Handling**: Missing resources are handled gracefully (no errors if not implemented)
- **JSON Format**: Always return JSON for better LLM performance
- **Service-Specific**: Only collected from services that were actually used in the current tool execution
- **Automatic**: No configuration needed - the system detects and uses available resources

#### Common Use Cases

- **Formatting Requirements**: Specify how data should be presented (units, date formats, etc.)
- **Response Style**: Control verbosity, tone, and conversational style
- **Content Restrictions**: Prevent unwanted advice, recommendations, or off-topic content
- **Data Focus**: Direct attention to specific types of information
- **Brand Guidelines**: Enforce consistent communication style across services

### Memory MCP Server

A Model Context Protocol (MCP) server that provides memory management functionality using [mem0](https://github.com/mem0ai/mem0). This server allows AI agents to store, search, and manage memories for personalized interactions.

#### Features

- **Add Memories**: Store text-based memories with user context
- **Search Memories**: Semantic search through stored memories
- **Delete Memories**: Remove specific memories by ID
- **User Isolation**: Each user has their own memory space
- **Persistent Storage**: Uses Chroma vector database stored in `/data/memory_db`
- **Configurable**: Supports different LLM and embedding providers

#### Configuration

Add memory service configuration to your `/data/config.yml`:

```yaml
# Memory service configuration
memory:
  openai_api_key: "your-openai-api-key"
  llm_provider: "openai"
  llm_model: "gpt-4o-mini"
  embedder_provider: "openai"
  embedder_model: "text-embedding-ada-002"

users:
  - username: alice
    services:
      memory:
        url: "http://memory-service/mcp"
        description: "Personal memory management"
        enable: true
```

#### API Tools

**add_memory**: Stores a new memory for a user
- `text` (str): The memory content to store
- `user_id` (str): Unique identifier for the user
- `metadata` (str, optional): JSON string with additional metadata

**search_memories**: Searches for relevant memories using semantic similarity
- `query` (str): Search query text
- `user_id` (str): User identifier
- `limit` (int): Maximum results to return (default: 10)

**delete_memory**: Removes a specific memory by its ID
- `memory_id` (str): Unique identifier of the memory to delete

**get_all_memories**: Retrieves all memories for a specific user
- `user_id` (str): User identifier

#### Docker Deployment

```dockerfile
FROM python:3.13-alpine
WORKDIR /app
RUN pip install --upgrade pip && \
    pip install requests mcp fastmcp mem0ai PyYAML
RUN addgroup -g 1000 memory && \
    adduser -u 1000 -G memory -s /bin/sh -D memory
COPY mcp/memory_server.py /app/
COPY lib/ /app/lib/
RUN chown -R memory:memory /app
RUN mkdir -p /data && chown -R memory:memory /data
USER 1000
EXPOSE 80
ENTRYPOINT ["python", "memory_server.py"]
```

#### Storage & Environment Variables

- **Database**: `/data/memory_db/` (Chroma vector store with SQLite backend)
- **Configuration**: `/data/config.yml`
- **Environment**: `OPENAI_API_KEY` required for LLM and embedding operations

## Troubleshooting

### Common Issues

1. **TLS Certificate Errors**: Ensure certificates are in `/data/tls/` and readable
2. **Configuration Not Found**: Check `/data/config.yml` exists and is valid YAML
3. **LLM API Errors**: Verify API keys and environment variables
4. **MCP Service Issues**: Check service URLs and authentication in user config
5. **Port Conflicts**: Ensure ports 443 and 8080 are available

### Log Messages

- `✅` - Successful operations
- `⚠️` - Warnings or missing optional components
- `❌` - Errors requiring attention
- `🚀` - Service startup messages
- `🛑` - Service shutdown messages

## License

This project is part of the Tom chatbot system. See individual files for specific licensing information.