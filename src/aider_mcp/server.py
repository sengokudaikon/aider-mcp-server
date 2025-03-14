"""
Aider MCP Server - Connects Claude to Aider file editing capabilities.

This module provides the core MCP server functionality.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import yaml
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple, Union

from mcp.server import Server
from mcp.types import Resource, TextContent, Tool

logger = logging.getLogger("aider-mcp")


@dataclass
class AppContext:
    """Application context for Aider MCP Server."""
    
    aider_path: str
    repo_path: str
    config_file: Optional[str] = None
    env_file: Optional[str] = None


def find_git_root(path: str) -> Optional[str]:
    """Find the git root directory from the given path."""
    current = os.path.abspath(path)
    while current != os.path.dirname(current):  # Stop at filesystem root
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        current = os.path.dirname(current)
    return None


def load_aider_config(repo_path: Optional[str] = None, config_file: Optional[str] = None) -> Dict[str, Any]:
    """Load Aider configuration from .aider.conf.yml files."""
    config = {}
    search_paths = []
    repo_path = os.path.abspath(repo_path or os.getcwd())
    
    logger.debug(f"Searching for Aider configuration in and around: {repo_path}")
    
    # Working directory config (highest priority for specific settings)
    workdir_config = os.path.join(repo_path, ".aider.conf.yml")
    if os.path.exists(workdir_config):
        logger.debug(f"Found Aider config in working directory: {workdir_config}")
        search_paths.append(workdir_config)
    
    # Git repo root config (if different from working directory)
    git_root = find_git_root(repo_path)
    if git_root and git_root != repo_path:
        git_config = os.path.join(git_root, ".aider.conf.yml")
        if os.path.exists(git_config) and git_config != workdir_config:
            logger.debug(f"Found Aider config in git root: {git_config}")
            search_paths.append(git_config)
    
    # Custom config file (specified by user, highest priority if specified)
    if config_file and os.path.exists(config_file):
        logger.debug(f"Using specified config file: {config_file}")
        if config_file not in search_paths:
            search_paths.append(config_file)
    
    # Home directory config (lowest priority, global defaults)
    home_config = os.path.expanduser("~/.aider.conf.yml")
    if os.path.exists(home_config) and home_config not in search_paths:
        logger.debug(f"Found Aider config in home directory: {home_config}")
        search_paths.append(home_config)
    
    # Load configs in reverse order (lowest priority first, then higher priorities override)
    # This ensures working directory and custom configs take precedence
    for path in reversed(search_paths):
        try:
            with open(path, 'r') as f:
                logger.info(f"Loading Aider config from {path}")
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    logger.debug(f"Config from {path}: {yaml_config}")
                    config.update(yaml_config)
        except Exception as e:
            logger.warning(f"Error loading config from {path}: {e}")
    
    logger.debug(f"Final merged Aider configuration: {config}")
    return config


def load_dotenv_file(repo_path: Optional[str] = None, env_file: Optional[str] = None) -> Dict[str, str]:
    """Load environment variables from .env files."""
    env_vars = {}
    search_paths = []
    repo_path = os.path.abspath(repo_path or os.getcwd())
    
    logger.debug(f"Searching for .env files in and around: {repo_path}")
    
    # Working directory .env (highest priority for specific settings)
    workdir_env = os.path.join(repo_path, ".env")
    if os.path.exists(workdir_env):
        logger.debug(f"Found .env in working directory: {workdir_env}")
        search_paths.append(workdir_env)
    
    # Git repo root .env (if different from working directory)
    git_root = find_git_root(repo_path)
    if git_root and git_root != repo_path:
        git_env = os.path.join(git_root, ".env")
        if os.path.exists(git_env) and git_env != workdir_env:
            logger.debug(f"Found .env in git root: {git_env}")
            search_paths.append(git_env)
    
    # Custom env file (specified by user, highest priority if specified)
    if env_file and os.path.exists(env_file):
        logger.debug(f"Using specified .env file: {env_file}")
        if env_file not in search_paths:
            search_paths.append(env_file)
    
    # Home directory .env (lowest priority, global defaults)
    home_env = os.path.expanduser("~/.env")
    if os.path.exists(home_env) and home_env not in search_paths:
        logger.debug(f"Found .env in home directory: {home_env}")
        search_paths.append(home_env)
    
    # Load env files in reverse order (lowest priority first, then higher priorities override)
    # This ensures working directory and custom env files take precedence
    for path in reversed(search_paths):
        try:
            with open(path, 'r') as f:
                logger.info(f"Loading .env from {path}")
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    try:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
                    except ValueError:
                        logger.warning(f"Invalid line in .env file {path}: {line}")
        except Exception as e:
            logger.warning(f"Error loading .env from {path}: {e}")
    
    logger.debug(f"Loaded environment variables: {list(env_vars.keys())}")
    return env_vars


async def run_command(command: List[str], input_data: Optional[str] = None) -> Tuple[str, str]:
    """Run a command and return stdout and stderr."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if input_data else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    if input_data:
        stdout, stderr = await process.communicate(input_data.encode())
    else:
        stdout, stderr = await process.communicate()
    
    return stdout.decode(), stderr.decode()


