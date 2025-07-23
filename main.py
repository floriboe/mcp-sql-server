
from fastapi import FastAPI
import os
from uvicorn import Config, Server

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

# Use programmatic startup to avoid asyncio.run() issue
port = int(os.environ.get("PORT", 8000))
print(f"Starting server on port {port}...")
config = Config(app=app, host="0.0.0.0", port=port)
server = Server(config=config)

import asyncio
loop = asyncio.get_event_loop()
loop.create_task(server.serve())
loop.run_forever()
