FROM python:3.13-slim

ARG TZ
ENV TZ="$TZ"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  curl \
  wget \
  git \
  iproute2 \
  procps \
  sudo \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  ripgrep \
  dnsutils \
  aggregate \
  jq \
  nodejs \
  npm \
  nano \
  vim \
  && apt-get clean && rm -rf /var/lib/apt/lists/*


# Create non-root user with UID 1000 and GID 1000
RUN groupadd --gid 1000 code && \
    useradd --create-home --home-dir /data --shell /bin/bash --uid 1000 --gid 1000 code

# Create necessary directories
RUN mkdir -p /app /data/projects && \
    chown -R code:code /app /data

RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R code:code /commandhistory

ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"


RUN npm install -g @anthropic-ai/claude-code@latest


# Copy MCP server
COPY mcp/claude_code_server.py /app/
COPY lib/ /app/lib/

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir fastmcp mcp requests claude-code-sdk cherrypy

RUN echo "code ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/code && \
    chmod 0440 /etc/sudoers.d/code

# Set up non-root user
USER code

# Expose ports
EXPOSE 80 8080

# Set environment variables
ENV PYTHONPATH=/app
ENV TOM_LOG_LEVEL=INFO

# Run the MCP server
CMD ["python", "claude_code_server.py"]

