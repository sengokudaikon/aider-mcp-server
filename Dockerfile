FROM python:3.10-slim

# Install git and other dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY README.md LICENSE .env.example ./

# Install uv and the package
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv && \
    uv pip install --no-cache-dir -e .

# Default environment variables
ENV AIDER_PATH=aider
ENV REPO_PATH=/workspace

# Create workspace directory for git repositories
RUN mkdir -p /workspace

WORKDIR /workspace

# Default to stdio mode for MCP protocol
ENTRYPOINT ["aider-mcp"] 