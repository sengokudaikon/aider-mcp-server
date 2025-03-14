"""Aider MCP Server - Connect Claude to Aider file editing capabilities"""

__version__ = "0.1.0"

import asyncio
import logging
import os
import sys
import shutil
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Setup logging
logging.basicConfig(
    level=logging.INFO if not os.environ.get("AIDER_MCP_VERBOSE") else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("aider-mcp")
console = Console()

app = typer.Typer(help="Aider MCP Server - Connect Claude to Aider file editing capabilities")

def find_aider_executable() -> str:
    """Find the Aider executable in the PATH."""
    aider_path = shutil.which("aider")
    if not aider_path:
        logger.warning("Aider executable not found in PATH. Will try to use 'aider' directly.")
        return "aider"
    logger.info(f"Found Aider executable at: {aider_path}")
    return aider_path

@app.command()
def run(
    aider_path: str = typer.Option(
        ..., 
        help="Path to the Aider executable"
    ),
    repo_path: str = typer.Option(
        ..., 
        help="Path to the git repository working directory"
    ),
    config_file: Optional[str] = typer.Option(
        None, 
        help="Path to custom Aider config file (will search in repo_path by default)"
    ),
    env_file: Optional[str] = typer.Option(
        None, 
        help="Path to custom .env file (will search in repo_path by default)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output"
    ),
) -> None:
    """Run the MCP Aider server via stdio."""
    # Handle environment variables and defaults
    config_file = config_file or os.environ.get("AIDER_CONFIG_FILE")
    env_file = env_file or os.environ.get("AIDER_ENV_FILE")
    verbose = verbose or bool(os.environ.get("AIDER_MCP_VERBOSE", False))
    
    if verbose:
        logging.getLogger("aider-mcp").setLevel(logging.DEBUG)
    
    # Ensure repo_path exists and is absolute
    repo_path = os.path.abspath(repo_path)
    if not os.path.exists(repo_path):
        logger.error(f"Repository path does not exist: {repo_path}")
        sys.exit(1)
    
    logger.info(f"Using repository path: {repo_path}")
    
    # Load environment variables from .env file
    if env_file:
        logger.info(f"Loading environment from specified file: {env_file}")
        load_dotenv(env_file)
    else:
        # Try to load from common locations
        for env_path in [
            Path(repo_path) / ".env",  # Repository directory first
            Path.cwd() / ".env",       # Current directory
            Path.home() / ".env",      # Home directory last
        ]:
            if env_path.exists():
                logger.info(f"Loading environment from: {env_path}")
                load_dotenv(env_path)
                break

    # Create and start the server
    asyncio.run(run_server(aider_path, repo_path, config_file, env_file))

def main():
    """Entry point for the package."""
    app()

async def run_server(
    aider_path: str,
    repo_path: str,
    config_file: Optional[str] = None,
    env_file: Optional[str] = None,
) -> None:
    """Run the MCP Aider server directly via stdio."""
    from aider_mcp.server import create_server, server_lifespan
    
    initialization_options = {
        "aider_path": aider_path,
        "repo_path": repo_path,
        "config_file": config_file,
        "env_file": env_file
    }
    
    app = create_server()
    
    logger.info(f"Starting Aider MCP Server with Aider at: {aider_path}")
    logger.info(f"Working directory: {repo_path}")
    
    async with stdio_server() as (read_stream, write_stream):
        # Initialize the server's lifespan context with our initialization_options
        app.lifespan = lambda server: server_lifespan(server, initialization_options)
        await app.run(read_stream, write_stream, initialization_options)

if __name__ == "__main__":
    main() 