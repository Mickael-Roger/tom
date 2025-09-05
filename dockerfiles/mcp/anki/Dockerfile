FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 anki && \
    adduser -u 1000 -G anki -s /bin/sh -D anki

# Copy anki MCP server and lib directory
COPY mcp/anki_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R anki:anki /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R anki:anki /data

# Switch to anki user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the anki MCP server
ENTRYPOINT ["python", "anki_server.py"]