#!/usr/bin/env python3
"""
Aider MCP Server - Connects Claude to Aider file editing capabilities

This Model Context Protocol (MCP) server allows Claude to use Aider's file editing 
capabilities through the standardized MCP protocol, enabling more efficient code 
manipulation and generation.
"""

import json
import os
import subprocess
import tempfile
import logging
import sys
import argparse
import asyncio
import yaml
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("aider-mcp")

# FastAPI app
app = FastAPI(title="Aider MCP Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MCP Protocol Models
class MCPServerInfo(BaseModel):
    title: str = "Aider MCP Server"
    description: str = "Allows Claude to connect to Aider for efficient file editing"
    version: str = "1.0.0"
    vendor: Optional[str] = "Claude Integration"

class MCPMethod(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

class MCPSchema(BaseModel):
    server_info: MCPServerInfo
    methods: List[MCPMethod]

# Aider Command Models
class EditFilesRequest(BaseModel):
    files: List[str] = Field(..., description="List of files to edit")
    instructions: str = Field(..., description="Instructions for editing the files")
    git_commit: bool = Field(True, description="Whether to automatically commit changes")
    aider_options: Optional[Dict[str, Any]] = Field(None, description="Additional Aider options")

class CreateFilesRequest(BaseModel):
    files: Dict[str, str] = Field(..., description="Dictionary of filename to content")
    message: str = Field(..., description="Commit message for the new files")
    git_commit: bool = Field(True, description="Whether to automatically commit changes")
    aider_options: Optional[Dict[str, Any]] = Field(None, description="Additional Aider options")

class GitStatusRequest(BaseModel):
    repo_path: Optional[str] = Field(None, description="Path to git repository (default: current directory)")

class ExtractCodeRequest(BaseModel):
    text: str = Field(..., description="Text containing code to extract")

class AiderStatusRequest(BaseModel):
    check_environment: bool = Field(True, description="Check if the environment is properly set up")

class AiderConfigRequest(BaseModel):
    repo_path: Optional[str] = Field(None, description="Path to repository to look for config files")
    config_file: Optional[str] = Field(None, description="Custom config file path")
    env_file: Optional[str] = Field(None, description="Custom .env file path")

# Global variables
AIDER_PATH = "aider"  # Default path to aider executable
REPO_PATH = os.getcwd()  # Default to current directory

# Aider configuration handling
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
    
    # Home directory config
    home_config = os.path.expanduser("~/.aider.conf.yml")
    if os.path.exists(home_config):
        search_paths.append(home_config)
    
    # Git repo root config
    git_root = find_git_root(repo_path or REPO_PATH)
    if git_root:
        git_config = os.path.join(git_root, ".aider.conf.yml")
        if os.path.exists(git_config):
            search_paths.append(git_config)
    
    # Current directory config
    current_dir_config = os.path.join(repo_path or REPO_PATH, ".aider.conf.yml")
    if os.path.exists(current_dir_config) and current_dir_config not in search_paths:
        search_paths.append(current_dir_config)
    
    # Custom config file
    if config_file and os.path.exists(config_file):
        search_paths.append(config_file)
    
    # Load configs in order
    for path in search_paths:
        try:
            with open(path, 'r') as f:
                logger.info(f"Loading Aider config from {path}")
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config.update(yaml_config)
        except Exception as e:
            logger.warning(f"Error loading config from {path}: {e}")
    
    return config

def load_dotenv_file(env_file: Optional[str] = None) -> Dict[str, str]:
    """Load environment variables from .env files."""
    env_vars = {}
    search_paths = []
    
    # Home directory .env
    home_env = os.path.expanduser("~/.env")
    if os.path.exists(home_env):
        search_paths.append(home_env)
    
    # Git repo root .env
    git_root = find_git_root(REPO_PATH)
    if git_root:
        git_env = os.path.join(git_root, ".env")
        if os.path.exists(git_env):
            search_paths.append(git_env)
    
    # Current directory .env
    current_dir_env = os.path.join(REPO_PATH, ".env")
    if os.path.exists(current_dir_env) and current_dir_env not in search_paths:
        search_paths.append(current_dir_env)
    
    # Custom env file
    if env_file and os.path.exists(env_file):
        search_paths.append(env_file)
    
    # Load env files in order
    for path in search_paths:
        try:
            with open(path, 'r') as f:
                logger.info(f"Loading .env from {path}")
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
        except Exception as e:
            logger.warning(f"Error loading .env from {path}: {e}")
    
    return env_vars

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

# Aider command execution functions
async def run_aider_command(command: List[str], input_data: Optional[str] = None) -> Tuple[str, str]:
    """Run an aider command and return stdout and stderr."""
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

async def edit_files(request: EditFilesRequest) -> Dict[str, Any]:
    """Use aider to edit files based on instructions."""
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
        f.write(request.instructions)
        instructions_file = f.name
    
    try:
        base_command = [AIDER_PATH]
        if not request.git_commit:
            base_command.append("--no-auto-commit")
        
        command = prepare_aider_command(
            base_command, 
            request.files, 
            request.aider_options
        )
        
        logger.info(f"Running aider command: {' '.join(command)}")
        
        with open(instructions_file, 'r') as f:
            instructions = f.read()
            
        stdout, stderr = await run_aider_command(command, instructions)
        
        if stderr and "error" in stderr.lower():
            return {
                "success": False,
                "error": stderr,
                "output": stdout
            }
        
        return {
            "success": True,
            "message": "Files edited successfully",
            "output": stdout,
            "files": request.files
        }
    finally:
        os.unlink(instructions_file)

async def create_files(request: CreateFilesRequest) -> Dict[str, Any]:
    """Create new files with specified content."""
    created_files = []
    
    for filename, content in request.files.items():
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
        
        with open(filename, 'w') as f:
            f.write(content)
        created_files.append(filename)
    
    if request.git_commit and created_files:
        try:
            # Add files to git
            add_command = ["git", "add"] + created_files
            add_process = await asyncio.create_subprocess_exec(
                *add_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await add_process.communicate()
            
            # Commit files
            commit_command = ["git", "commit", "-m", request.message]
            commit_process = await asyncio.create_subprocess_exec(
                *commit_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await commit_process.communicate()
            
            if commit_process.returncode != 0:
                return {
                    "success": True,
                    "warning": f"Files created but git commit failed: {stderr.decode()}",
                    "files": created_files
                }
        except Exception as e:
            return {
                "success": True,
                "warning": f"Files created but git commit failed: {str(e)}",
                "files": created_files
            }
    
    return {
        "success": True,
        "message": "Files created successfully",
        "files": created_files
    }

async def git_status() -> Dict[str, Any]:
    """Get git status of the repository."""
    try:
        command = ["git", "status"]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode()
            }
        
        # Also get git diff
        diff_command = ["git", "diff", "--staged"]
        diff_process = await asyncio.create_subprocess_exec(
            *diff_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        diff_stdout, diff_stderr = await diff_process.communicate()
        
        return {
            "success": True,
            "status": stdout.decode(),
            "staged_diff": diff_stdout.decode() if diff_process.returncode == 0 else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def extract_code(request: ExtractCodeRequest) -> Dict[str, Any]:
    """Extract code blocks from markdown text."""
    import re
    
    code_blocks = []
    # Match code blocks with language specification
    pattern = r"```(\w+)?\s*([\s\S]*?)```"
    matches = re.findall(pattern, request.text)
    
    for language, code in matches:
        code_blocks.append({
            "language": language.strip() if language else "text",
            "code": code.strip()
        })
    
    return {
        "success": True,
        "code_blocks": code_blocks,
        "count": len(code_blocks)
    }

async def check_aider_status() -> Dict[str, Any]:
    """Check if aider is installed and working."""
    try:
        command = [AIDER_PATH, "--version"]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return {
                "success": False,
                "error": f"Aider is not properly installed: {stderr.decode()}"
            }
        
        # Check for API keys
        environment_status = {
            "OPENAI_API_KEY": "set" if os.environ.get("OPENAI_API_KEY") else "not set",
            "ANTHROPIC_API_KEY": "set" if os.environ.get("ANTHROPIC_API_KEY") else "not set",
        }
        
        return {
            "success": True,
            "version": stdout.decode().strip(),
            "environment": environment_status,
            "repo_path": REPO_PATH
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"Aider executable not found at {AIDER_PATH}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def get_aider_config(request: AiderConfigRequest) -> Dict[str, Any]:
    """Get Aider configuration options."""
    repo_path = request.repo_path or REPO_PATH
    
    # Load YAML config
    yaml_config = load_aider_config(repo_path, request.config_file)
    
    # Load .env files
    env_vars = load_dotenv_file(request.env_file)
    
    # Extract Aider-specific environment variables
    aider_env_vars = {
        k.replace('AIDER_', '').lower().replace('_', '-'): v
        for k, v in env_vars.items()
        if k.startswith('AIDER_')
    }
    
    # Merge configs (env vars take precedence)
    config = {**yaml_config, **aider_env_vars}
    
    return {
        "success": True,
        "config": config,
        "config_files_loaded": True,
        "repo_path": repo_path
    }

# MCP Protocol endpoints
@app.get("/mcp")
async def get_mcp_schema():
    """Return the MCP schema with available methods."""
    schema = MCPSchema(
        server_info=MCPServerInfo(),
        methods=[
            MCPMethod(
                name="edit_files",
                description="Edit existing files using aider",
                parameters={
                    "files": {"type": "array", "description": "List of files to edit"},
                    "instructions": {"type": "string", "description": "Instructions for editing"},
                    "git_commit": {"type": "boolean", "description": "Whether to commit changes"},
                    "aider_options": {"type": "object", "description": "Additional options for Aider"}
                }
            ),
            MCPMethod(
                name="create_files",
                description="Create new files with content",
                parameters={
                    "files": {"type": "object", "description": "Dict of filename to content"},
                    "message": {"type": "string", "description": "Commit message"},
                    "git_commit": {"type": "boolean", "description": "Whether to commit changes"},
                    "aider_options": {"type": "object", "description": "Additional options for Aider"}
                }
            ),
            MCPMethod(
                name="git_status",
                description="Get git status of the repository",
                parameters={}
            ),
            MCPMethod(
                name="extract_code",
                description="Extract code blocks from markdown text",
                parameters={
                    "text": {"type": "string", "description": "Text containing code blocks"}
                }
            ),
            MCPMethod(
                name="aider_status",
                description="Check aider status and environment",
                parameters={
                    "check_environment": {"type": "boolean", "description": "Check environment"}
                }
            ),
            MCPMethod(
                name="aider_config",
                description="Get Aider configuration settings",
                parameters={
                    "repo_path": {"type": "string", "description": "Repository path"},
                    "config_file": {"type": "string", "description": "Custom config file path"},
                    "env_file": {"type": "string", "description": "Custom .env file path"}
                }
            )
        ]
    )
    return schema.dict()

@app.post("/mcp/edit_files")
async def mcp_edit_files(request: EditFilesRequest):
    """MCP endpoint to edit files using aider."""
    result = await edit_files(request)
    return result

@app.post("/mcp/create_files")
async def mcp_create_files(request: CreateFilesRequest):
    """MCP endpoint to create new files."""
    result = await create_files(request)
    return result

@app.post("/mcp/git_status")
async def mcp_git_status():
    """MCP endpoint to get git status."""
    result = await git_status()
    return result

@app.post("/mcp/extract_code")
async def mcp_extract_code(request: ExtractCodeRequest):
    """MCP endpoint to extract code from text."""
    result = await extract_code(request)
    return result

@app.post("/mcp/aider_status")
async def mcp_aider_status(request: AiderStatusRequest):
    """MCP endpoint to check aider status."""
    result = await check_aider_status()
    return result

@app.post("/mcp/aider_config")
async def mcp_aider_config(request: AiderConfigRequest):
    """MCP endpoint to get Aider configuration."""
    result = await get_aider_config(request)
    return result

@app.post("/mcp/{method}")
async def mcp_method_not_found(method: str):
    """Return error for non-existent methods."""
    raise HTTPException(
        status_code=404,
        detail=f"Method '{method}' not found. See /mcp for available methods."
    )

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Aider MCP Server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--aider-path", type=str, default="aider", help="Path to aider executable")
    parser.add_argument("--repo-path", type=str, default=os.getcwd(), help="Path to git repository")
    parser.add_argument("--config-file", type=str, help="Path to Aider config file")
    parser.add_argument("--env-file", type=str, help="Path to .env file")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    
    # Update global variables from command-line arguments
    AIDER_PATH = args.aider_path
    REPO_PATH = args.repo_path
    
    # Change to repository directory
    os.chdir(REPO_PATH)
    
    # Start server
    uvicorn.run(app, host=args.host, port=args.port) 