FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install caldav icalendar pytz pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 calendar && \
    adduser -u 1000 -G calendar -s /bin/sh -D calendar

# Copy calendar MCP server and lib directory
COPY mcp/calendar_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R calendar:calendar /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R calendar:calendar /data

# Switch to calendar user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the calendar MCP server
ENTRYPOINT ["python", "calendar_server.py"]