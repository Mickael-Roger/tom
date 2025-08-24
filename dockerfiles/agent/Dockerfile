FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install cherrypy PyYAML litellm mcp httpx pytz

# Create user with UID 1000
RUN addgroup -g 1000 tom && \
    adduser -u 1000 -G tom -s /bin/sh -D tom

# Copy agent application and lib directory
COPY agent.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R tom:tom /app

# Switch to tom user
USER 1000

# Expose port 8080
EXPOSE 8080

# Run the agent application
ENTRYPOINT ["python", "agent.py"]
