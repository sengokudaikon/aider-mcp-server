"""Tests for the Aider MCP Server."""

import json
import os
from pathlib import Path
import pytest
import tempfile
import asyncio
import contextlib
import contextvars
from unittest.mock import patch, MagicMock, AsyncMock

from aider_mcp.server import find_git_root, load_aider_config, load_dotenv_file, create_server
from mcp.types import TextContent
from mcp.shared.context import RequestContext
from mcp.shared.session import ServerSession


def test_find_git_root():
    """Test finding a git root directory."""
    # Current directory is not a git root
    assert find_git_root(os.getcwd()) is not None


def test_load_aider_config():
    """Test loading Aider configuration."""
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.yml', delete=False) as f:
        f.write("model: gpt-4\ndark_mode: true\n")
        config_file = f.name
    
    try:
        # Load the config
        config = load_aider_config(config_file=config_file)
        
        # Check that the config contains the expected values
        assert "model" in config
        assert config["model"] == "gpt-4"
        assert "dark_mode" in config
        assert config["dark_mode"] is True
    finally:
        # Clean up
        os.unlink(config_file)


def test_load_dotenv_file():
    """Test loading environment variables from .env file."""
    # Create a temporary .env file
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.env', delete=False) as f:
        f.write("TEST_VAR=test_value\nOTHER_VAR=other_value\n")
        env_file = f.name
    
    try:
        # Load the environment variables
        env_vars = load_dotenv_file(env_file=env_file)
        
        # Check that the environment variables were loaded correctly
        assert "TEST_VAR" in env_vars
        assert env_vars["TEST_VAR"] == "test_value"
        assert "OTHER_VAR" in env_vars
        assert env_vars["OTHER_VAR"] == "other_value"
    finally:
        # Clean up
        os.unlink(env_file)


def test_create_server():
    """Test creating the MCP server."""
    # Create the server
    server = create_server()
    
    # Check that the server has the expected attributes
    assert server.name == "aider-mcp"
    assert hasattr(server, "list_resources")
    assert hasattr(server, "read_resource")
    assert hasattr(server, "list_tools")
    assert hasattr(server, "call_tool")
    

@contextlib.contextmanager
def mock_request_context(server):
    """Create a mock request context for testing."""
    # Create a mock lifespan context
    lifespan_context = MagicMock()
    lifespan_context.aider_path = "aider"
    
    # Create a mock session
    session = ServerSession()
    
    # Create a request context
    context = RequestContext(
        request_id="test-request-id",
        request_meta={},
        session=session,
        lifespan_context=lifespan_context
    )
    
    # Set the context in the server
    token = server._routes["request_ctx"].set(context)
    try:
        yield context
    finally:
        server._routes["request_ctx"].reset(token)