def prepare_aider_command(
    base_command: List[str], 
    files: List[str] = None, 
    options: Dict[str, Any] = None
) -> List[str]:
    """Prepare an Aider command with files and options."""
    command = base_command.copy()
    
    if options:
        # Convert options to command line arguments
        for key, value in options.items():
            arg_key = key.replace('_', '-')
            
            # Handle boolean flags
            if isinstance(value, bool):
                if value:
                    command.append(f"--{arg_key}")
                else:
                    command.append(f"--no-{arg_key}")
            
            # Handle lists
            elif isinstance(value, list):
                for item in value:
                    command.append(f"--{arg_key}")
                    command.append(str(item))
            
            # Handle simple values
            elif value is not None:
                command.append(f"--{arg_key}")
                command.append(str(value))
    
    # Add files last
    if files:
        command.extend(files)
    
    # Remove empty strings
    command = [c for c in command if c]
    
    return command


@asynccontextmanager
async def server_lifespan(server: Server, init_options=None) -> AsyncIterator[AppContext]:
    """Initialize and clean up application resources."""
    try:
        # Try to get context from server if available
        ctx = server.request_context.initialization_options
    except (LookupError, AttributeError):
        # Fall back to the provided init_options if request_context is unavailable
        ctx = init_options or {}
    
    # Extract parameters from initialization options
    aider_path = ctx.get("aider_path", "aider")
    repo_path = ctx.get("repo_path", os.getcwd())
    config_file = ctx.get("config_file")
    env_file = ctx.get("env_file")
    
    logger.info(f"Initializing Aider MCP Server")
    logger.info(f"Aider executable: {aider_path}")
    logger.info(f"Repository path: {repo_path}")
    
    # Validate repository path
    if not os.path.exists(repo_path):
        logger.error(f"Repository path does not exist: {repo_path}")
        repo_path = os.getcwd()
        logger.info(f"Falling back to current directory: {repo_path}")
        
    # Try to validate aider executable
    aider_version = None
    try:
        logger.debug(f"Checking Aider version using: {aider_path}")
        result, error = await run_command([aider_path, "--version"])
        if result:
            aider_version = result.strip()
            logger.info(f"Detected Aider version: {aider_version}")
        else:
            logger.warning(f"Could not determine Aider version: {error}")
    except Exception as e:
        logger.warning(f"Error checking Aider version: {e}")
    
    # Load configuration with specified hierarchy
    aider_config = load_aider_config(repo_path, config_file)
    env_vars = load_dotenv_file(repo_path, env_file)
    
    # Set environment variables from loaded .env files
    for key, value in env_vars.items():
        if key not in os.environ:  # Don't override existing env vars
            logger.debug(f"Setting environment variable: {key}")
            os.environ[key] = value
    
    # Remember the original directory
    original_dir = os.getcwd()
    
    # Change to the repository directory
    try:
        logger.info(f"Changing to repository directory: {repo_path}")
        os.chdir(repo_path)
        
        # Provide context to the application
        yield AppContext(
            aider_path=aider_path,
            repo_path=repo_path,
            config_file=config_file,
            env_file=env_file
        )
    finally:
        # Return to original directory
        logger.debug(f"Returning to original directory: {original_dir}")
        os.chdir(original_dir)


