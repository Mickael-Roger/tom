FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests beautifulsoup4 pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 kwyk && \
    adduser -u 1000 -G kwyk -s /bin/sh -D kwyk

# Copy kwyk MCP server and lib directory
COPY mcp/kwyk_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R kwyk:kwyk /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R kwyk:kwyk /data

# Switch to kwyk user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the kwyk MCP server
ENTRYPOINT ["python", "kwyk_server.py"]