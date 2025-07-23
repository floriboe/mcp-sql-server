
from fastapi import FastAPI
import os
import uvicorn

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

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

# Always run the server, even if main.py is run via module import
port = int(os.environ.get("PORT", 8000))
print(f"Starting server on port {port}...")
uvicorn.run("main:app", host="0.0.0.0", port=port)