# Create server instance
app = Server("aider-mcp", lifespan=server_lifespan)


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    # For now, we're just returning a simple resource representing the Git repository
    ctx = app.request_context.lifespan_context
    
    if not ctx:
        return []
    
    # Get repository information
    repo_path = ctx.repo_path
    git_root = find_git_root(repo_path)
    
    resources = []
    
    if git_root:
        try:
            # Try to get the remote URL for a better name
            command = ["git", "config", "--get", "remote.origin.url"]
            stdout, _ = await run_command(command)
            remote_url = stdout.strip()
            
            # Extract repository name from remote URL
            if remote_url:
                repo_name = remote_url.split("/")[-1].replace(".git", "")
            else:
                # Fallback to the directory name
                repo_name = os.path.basename(git_root)
                
            resources.append(
                Resource(
                    uri=f"git://{repo_name}",
                    name=f"Git Repository: {repo_name}",
                    mimeType="text/plain",
                    description="The Git repository for Aider to edit."
                )
            )
        except Exception as e:
            logger.error(f"Error getting repository info: {str(e)}")
    
    return resources


@app.read_resource()
async def read_resource(uri: str) -> tuple[str, str]:
    """Read a resource."""
    ctx = app.request_context.lifespan_context
    
    if not ctx:
        raise ValueError("Application context not initialized.")
    
    if uri.startswith("git://"):
        # Get git status
        try:
            command = ["git", "status", "--porcelain"]
            stdout, stderr = await run_command(command)
            
            if stderr:
                return f"Error: {stderr}", "text/plain"
            
            # If there are no changes, get a summary of the repo
            if not stdout.strip():
                # Get repository info
                commits_cmd = ["git", "log", "--oneline", "-n", "5"]
                commits, _ = await run_command(commits_cmd)
                
                branches_cmd = ["git", "branch", "--list"]
                branches, _ = await run_command(branches_cmd)
                
                return (
                    f"# Git Repository Status\n\n"
                    f"**Working directory is clean**\n\n"
                    f"## Recent Commits\n```\n{commits}```\n\n"
                    f"## Branches\n```\n{branches}```\n",
                    "text/markdown"
                )
            
            # Parse the status output
            modified = []
            added = []
            deleted = []
            untracked = []
            
            for line in stdout.split("\n"):
                if not line.strip():
                    continue
                    
                status = line[:2]
                filename = line[3:]
                
                if status == " M" or status == "M ":
                    modified.append(filename)
                elif status == "A " or status == " A":
                    added.append(filename)
                elif status == "D " or status == " D":
                    deleted.append(filename)
                elif status == "??":
                    untracked.append(filename)
            
            # Format the status as markdown
            content = "# Git Repository Status\n\n"
            
            if modified:
                content += "## Modified Files\n"
                for file in modified:
                    content += f"- {file}\n"
                content += "\n"
                
            if added:
                content += "## Added Files\n"
                for file in added:
                    content += f"- {file}\n"
                content += "\n"
                
            if deleted:
                content += "## Deleted Files\n"
                for file in deleted:
                    content += f"- {file}\n"
                content += "\n"
                
            if untracked:
                content += "## Untracked Files\n"
                for file in untracked:
                    content += f"- {file}\n"
                content += "\n"
                
            return content, "text/markdown"
            
        except Exception as e:
            logger.error(f"Error reading git status: {str(e)}")
            return f"Error: {str(e)}", "text/plain"
    
    return f"Resource not found: {uri}", "text/plain"


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="edit_files",
            description="AI pair programming tool for making targeted code changes. Use this tool to:\n\n"
                        "1. Implement new features or functionality in existing code\n"
                        "2. Add tests to an existing codebase\n"
                        "3. Fix bugs in code\n"
                        "4. Refactor or improve existing code\n"
                        "5. Make structural changes across multiple files\n\n"
                        "The tool requires:\n"
                        "- A directory path where the code exists\n"
                        "- A detailed message describing what changes to make. Please only describe one change per message. "
                        "If you need to make multiple changes, please submit multiple requests.\n\n"
                        "Best practices for messages:\n"
                        "- Be specific about what files or components to modify\n"
                        "- Describe the desired behavior or functionality clearly\n"
                        "- Provide context about the existing codebase structure\n"
                        "- Include any constraints or requirements to follow\n\n"
                        "Examples of good messages:\n"
                        "- \"Add unit tests for the Customer class in src/models/customer.rb testing the validation logic\"\n"
                        "- \"Implement pagination for the user listing API in the controllers/users_controller.js file\"\n"
                        "- \"Fix the bug in utils/date_formatter.py where dates before 1970 aren't handled correctly\"\n"
                        "- \"Refactor the authentication middleware in middleware/auth.js to use async/await instead of callbacks\"",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The directory path where aider should run (must exist and contain code files)"
                    },
                    "message": {
                        "type": "string",
                        "description": "Detailed instructions for what changes aider should make to the code"
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Additional command-line options to pass to aider (optional)"
                    }
                },
                "required": ["directory", "message"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="create_files",
            description="Create new files in a git repository. Use this when you need to:\n\n"
                        "1. Add new source code files to a project\n"
                        "2. Create configuration files\n"
                        "3. Add documentation files\n"
                        "4. Generate scaffold files for a new feature\n\n"
                        "Provide a map of filenames to content, and specify if the files should be committed to git.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The directory path where files should be created"
                    },
                    "files": {
                        "type": "object",
                        "description": "Dictionary of filename to content",
                        "additionalProperties": {"type": "string"}
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message for the new files",
                        "default": "Create new files via Aider MCP"
                    },
                    "git_commit": {
                        "type": "boolean",
                        "description": "Whether to automatically commit the files to git",
                        "default": True
                    }
                },
                "required": ["directory", "files"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="git_status",
            description="Get the current git status of a repository. Shows modified, untracked, and staged files.\n\n"
                        "Use this to understand the current state of the repository before making changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The directory path of the git repository to check"
                    }
                },
                "required": ["directory"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="extract_code",
            description="Extract code blocks from markdown or text. Use this to:\n\n"
                        "1. Extract code samples from documentation\n"
                        "2. Save code snippets from messages or comments\n"
                        "3. Prepare code from explanations for execution\n\n"
                        "The tool will identify all code blocks (surrounded by triple backticks) in the provided text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text containing code blocks to extract"
                    },
                    "save_to_directory": {
                        "type": "string",
                        "description": "Optional directory to save extracted code blocks as files. If not provided, code blocks will just be returned."
                    }
                },
                "required": ["text"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="aider_status",
            description="Check the status of Aider and its environment. Use this to:\n\n"
                        "1. Verify Aider is correctly installed\n"
                        "2. Check API keys for OpenAI/Anthropic are set up\n"
                        "3. View the current configuration\n"
                        "4. Diagnose connection or setup issues",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to check configuration for (will look for .aider.conf.yml in this location)"
                    },
                    "check_environment": {
                        "type": "boolean",
                        "description": "Whether to check environment variables and API keys",
                        "default": True
                    }
                },
                "additionalProperties": False
            }
        ),
        Tool(
            name="aider_config",
            description="Get detailed Aider configuration information. Use this to:\n\n"
                        "1. See all Aider configuration settings currently applied\n"
                        "2. Find which configuration files are being used\n"
                        "3. Check which environment variables are available\n"
                        "4. View the configuration hierarchy and precedence",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to get configuration for (will look for .aider.conf.yml in this location)"
                    }
                },
                "additionalProperties": False
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Aider operations."""
    ctx = app.request_context.lifespan_context
    
    if not ctx:
        return [TextContent(type="text", text="Error: Application context not initialized.")]
    
    try:
        # Tool: edit_files
        if name == "edit_files":
            directory = arguments.get("directory", "")
            message = arguments.get("message", "")
            options_list = arguments.get("options", [])
            
            logger.info(f"Running aider in directory: {directory}")
            logger.debug(f"Message length: {len(message)} characters")
            logger.debug(f"Additional options: {options_list}")
            
            # Verify directory exists
            directory_path = os.path.abspath(directory)
            if not os.path.exists(directory_path):
                logger.error(f"Directory does not exist: {directory_path}")
                return [TextContent(
                    type="text",
                    text=f"Error: Directory does not exist: {directory_path}"
                )]
            
            # Load the configuration for this directory
            aider_config = load_aider_config(directory_path, ctx.config_file)
            
            # Build command line options
            aider_options = {}
            # Always add --yes-always to automatically accept changes
            aider_options["yes_always"] = True
            
            # Add any additional options from the options list
            additional_opts = {}
            for opt in options_list:
                if opt.startswith("--"):
                    # Handle --option=value format
                    if "=" in opt:
                        key, value = opt[2:].split("=", 1)
                        additional_opts[key.replace("-", "_")] = value
                    # Handle --option format (boolean flags)
                    else:
                        additional_opts[opt[2:].replace("-", "_")] = True
                elif opt.startswith("--no-"):
                    # Handle --no-option format (negative boolean flags)
                    key = opt[5:].replace("-", "_")
                    additional_opts[key] = False
            
            # Add the options from the command line
            aider_options.update(additional_opts)
            
            # Write the instructions to a temporary file
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
                f.write(message)
                instructions_file = f.name
                logger.debug(f"Instructions written to temporary file: {instructions_file}")
            
            try:
                # Save current directory
                original_dir = os.getcwd()
                
                # Change to the target directory
                os.chdir(directory_path)
                logger.debug(f"Changed working directory to: {directory_path}")
                
                # Build the command
                base_command = [ctx.aider_path]
                command = prepare_aider_command(
                    base_command,
                    [],  # No specific files, Aider will handle this 
                    aider_options
                )
                
                logger.info(f"Running aider command: {' '.join(command)}")
                
                # Execute Aider with the instructions
                with open(instructions_file, 'r') as f:
                    instructions_content = f.read()
                    
                logger.debug("Executing Aider with the instructions...")
                stdout, stderr = await run_command(command, instructions_content)
                
                # Change back to original directory
                os.chdir(original_dir)
                
                if stderr and ("error" in stderr.lower() or "exception" in stderr.lower()):
                    logger.error(f"Aider reported an error: {stderr}")
                    return [TextContent(
                        type="text",
                        text=f"Error making code changes:\n{stderr}\n\nOutput:\n{stdout}"
                    )]
                
                logger.info("Code changes completed successfully")
                return [TextContent(
                    type="text",
                    text=f"Code changes completed successfully:\n\n{stdout}"
                )]
            finally:
                logger.debug(f"Cleaning up temporary file: {instructions_file}")
                os.unlink(instructions_file)
                
                # Ensure we're back in the original directory
                if os.getcwd() != original_dir:
                    os.chdir(original_dir)
                    logger.debug(f"Restored working directory to: {original_dir}")
                
        # Tool: create_files
        elif name == "create_files":
            directory = arguments.get("directory", "")
            files = arguments.get("files", {})
            message = arguments.get("message", "Create files via Aider MCP")
            git_commit = arguments.get("git_commit", True)
            
            # Verify directory exists
            directory_path = os.path.abspath(directory)
            if not os.path.exists(directory_path):
                logger.error(f"Directory does not exist: {directory_path}")
                return [TextContent(
                    type="text",
                    text=f"Error: Directory does not exist: {directory_path}"
                )]
            
            logger.info(f"Creating {len(files)} files in {directory_path}")
            logger.debug(f"Files to create: {list(files.keys())}")
            logger.debug(f"Git commit: {git_commit}")
            logger.debug(f"Commit message: {message}")
            
            # Save current directory
            original_dir = os.getcwd()
            
            try:
                # Change to target directory
                os.chdir(directory_path)
                logger.debug(f"Changed working directory to: {directory_path}")
                
                created_files = []
                skipped_files = []
                
                for filename, content in files.items():
                    file_path = os.path.abspath(filename)
                    
                    # Check if file would be outside the target directory
                    if not file_path.startswith(directory_path):
                        logger.warning(f"Skipping file outside target directory: {filename}")
                        skipped_files.append(filename)
                        continue
                    
                    # Check if file already exists
                    if os.path.exists(file_path):
                        logger.warning(f"File already exists: {filename}")
                        # We'll still update it, but log the warning
                    
                    # Ensure directory exists
                    try:
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        logger.debug(f"Ensured directory exists for: {filename}")
                        
                        with open(file_path, 'w') as f:
                            f.write(content)
                        logger.info(f"Created/updated file: {filename}")
                        created_files.append(filename)
                    except Exception as e:
                        logger.error(f"Error creating file {filename}: {str(e)}")
                        skipped_files.append(filename)
                
                result_lines = [f"Created {len(created_files)} files:"]
                result_lines.extend(f"- {file}" for file in created_files)
                
                if skipped_files:
                    result_lines.append(f"\nSkipped {len(skipped_files)} files:")
                    result_lines.extend(f"- {file}" for file in skipped_files)
                
                result = "\n".join(result_lines)
                
                if git_commit and created_files:
                    try:
                        # Check if git is available and repo is valid
                        git_check_cmd = ["git", "rev-parse", "--is-inside-work-tree"]
                        git_check_stdout, git_check_stderr = await run_command(git_check_cmd)
                        
                        if git_check_stderr or git_check_stdout.strip() != "true":
                            logger.warning(f"Not a valid git repository: {git_check_stderr}")
                            return [TextContent(
                                type="text",
                                text=f"{result}\n\nFiles were created but not committed: Not a valid git repository."
                            )]
                        
                        # Add files to git
                        add_command = ["git", "add"] + created_files
                        logger.debug(f"Running git add command: {add_command}")
                        add_stdout, add_stderr = await run_command(add_command)
                        
                        if add_stderr:
                            logger.error(f"Error adding files to git: {add_stderr}")
                            return [TextContent(
                                type="text",
                                text=f"{result}\n\nError adding files to git:\n{add_stderr}"
                            )]
                        
                        # Commit files
                        commit_command = ["git", "commit", "-m", message]
                        logger.debug(f"Running git commit command: {commit_command}")
                        commit_stdout, commit_stderr = await run_command(commit_command)
                        
                        if "nothing to commit" in commit_stderr.lower():
                            logger.info("No changes to commit")
                            result += "\n\nNo changes to commit."
                        elif commit_stderr and "error" in commit_stderr.lower():
                            result += f"\n\nError committing files:\n{commit_stderr}"
                        else:
                            result += f"\n\nCommitted files:\n{commit_stdout}"
                            
                    except Exception as e:
                        result += f"\n\nError in git operations: {str(e)}"
                
                return [TextContent(type="text", text=result)]
                
            finally:
                # Change back to original directory
                os.chdir(original_dir)
                logger.debug(f"Restored working directory to: {original_dir}")
            
        # Tool: git_status
        elif name == "git_status":
            directory = arguments.get("directory", "")
            
            if not directory:
                return [TextContent(
                    type="text",
                    text="Error: Directory not specified"
                )]
            
            # Verify directory exists
            directory_path = os.path.abspath(directory)
            if not os.path.exists(directory_path):
                logger.error(f"Directory does not exist: {directory_path}")
                return [TextContent(
                    type="text",
                    text=f"Error: Directory does not exist: {directory_path}"
                )]
            
            # Save current directory
            original_dir = os.getcwd()
            
            try:
                # Change to target directory
                os.chdir(directory_path)
                logger.debug(f"Changed working directory to: {directory_path}")
                
                # Check if this is a git repository
                git_check_cmd = ["git", "rev-parse", "--is-inside-work-tree"]
                git_check_stdout, git_check_stderr = await run_command(git_check_cmd)
                
                if git_check_stderr or git_check_stdout.strip() != "true":
                    logger.warning(f"Not a valid git repository: {git_check_stderr}")
                    return [TextContent(
                        type="text",
                        text=f"Error: Not a valid git repository in {directory_path}"
                    )]
                
                # Get git status
                command = ["git", "status"]
                stdout, stderr = await run_command(command)
                
                if stderr:
                    logger.error(f"Error getting git status: {stderr}")
                    return [TextContent(
                        type="text",
                        text=f"Error getting git status:\n{stderr}"
                    )]
                    
                return [TextContent(
                    type="text",
                    text=f"Git status for {directory_path}:\n\n{stdout}"
                )]
            
            finally:
                # Change back to original directory
                os.chdir(original_dir)
                logger.debug(f"Restored working directory to: {original_dir}")
            
        # Tool: extract_code
        elif name == "extract_code":
            text = arguments.get("text", "")
            save_to_directory = arguments.get("save_to_directory", "")
            
            # Extract code blocks (```language ... ```)
            code_blocks = re.findall(r'```(?:(\w+))?\s*([\s\S]*?)```', text)
            
            if not code_blocks:
                return [TextContent(
                    type="text",
                    text="No code blocks found in the text."
                )]
            
            result_text = f"Extracted {len(code_blocks)} code blocks:\n\n"
            saved_files = []
            
            # If saving to directory
            if save_to_directory:
                directory_path = os.path.abspath(save_to_directory)
                
                # Ensure directory exists
                if not os.path.exists(directory_path):
                    try:
                        os.makedirs(directory_path, exist_ok=True)
                        logger.info(f"Created directory: {directory_path}")
                    except Exception as e:
                        logger.error(f"Error creating directory {directory_path}: {str(e)}")
                        return [TextContent(
                            type="text",
                            text=f"Error creating directory {directory_path}: {str(e)}"
                        )]
                
                # Save each code block to a file
                for i, (language, block) in enumerate(code_blocks):
                    lang = language.strip() if language else "txt"
                    filename = f"code_block_{i+1}.{lang}"
                    file_path = os.path.join(directory_path, filename)
                    
                    try:
                        with open(file_path, 'w') as f:
                            f.write(block)
                        saved_files.append(filename)
                        logger.info(f"Saved code block to: {file_path}")
                    except Exception as e:
                        logger.error(f"Error saving code block to {file_path}: {str(e)}")
                
                # Format the result
                result_text += "\n".join([f"Block {i+1} ({lang}): Saved to {filename}" 
                                        for i, ((lang, _), filename) in enumerate(zip(code_blocks, saved_files))])
                result_text += f"\n\nSaved {len(saved_files)} files to {directory_path}"
            else:
                # Just return the extracted code blocks
                for i, (language, block) in enumerate(code_blocks):
                    lang = language.strip() if language else "unknown"
                    result_text += f"Block {i+1} ({lang}):\n```{lang}\n{block}\n```\n\n"
            
            return [TextContent(
                type="text",
                text=result_text
            )]
            
        # Tool: aider_status
        elif name == "aider_status":
            directory = arguments.get("directory", ctx.repo_path)
            check_environment = arguments.get("check_environment", True)
            
            logger.info("Checking Aider status")
            
            # Basic information
            result = {}
            
            # Check if aider is installed and get its version
            try:
                command = [ctx.aider_path, "--version"]
                stdout, stderr = await run_command(command)
                
                version_info = stdout.strip() if stdout else "Unknown version"
                logger.info(f"Detected Aider version: {version_info}")
                
                result["aider"] = {
                    "installed": bool(stdout and not stderr),
                    "version": version_info,
                    "executable_path": ctx.aider_path,
                }
                
                # Repository information
                directory_path = os.path.abspath(directory) if directory else ctx.repo_path
                result["directory"] = {
                    "path": directory_path,
                    "exists": os.path.exists(directory_path),
                }
                
                # Git information
                git_root = find_git_root(directory_path)
                result["git"] = {
                    "is_git_repo": bool(git_root),
                    "git_root": git_root,
                }
                
                if git_root:
                    # Try to get repo information
                    try:
                        # Save current directory
                        original_dir = os.getcwd()
                        
                        # Change to target directory to run git commands
                        os.chdir(directory_path)
                        
                        name_cmd = ["git", "config", "--get", "remote.origin.url"]
                        name_stdout, _ = await run_command(name_cmd)
                        result["git"]["remote_url"] = name_stdout.strip() if name_stdout else None
                        
                        branch_cmd = ["git", "branch", "--show-current"]
                        branch_stdout, _ = await run_command(branch_cmd)
                        result["git"]["current_branch"] = branch_stdout.strip() if branch_stdout else None
                        
                        # Change back to original directory
                        os.chdir(original_dir)
                    except Exception as e:
                        logger.warning(f"Error getting git details: {e}")
                
                if check_environment:
                    # Check API keys
                    env_vars = {}
                    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AIDER_MODEL"]:
                        env_vars[key] = key in os.environ
                    
                    result["environment"] = env_vars
                    
                    # Add configuration information
                    config = load_aider_config(directory_path, ctx.config_file)
                    if config:
                        result["config"] = config
                    
                    # Add config file paths
                    result["config_files"] = {
                        "searched": [
                            os.path.expanduser("~/.aider.conf.yml"),
                            os.path.join(git_root, ".aider.conf.yml") if git_root else None,
                            os.path.join(directory_path, ".aider.conf.yml"),
                            ctx.config_file
                        ],
                        "used": ctx.config_file or os.path.join(directory_path, ".aider.conf.yml") 
                        if os.path.exists(os.path.join(directory_path, ".aider.conf.yml")) else None
                    }
                
                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str)
                )]
                
            except Exception as e:
                logger.error(f"Error checking Aider status: {e}")
                return [TextContent(
                    type="text",
                    text=f"Error checking Aider status: {str(e)}"
                )]
                
        # Tool: aider_config
        elif name == "aider_config":
            directory = arguments.get("directory", ctx.repo_path)
            directory_path = os.path.abspath(directory) if directory else ctx.repo_path
            
            logger.info(f"Getting Aider configuration for directory: {directory_path}")
            
            # Load configuration with specified hierarchy
            config = load_aider_config(directory_path, ctx.config_file)
            env_vars = load_dotenv_file(directory_path, ctx.env_file)
            
            # Only show if environment variables exist, not their values for security
            env_vars_keys = list(env_vars.keys())
            
            # Get the git root for this directory
            git_root = find_git_root(directory_path)
            
            # Find which config files exist
            home_config = os.path.expanduser("~/.aider.conf.yml")
            git_root_config = os.path.join(git_root, ".aider.conf.yml") if git_root else None
            dir_config = os.path.join(directory_path, ".aider.conf.yml")
            
            config_files = {
                "home_config": {
                    "path": home_config,
                    "exists": os.path.exists(home_config)
                },
                "git_root_config": {
                    "path": git_root_config,
                    "exists": os.path.exists(git_root_config) if git_root_config else False
                },
                "directory_config": {
                    "path": dir_config,
                    "exists": os.path.exists(dir_config)
                },
                "custom_config": {
                    "path": ctx.config_file,
                    "exists": os.path.exists(ctx.config_file) if ctx.config_file else False
                }
            }
            
            # Build a more informative result
            result = {
                "directory": directory_path,
                "aider_config": config,
                "environment_variables": {
                    "found": env_vars_keys,
                    "relevant": {
                        "OPENAI_API_KEY": "OPENAI_API_KEY" in os.environ,
                        "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY" in os.environ,
                        "AIDER_MODEL": "AIDER_MODEL" in os.environ
                    }
                },
                "config_files": config_files,
                "git_repository": {
                    "is_git_repo": bool(git_root),
                    "git_root": git_root
                }
            }
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
            
        # Unknown tool
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]
        
    except Exception as e:
        logger.error(f"Error executing tool {name}: {str(e)}")
        return [TextContent(
            type="text",
            text=f"Error executing tool {name}: {str(e)}"
        )]


def create_server() -> Server:
    """Create and return the MCP server."""
    # Set the lifespan handler
    app.lifespan = lambda server: server_lifespan(server)
    return app 