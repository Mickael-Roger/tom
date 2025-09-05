FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install caldav icalendar pytz pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 todo && \
    adduser -u 1000 -G todo -s /bin/sh -D todo

# Copy todo MCP server and lib directory
COPY mcp/todo_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R todo:todo /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R todo:todo /data

# Switch to todo user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the todo MCP server
ENTRYPOINT ["python", "todo_server.py"]