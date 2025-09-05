FROM python:3.13-slim

WORKDIR /app

# Install system dependencies needed for chromadb
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests mcp fastmcp mem0ai PyYAML chromadb schedule cherrypy litellm

# Create user with UID 1000
RUN groupadd -g 1000 memory && \
    useradd -u 1000 -g memory -s /bin/sh -m memory

# Copy memory MCP server and lib directory
COPY mcp/memory_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R memory:memory /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R memory:memory /data

# Switch to memory user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the memory MCP server
ENTRYPOINT ["python", "memory_server.py"]