@pytest.mark.asyncio
async def test_list_tools():
    """Test that the server lists the expected tools."""
    # Create the server
    server = create_server()
    
    # Use the mock context
    with mock_request_context(server):
        # Access the list_tools handler directly
        handler = server._routes["list_tools"]
        
        # Call the handler function
        tools = await handler()
        
        # Get the tool names
        tool_names = [tool.name for tool in tools]
        
        # Check that the expected tools are in the list
        expected_tools = [
            "edit_files",
            "create_files",
            "git_status",
            "extract_code",
            "aider_status",
            "aider_config"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names


@pytest.mark.asyncio
async def test_list_resources():
    """Test that the server lists the expected resources."""
    # Create the server
    server = create_server()
    
    # Use the mock context
    with mock_request_context(server):
        # Access the list_resources handler directly
        handler = server._routes["list_resources"]
        
        # Call the handler function
        resources = await handler()
        
        # Check that the resources list is not empty
        assert len(resources) > 0
        
        # Check that the resources have the required attributes
        for resource in resources:
            assert hasattr(resource, "uri")
            assert hasattr(resource, "name")


@pytest.mark.asyncio
async def test_read_resource_not_found():
    """Test reading a resource that doesn't exist."""
    # Create the server
    server = create_server()
    
    # Use the mock context
    with mock_request_context(server):
        # Access the read_resource handler directly
        handler = server._routes["read_resource"]
        
        # Call the handler function with an invalid URI
        content, content_type = await handler(uri="invalid:uri")
        
        # Check that the response indicates the resource wasn't found
        assert "not found" in content.lower()
        assert content_type == "text/plain"


@pytest.mark.asyncio
async def test_call_tool_unknown():
    """Test calling an unknown tool."""
    # Create the server
    server = create_server()
    
    # Use the mock context
    with mock_request_context(server):
        # Access the call_tool handler directly
        handler = server._routes["call_tool"]
        
        # Call the handler function with an unknown tool name
        response = await handler(name="unknown_tool", arguments={})
        
        # Check that the response indicates the tool is unknown
        assert len(response) == 1
        assert response[0].type == "text"
        assert "unknown tool" in response[0].text.lower()


@pytest.mark.asyncio
async def test_extract_code_tool():
    """Test the extract_code tool."""
    # Create the server
    server = create_server()
    
    # Test input with code blocks
    test_input = """
    Here is some Python code:
    ```python
    def hello_world():
        print("Hello, world!")
    ```
    
    And here's some JavaScript:
    ```javascript
    function greet() {
        console.log("Hello!");
    }
    ```
    """
    
    # Use the mock context
    with mock_request_context(server):
        # Access the call_tool handler directly
        handler = server._routes["call_tool"]
        
        # Call the extract_code tool
        response = await handler(name="extract_code", arguments={"text": test_input})
        
        # Check the response
        assert len(response) > 0
        assert response[0].type == "text"
        
        # Response should contain information about the extracted code blocks
        assert "python" in response[0].text.lower()
        assert "javascript" in response[0].text.lower()


@pytest.mark.asyncio
async def test_aider_config_tool():
    """Test the aider_config tool."""
    # Create the server
    server = create_server()
    
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.aider.conf.yml', delete=False) as f:
        f.write("model: gpt-4\ndark_mode: true\n")
        temp_dir = os.path.dirname(f.name)
    
    try:
        # Use the mock context
        with mock_request_context(server):
            # Mock the load_aider_config function to return our test config
            with patch('aider_mcp.server.load_aider_config') as mock_load_config:
                mock_load_config.return_value = {"model": "gpt-4", "dark_mode": True}
                
                # Access the call_tool handler directly
                handler = server._routes["call_tool"]
                
                # Call the aider_config tool
                response = await handler(name="aider_config", arguments={"directory": temp_dir})
                
                # Check the response
                assert len(response) > 0
                assert response[0].type == "text"
                
                # Parse the JSON response
                result = json.loads(response[0].text)
                
                # Verify that the config is in the response
                assert "config" in result
                assert result["config"]["model"] == "gpt-4"
                assert result["config"]["dark_mode"] is True
    finally:
        # Clean up
        os.unlink(f.name)


@pytest.mark.asyncio
async def test_git_status_tool():
    """Test the git_status tool."""
    # Create the server
    server = create_server()
    
    # Use the mock context
    with mock_request_context(server):
        # Mock the run_command function to return a git status output
        with patch('aider_mcp.server.run_command') as mock_run_command:
            mock_run_command.return_value = (
                "On branch main\nYour branch is up to date with 'origin/main'.\n\n"
                "Changes not staged for commit:\n"
                "  (use \"git add <file>...\" to update what will be committed)\n"
                "  (use \"git restore <file>...\" to discard changes in working directory)\n"
                "        modified:   README.md\n\n"
                "Untracked files:\n"
                "  (use \"git add <file>...\" to include in what will be committed)\n"
                "        new_file.txt\n\n",
                ""
            )
            
            # Access the call_tool handler directly
            handler = server._routes["call_tool"]
            
            # Call the git_status tool
            response = await handler(name="git_status", arguments={"directory": os.getcwd()})
            
            # Check the response
            assert len(response) > 0
            assert response[0].type == "text"
            
            # Response should contain information about the git status
            assert "branch main" in response[0].text.lower()
            assert "modified" in response[0].text.lower()
            assert "untracked" in response[0].text.lower()


@pytest.mark.asyncio
async def test_create_files_tool():
    """Test the create_files tool."""
    # Create the server
    server = create_server()
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Use the mock context
        with mock_request_context(server):
            # Mock the run_command function to simulate successful git operations
            with patch('aider_mcp.server.run_command') as mock_run_command:
                mock_run_command.return_value = ("", "")
                
                # Files to create
                files = {
                    "test_file.py": "print('Hello, world!')",
                    "another_file.txt": "This is a test file."
                }
                
                # Access the call_tool handler directly
                handler = server._routes["call_tool"]
                
                # Call the create_files tool
                response = await handler(
                    name="create_files",
                    arguments={
                        "directory": temp_dir,
                        "files": files,
                        "message": "Add test files",
                        "git_commit": True
                    }
                )
                
                # Check the response
                assert len(response) > 0
                assert response[0].type == "text"
                
                # Response should indicate success
                assert "created" in response[0].text.lower()
                
                # Check that the files were actually created
                for filename, content in files.items():
                    file_path = os.path.join(temp_dir, filename)
                    assert os.path.exists(file_path)
                    with open(file_path, 'r') as f:
                        assert f.read() == content


@pytest.mark.asyncio
async def test_aider_status_tool():
    """Test the aider_status tool."""
    # Create the server
    server = create_server()
    
    # Use the mock context
    with mock_request_context(server):
        # Mock the run_command function to return a version string
        with patch('aider_mcp.server.run_command') as mock_run_command:
            mock_run_command.return_value = ("aider 0.25.0\n", "")
            
            # Mock the load_aider_config function
            with patch('aider_mcp.server.load_aider_config') as mock_load_config:
                mock_load_config.return_value = {"model": "gpt-4", "dark_mode": True}
                
                # Mock the load_dotenv_file function
                with patch('aider_mcp.server.load_dotenv_file') as mock_load_env:
                    mock_load_env.return_value = {"OPENAI_API_KEY": "sk-..."}
                    
                    # Access the call_tool handler directly
                    handler = server._routes["call_tool"]
                    
                    # Call the aider_status tool
                    response = await handler(
                        name="aider_status",
                        arguments={
                            "directory": os.getcwd(),
                            "check_environment": True
                        }
                    )
                    
                    # Check the response
                    assert len(response) > 0
                    assert response[0].type == "text"
                    
                    # Parse the JSON response
                    result = json.loads(response[0].text)
                    
                    # Verify the response contains expected information
                    assert "aider_version" in result
                    assert result["aider_version"] == "aider 0.25.0"
                    assert "config" in result
                    assert "environment" in result
                    assert "api_keys" in result["environment"]


@pytest.mark.asyncio
async def test_edit_files_tool():
    """Test the edit_files tool."""
    # Create the server
    server = create_server()
    
    # Create a temporary directory with a test file
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test file to edit
        test_file = os.path.join(temp_dir, "test_file.py")
        with open(test_file, 'w') as f:
            f.write("def hello():\n    print('Hello')\n")
        
        # Use the mock context
        with mock_request_context(server):
            # Define the expected output from running aider
            aider_output = (
                "Aider: I'll help you update the hello function to include a world parameter.\n\n"
                "I've made the following changes to test_file.py:\n\n"
                "```diff\n"
                "- def hello():\n"
                "-     print('Hello')\n"
                "+ def hello(world='world'):\n"
                "+     print(f'Hello, {world}!')\n"
                "```\n\n"
                "Committed as: Updated hello function with world parameter\n",
                ""
            )
            
            # Mock the run_command function to return the expected output
            with patch('aider_mcp.server.run_command', new_callable=AsyncMock) as mock_run:
                mock_run.return_value = aider_output
                
                # Access the call_tool handler directly
                handler = server._routes["call_tool"]
                
                # Call the edit_files tool
                response = await handler(
                    name="edit_files",
                    arguments={
                        "directory": temp_dir,
                        "message": "Update the hello function to include a world parameter"
                    }
                )
                
                # Check the response format
                assert len(response) > 0
                assert response[0].type == "text"
                
                # Verify the aider output is included in the response
                response_text = response[0].text
                assert "updated hello function" in response_text.lower()
                
                # Check that mock_run was called with the expected arguments
                mock_run.assert_called_once()
                # We expect the command to include 'aider' and the message
                args = mock_run.call_args[0][0]
                assert 'aider' in args[0].lower() or args[0].endswith('aider')
                message_file_content = ""
                # The message should be written to a file which is passed to aider
                with open(args[-1], 'r') as f:
                    message_file_content = f.read()
                assert "world parameter" in message_file_content 