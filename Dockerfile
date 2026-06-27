# Use a lightweight official Python image
FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Copy dependencies list first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY pyproject.toml .
COPY README.md .

# Install the package to create the 'mcp-k8s-deployer' binary
RUN pip install --no-cache-dir .

# Create and switch to a secure non-root user
RUN adduser -D mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

# Set entrypoint to run the MCP server executable over stdio
ENTRYPOINT ["mcp-k8s-deployer"]
