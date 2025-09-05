FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests mcp fastmcp pronotepy

# Create user with UID 1000
RUN addgroup -g 1000 pronote && \
    adduser -u 1000 -G pronote -s /bin/sh -D pronote

# Copy anki MCP server and lib directory
COPY mcp/pronote_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R pronote:pronote /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R pronote:pronote /data

# Switch to pronote user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the pronoteanki MCP server
ENTRYPOINT ["python", "pronote_server.py"]
