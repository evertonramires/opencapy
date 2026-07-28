import json
import os
import sys

import anyio
import mcp.types as types
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)
# The Claude Code CLI spawns this bridge with its own environment, so point dotenv at the repo .env
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from connectors.llm_connector import _load_tools_from_disk

tools, handlers = _load_tools_from_disk()


async def list_tools(context, params) -> types.ListToolsResult:
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name=tool["function"]["name"],
                description=tool["function"]["description"],
                input_schema=tool["function"]["parameters"],
            )
            for tool in tools
        ]
    )


async def call_tool(context, params) -> types.CallToolResult:
    arguments = dict(params.arguments or {})
    if params.name == "ask_human":
        arguments.setdefault("original_user_prompt", os.getenv("OPENCAPY_ORIGINAL_PROMPT", ""))
    result = handlers[params.name](**arguments)
    content = json.dumps(result) if isinstance(result, (dict, list)) else str(result)
    return types.CallToolResult(content=[types.TextContent(type="text", text=content)])


async def serve() -> None:
    server = Server("opencapy", version="1.0.0", on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(serve)
