FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 homeconnect && \
    adduser -u 1000 -G homeconnect -s /bin/sh -D homeconnect

# Copy homeconnect MCP server and lib directory
COPY mcp/homeconnect_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R homeconnect:homeconnect /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R homeconnect:homeconnect /data

# Switch to homeconnect user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the homeconnect MCP server
ENTRYPOINT ["python", "homeconnect_server.py"]