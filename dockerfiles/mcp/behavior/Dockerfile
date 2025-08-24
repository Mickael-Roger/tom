FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 behavior && \
    adduser -u 1000 -G behavior -s /bin/sh -D behavior

# Copy behavior MCP server and lib directory
COPY mcp/behavior_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R behavior:behavior /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R behavior:behavior /data

# Switch to behavior user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the behavior MCP server
ENTRYPOINT ["python", "behavior_server.py"]