# Aider MCP Server

A Model Context Protocol (MCP) server that allows Claude and other MCP clients to connect to [Aider](https://github.com/paul-gauthier/aider) for efficient file editing capabilities.

## Overview

This MCP server bridges the gap between AI assistants like Claude and Aider's powerful file editing capabilities. It provides a standardized interface through the Model Context Protocol, allowing Claude to:

- Edit existing files using Aider's capabilities
- Create new files with content
- Extract code blocks from markdown text
- Get git status information
- Check Aider installation status
- Access and use Aider's configuration system

## Prerequisites

- Python 3.8 or higher
- Aider installed (`pip install aider-chat`)
- An API key for OpenAI or Anthropic (depending on which model you want Aider to use)
- Git repository for file editing

## Installation

You can install the Aider MCP server in several ways:

### Using UV (Recommended)

If you have [uv](https://github.com/astral-sh/uv) installed:

```bash
# Install uv if you don't have it
curl -fsSL https://astral.sh/uv/install.sh | bash

# Run directly with uvx (no installation required)
uvx aider-mcp
```

### Using PIP

```bash
# Install the package
pip install aider-mcp

# Run the server
aider-mcp
```

## Usage

The Aider MCP server runs in MCP protocol mode over stdio by default, which is designed for direct integration with MCP clients like Claude Desktop and Cursor IDE.

```bash
# Run directly with uvx (recommended)
uvx aider-mcp

# With repository path specified
uvx aider-mcp --repo-path=/path/to/your/repo

# With custom Aider executable path
uvx aider-mcp --aider-path=/path/to/aider

# With environment variables
REPO_PATH=/path/to/your/repo uvx aider-mcp
```

### Command Line Options

You can customize the server with these environment variables or command-line arguments:

- `--aider-path`: Path to the Aider executable (default: "aider", automatically searches PATH)
- `--repo-path`: Path to the git repository (default: current directory)
- `--config-file`: Path to a custom Aider config file
- `--env-file`: Path to a custom .env file
- `--verbose`, `-v`: Enable verbose output

## Client Configuration

### Claude Desktop

Add this to your Claude Desktop configuration file:

```json
{
  "mcpServers": {
    "aider-mcp": {
      "command": "uvx",
      "args": [
        "aider-mcp",
        "--repo-path", "/path/to/your/repo"
      ]
    }
  }
}
```

### Cursor IDE

To integrate with Cursor IDE:

1. Open Cursor Settings
2. Navigate to `Features` > `MCP Servers`
3. Click `Add new MCP server`
4. Enter this configuration:
   ```
   name: aider-mcp
   type: command
   command: uvx aider-mcp --repo-path=/path/to/your/repo
   ```
5. After configuring, ensure you're in Agent mode in the Composer to use MCP tools

## Aider Configuration Support

This MCP server supports Aider's configuration system, allowing you to:

1. Use configuration from `.aider.conf.yml` files in:
   - Your home directory
   - The git repository root
   - The current directory
   - A custom path specified with `--config-file`

2. Use environment variables from `.env` files in:
   - Your home directory
   - The git repository root
   - The current directory
   - A custom path specified with `--env-file`

3. Pass custom Aider options when editing files through the MCP tools.

## Example Prompts for Claude

Once connected to Claude, you can use prompts like:

- "Edit my app.py file to add error handling to the main function"
- "Create a new file called utils.py with helper functions for date formatting"
- "Show me the current git status of the repository"
- "Extract the Python code from this explanation and save it to a file"

## Available Tools

The MCP server provides these directory-based tools:

- `edit_files`: Make targeted code changes in a specified directory 
  - Requires a directory path and detailed instructions
  - Automatically accepts all proposed changes (uses `--yes-always`)
  - Additional Aider options can be specified when needed

- `create_files`: Create new files with content in a specified directory
  - You can provide multiple files to create at once
  - Optionally commit the new files to git

- `git_status`: Get git status of a specified directory's repository
  - Quick way to check for modified, added, deleted, and untracked files

- `extract_code`: Extract code blocks from markdown or text
  - Can optionally save extracted code blocks to files in a specified directory
  - Preserves language information from code block markers

- `aider_status`: Check Aider installation and environment status
  - Verifies Aider is correctly installed and accessible
  - Can check specific directories for configuration
  - Reports on API keys and environment variables

- `aider_config`: Get detailed Aider configuration information
  - Shows which configuration files are being used
  - Displays settings from all layers of configuration
  - Reports available environment variables

## Environment Variables

The server uses environment variables which can be set directly or through `.env` files:

- `AIDER_PATH`: Path to the Aider executable
- `REPO_PATH`: Path to the git repository
- `AIDER_CONFIG_FILE`: Path to a custom Aider config file
- `AIDER_ENV_FILE`: Path to a custom .env file
- `AIDER_MCP_VERBOSE`: Enable verbose logging
- `OPENAI_API_KEY`: Your OpenAI API key (if using GPT-4 with Aider)
- `ANTHROPIC_API_KEY`: Your Anthropic API key (if using Claude with Aider)

## Debugging

You can use the MCP inspector to debug the server:

```bash
# Test with MCP inspector
npx @modelcontextprotocol/inspector uvx aider-mcp

# Test with specific repository path
npx @modelcontextprotocol/inspector uvx aider-mcp --repo-path=/path/to/your/repo

# If running from Python package
npx @modelcontextprotocol/inspector python -m aider_mcp
```

The inspector provides an interactive UI to:
1. View available tools and their schemas
2. Call tools with test parameters
3. See the responses and debug issues

## Development

For local development:

```bash
git clone https://github.com/yourusername/aider-mcp-server.git
cd aider-mcp-server
pip install -e .
```

## License

MIT 