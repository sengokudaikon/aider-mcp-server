#!/usr/bin/env python3
"""
Test Client for Aider MCP Server

A simple client to test the Aider MCP Server functionality.
"""

import argparse
import json
import sys
import requests
from typing import Dict, Any, List, Optional


def get_schema(base_url: str) -> Dict[str, Any]:
    """Get the MCP schema from the server."""
    response = requests.get(f"{base_url}/mcp")
    response.raise_for_status()
    return response.json()


def call_method(base_url: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Call an MCP method with parameters."""
    response = requests.post(f"{base_url}/mcp/{method}", json=params)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    return response.json()


def check_aider_status(base_url: str) -> Dict[str, Any]:
    """Check Aider status."""
    return call_method(base_url, "aider_status", {"check_environment": True})


def get_git_status(base_url: str) -> Dict[str, Any]:
    """Get git status."""
    return call_method(base_url, "git_status", {})


def edit_files(base_url: str, files: List[str], instructions: str, git_commit: bool = True) -> Dict[str, Any]:
    """Edit files using Aider."""
    params = {
        "files": files,
        "instructions": instructions,
        "git_commit": git_commit
    }
    return call_method(base_url, "edit_files", params)


def create_files(base_url: str, files_dict: Dict[str, str], message: str, git_commit: bool = True) -> Dict[str, Any]:
    """Create new files with content."""
    params = {
        "files": files_dict,
        "message": message,
        "git_commit": git_commit
    }
    return call_method(base_url, "create_files", params)


def extract_code(base_url: str, text: str) -> Dict[str, Any]:
    """Extract code blocks from text."""
    params = {
        "text": text
    }
    return call_method(base_url, "extract_code", params)


def main():
    """Main function to run the test client."""
    parser = argparse.ArgumentParser(description="Test Client for Aider MCP Server")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000", help="Base URL of the MCP server")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Schema command
    schema_parser = subparsers.add_parser("schema", help="Get MCP schema")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check Aider status")
    
    # Git status command
    git_parser = subparsers.add_parser("git", help="Get git status")
    
    # Edit files command
    edit_parser = subparsers.add_parser("edit", help="Edit files using Aider")
    edit_parser.add_argument("--files", type=str, nargs="+", required=True, help="Files to edit")
    edit_parser.add_argument("--instructions", type=str, required=True, help="Instructions for editing")
    edit_parser.add_argument("--no-commit", action="store_true", help="Don't commit changes")
    
    # Create files command
    create_parser = subparsers.add_parser("create", help="Create new files")
    create_parser.add_argument("--files", type=str, nargs="+", required=True, help="Files to create (format: filename:content)")
    create_parser.add_argument("--message", type=str, required=True, help="Commit message")
    create_parser.add_argument("--no-commit", action="store_true", help="Don't commit changes")
    
    # Extract code command
    extract_parser = subparsers.add_parser("extract", help="Extract code blocks from text")
    extract_parser.add_argument("--text", type=str, required=True, help="Text containing code blocks")
    
    args = parser.parse_args()
    
    # Handle each command
    if args.command == "schema":
        schema = get_schema(args.base_url)
        print(json.dumps(schema, indent=2))
        
    elif args.command == "status":
        status = check_aider_status(args.base_url)
        print(json.dumps(status, indent=2))
        
    elif args.command == "git":
        status = get_git_status(args.base_url)
        print(json.dumps(status, indent=2))
        
    elif args.command == "edit":
        result = edit_files(
            args.base_url, 
            args.files, 
            args.instructions, 
            not args.no_commit
        )
        print(json.dumps(result, indent=2))
        
    elif args.command == "create":
        # Convert files list to dictionary
        files_dict = {}
        for file_spec in args.files:
            if ":" in file_spec:
                filename, content = file_spec.split(":", 1)
                files_dict[filename] = content
            else:
                files_dict[file_spec] = ""
        
        result = create_files(
            args.base_url, 
            files_dict, 
            args.message, 
            not args.no_commit
        )
        print(json.dumps(result, indent=2))
        
    elif args.command == "extract":
        result = extract_code(args.base_url, args.text)
        print(json.dumps(result, indent=2))
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 