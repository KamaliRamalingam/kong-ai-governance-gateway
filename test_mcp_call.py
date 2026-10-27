import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def main():
    try:
        async with sse_client("http://localhost:8765/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("Connected to MCP!")
                res = await session.call_tool("read_file", arguments={"filename": "vehicle_specs.csv"})
                print("Tool Result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
