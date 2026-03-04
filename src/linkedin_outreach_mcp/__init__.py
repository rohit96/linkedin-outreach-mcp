"""LinkedIn Outreach MCP Server.

An MCP server for LinkedIn outreach automation — discover prospects,
send personalized connections, and track your pipeline from Claude Code.
"""

__version__ = "0.1.0"


def main():
    """Entry point for the MCP server."""
    from .server import main as server_main
    server_main()
