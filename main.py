
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import sqlite3
import os
import requests

app = FastAPI()
DB_PATH = "coding_data.db"
SQL_URL = "https://storage.googleapis.com/antedata_open/coding_data.sql"

# Download and build database on startup if needed
if not os.path.exists(DB_PATH):
    print("DB not found — downloading SQL file...")
    try:
        r = requests.get(SQL_URL)
        r.raise_for_status()
        with open("coding_data.sql", "wb") as f:
            f.write(r.content)
        print("SQL file downloaded — creating database...")
        with sqlite3.connect(DB_PATH) as conn:
            with open("coding_data.sql", "r") as f:
                conn.executescript(f.read())
        print("Database created successfully.")
    except Exception as e:
        print(f"Error creating database: {e}")
        raise RuntimeError(f"DB init failed: {e}")

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
        rows = cursor.fetchall()

        # Handle columns only if present
        cols = [desc[0] for desc in cursor.description] if cursor.description else []
        result = [dict(zip(cols, row)) for row in rows] if cols else []

        conn.close()

        return {
            "tool_response": {
                "output": {
                    "result": result
                }
            }
        }

    except Exception as e:
        print(f"Query failed: {e}")
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
                        "query": { "type": "string" }
                    },
                    "required": ["query"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "array",
                            "items": { "type": "object" }
                        }
                    }
                }
            }
        ]
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port)
