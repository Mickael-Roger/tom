FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install pynintendoparental aiohttp pytz pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 switchparentalcontrol && \
    adduser -u 1000 -G switchparentalcontrol -s /bin/sh -D switchparentalcontrol

# Copy switchparentalcontrol MCP server and lib directory
COPY mcp/switchparentalcontrol_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R switchparentalcontrol:switchparentalcontrol /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R switchparentalcontrol:switchparentalcontrol /data

# Switch to switchparentalcontrol user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the switchparentalcontrol MCP server
ENTRYPOINT ["python", "switchparentalcontrol_server.py"]