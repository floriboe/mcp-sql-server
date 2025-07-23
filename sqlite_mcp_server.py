#!/usr/bin/env python3
"""
SQLite MCP Server for Render deployment
Provides Claude with SQLite database access via MCP protocol
"""

import asyncio
import json
import os
import sqlite3
import sys
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

# MCP imports
try:
    from mcp import Server, types
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions, ServerRequestContext
    from mcp.server.stdio import stdio_server
except ImportError:
    print("Error: MCP package not found. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SQLiteMCPServer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.server = Server("sqlite-mcp-server")
        self._setup_database()
        self._register_handlers()
    
    def _setup_database(self):
        """Initialize the SQLite database if it doesn't exist"""
        if not os.path.exists(self.db_path):
            # Create a sample database with some tables
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create sample tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Insert sample data
            cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", 
                         ("John Doe", "john@example.com"))
            cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", 
                         ("Jane Smith", "jane@example.com"))
            
            cursor.execute("INSERT INTO posts (user_id, title, content) VALUES (?, ?, ?)",
                         (1, "First Post", "This is my first post!"))
            cursor.execute("INSERT INTO posts (user_id, title, content) VALUES (?, ?, ?)",
                         (2, "Hello World", "Hello from Jane!"))
            
            conn.commit()
            conn.close()
            logger.info(f"Created sample database at {self.db_path}")
    
    def _get_database_schema(self) -> Dict[str, Any]:
        """Get complete database schema information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        schema = {}
        for (table_name,) in tables:
            # Get column information
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            # Get foreign keys
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            foreign_keys = cursor.fetchall()
            
            schema[table_name] = {
                "columns": [
                    {
                        "name": col[1],
                        "type": col[2],
                        "nullable": not col[3],
                        "default": col[4],
                        "primary_key": bool(col[5])
                    }
                    for col in columns
                ],
                "foreign_keys": [
                    {
                        "column": fk[3],
                        "references_table": fk[2],
                        "references_column": fk[4]
                    }
                    for fk in foreign_keys
                ]
            }
        
        conn.close()
        return schema
    
    def _execute_query(self, query: str, params: Optional[List] = None) -> Dict[str, Any]:
        """Execute a SQL query safely"""
        # Basic safety checks
        query_lower = query.lower().strip()
        
        # Block potentially dangerous operations
        dangerous_keywords = ['drop', 'delete', 'truncate', 'alter', 'create', 'pragma']
        if any(keyword in query_lower for keyword in dangerous_keywords):
            if not query_lower.startswith('select'):
                return {
                    "error": "Only SELECT queries are allowed for safety",
                    "query": query
                }
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query_lower.startswith('select'):
                rows = cursor.fetchall()
                # Convert rows to dictionaries
                result = [dict(row) for row in rows]
                return {
                    "success": True,
                    "data": result,
                    "row_count": len(result)
                }
            else:
                conn.commit()
                return {
                    "success": True,
                    "rows_affected": cursor.rowcount
                }
                
        except sqlite3.Error as e:
            return {
                "error": str(e),
                "query": query
            }
        finally:
            conn.close()
    
    def _register_handlers(self):
        """Register MCP protocol handlers"""
        
        @self.server.list_resources()
        async def handle_list_resources() -> List[types.Resource]:
            """List available database resources"""
            return [
                types.Resource(
                    uri="sqlite:///schema",
                    name="Database Schema",
                    description="Complete database schema with tables and columns",
                    mimeType="application/json"
                ),
                types.Resource(
                    uri="sqlite:///tables",
                    name="Table List",
                    description="List of all tables in the database",
                    mimeType="application/json"
                )
            ]
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read database resource content"""
            if uri == "sqlite:///schema":
                schema = self._get_database_schema()
                return json.dumps(schema, indent=2)
            elif uri == "sqlite:///tables":
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                return json.dumps(tables, indent=2)
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available database tools"""
            return [
                types.Tool(
                    name="execute_query",
                    description="Execute a SQL SELECT query on the database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The SQL query to execute (SELECT only for safety)"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="get_table_info",
                    description="Get detailed information about a specific table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to inspect"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                types.Tool(
                    name="sample_data",
                    description="Get a sample of data from a table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to sample from"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of rows to return (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["table_name"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool calls"""
            try:
                if name == "execute_query":
                    query = arguments.get("query", "")
                    result = self._execute_query(query)
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2)
                    )]
                
                elif name == "get_table_info":
                    table_name = arguments.get("table_name", "")
                    schema = self._get_database_schema()
                    if table_name in schema:
                        table_info = schema[table_name]
                        return [types.TextContent(
                            type="text",
                            text=json.dumps(table_info, indent=2)
                        )]
                    else:
                        return [types.TextContent(
                            type="text",
                            text=json.dumps({"error": f"Table '{table_name}' not found"})
                        )]
                
                elif name == "sample_data":
                    table_name = arguments.get("table_name", "")
                    limit = arguments.get("limit", 10)
                    query = f"SELECT * FROM {table_name} LIMIT {limit}"
                    result = self._execute_query(query)
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2)
                    )]
                
                else:
                    return [types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Unknown tool: {name}"})
                    )]
                    
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}")
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)})
                )]

async def main():
    """Main entry point"""
    # Get database path from environment or use default
    db_path = os.getenv("DATABASE_PATH", "/tmp/database.db")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Create and run the server
    mcp_server = SQLiteMCPServer(db_path)
    
    logger.info(f"Starting SQLite MCP Server with database: {db_path}")
    
    # Run the server using stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sqlite-mcp-server",
                server_version="1.0.0",
                capabilities=mcp_server.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())