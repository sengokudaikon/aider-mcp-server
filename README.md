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

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/aider-mcp-server.git
   cd aider-mcp-server
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the MCP server:
   ```bash
   python aider_mcp_server.py --host 127.0.0.1 --port 8000 --repo-path /path/to/your/repo
   ```

2. Configure Claude Desktop or any other MCP client to connect to the server at `http://127.0.0.1:8000/mcp`

3. Now you can ask Claude to edit files for you, and it will use Aider's capabilities to do so.

### Example Prompts for Claude

Once the MCP server is running and connected to Claude, you can use prompts like:

- "Edit my app.py file to add error handling to the main function"
- "Create a new file called utils.py with helper functions for date formatting"
- "Show me the current git status of the repository"
- "Extract the Python code from this explanation and save it to a file"

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

3. Pass custom Aider options when editing files:
   ```json
   {
     "files": ["app.py"],
     "instructions": "Add error handling",
     "aider_options": {
       "model": "gpt-4",
       "dark_mode": true,
       "verbose": true
     }
   }
   ```

### Command Line Options

- `--host`: Host to bind the server to (default: 127.0.0.1)
- `--port`: Port to bind the server to (default: 8000)
- `--aider-path`: Path to the Aider executable (default: "aider")
- `--repo-path`: Path to the git repository (default: current directory)
- `--config-file`: Path to a custom Aider config file
- `--env-file`: Path to a custom .env file

## API Reference

The server exposes the following MCP methods:

- `edit_files`: Edit existing files using Aider
- `create_files`: Create new files with content
- `git_status`: Get git status of the repository
- `extract_code`: Extract code blocks from markdown text
- `aider_status`: Check Aider status and environment
- `aider_config`: Get Aider configuration settings from files and environment

## Environment Variables

The server uses the following environment variables:

- `OPENAI_API_KEY`: Your OpenAI API key (if using GPT-4 with Aider)
- `ANTHROPIC_API_KEY`: Your Anthropic API key (if using Claude with Aider)

## License

MIT 