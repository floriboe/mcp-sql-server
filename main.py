
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import sqlite3
import os

app = FastAPI()
DB_PATH = "coding_data.db"

# Bootstrap database from SQL file if it doesn't exist
if not os.path.exists(DB_PATH):
    with sqlite3.connect(DB_PATH) as conn:
        with open("coding_data.sql", "r") as f:
            conn.executescript(f.read())

class QueryInput(BaseModel):
    query: str

@app.post("/mcp")
def mcp_tool_handler(payload: Dict[str, Any]):
    tool_call = payload.get("tool_call", {})
    if tool_call.get("name") != "query_sql":
        raise HTTPException(status_code=400, detail="Unsupported tool")

    query = tool_call.get("input", {}).get("query", "")
    if not query.strip().lower().startswith("select"):
        raise HTTPException(status_code=403, detail="Only SELECT queries are allowed")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        result = [dict(zip(cols, row)) for row in rows]
        conn.close()
        return {"tool_response": {"output": {"result": result}}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/.well-known/mcp-schema.json")
def get_schema():
    return {
        "tools": [
            {
                "name": "query_sql",
                "description": "Run a SELECT SQL query on the dataset.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "array",
                            "items": {"type": "object"}
                        }
                    }
                }
            }
        ]
    }
