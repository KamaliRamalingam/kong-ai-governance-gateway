import asyncio
import httpx
import json
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

KONG_AI_URL = "http://localhost:8000/ai"
KONG_MCP_URL = "http://localhost:5000/sse"
MODEL = "google/gemini-2.0-flash-001"
MAX_TOOL_LOOPS = 5  # Prevent infinite loops

async def chat_with_agent(prompt: str):
    print(f"\n[Agent] Connecting to MCP Server via Kong at {KONG_MCP_URL}...")
    
    try:
        async with sse_client(KONG_MCP_URL) as streams:
            async with ClientSession(streams[0], streams[1]) as mcp:
                await mcp.initialize()
                
                # 1. Discover Tools
                print("[Agent] Discovering tools...")
                tools_response = await mcp.list_tools()
                
                # Format tools for OpenRouter / Gemini format
                llm_tools = []
                for t in tools_response.tools:
                    llm_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema
                        }
                    })
                
                system_prompt = (
                    "You are a helpful Volvo data assistant. You have access to several local dataset files via your MCP tools.\n"
                    "Before answering user questions about data, ALWAYS use the list_available_files tool to see what documents exist, "
                    "and then use the fetch_documents tool to read their contents. "
                    "IMPORTANT: Use the actual tool calls — do NOT write Python code blocks. "
                    "After fetching the documents, summarize their contents directly."
                )
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
                
                async with httpx.AsyncClient(timeout=60.0) as http:
                    # ── AGENTIC LOOP ──────────────────────────────────────────
                    for loop_count in range(MAX_TOOL_LOOPS):
                        print(f"[Agent] Sending prompt and tools to LLM via Kong AI Proxy...")
                        
                        response = await http.post(
                            KONG_AI_URL,
                            json={
                                "model": MODEL,
                                "messages": messages,
                                "tools": llm_tools
                            },
                            headers={"Content-Type": "application/json"}
                        )
                        
                        data = response.json()
                        
                        if "error" in data:
                            print(f"\n⛔ KONG BLOCKED REQUEST: {data['error'].get('message', data['error'])}")
                            return
                        
                        message = data["choices"][0].get("message", {})
                        
                        # If no tool call, we have the final answer — break out
                        if "tool_calls" not in message or not message["tool_calls"]:
                            print(f"\n[LLM Final Answer]:\n{message.get('content', '')}")
                            return
                        
                        # Handle all tool calls in the response
                        messages.append(message)
                        
                        for tool_call in message["tool_calls"]:
                            function_name = tool_call["function"]["name"]
                            args = json.loads(tool_call["function"]["arguments"])
                            
                            print(f"\n[Agent] 🛠️  Tool call: {function_name}({args})")
                            
                            tool_result = await mcp.call_tool(function_name, arguments=args)
                            
                            result_text = "\n".join(
                                c.text for c in tool_result.content if c.type == "text"
                            )
                            
                            print(f"[Agent] ✅ Tool returned {len(result_text)} characters.")
                            
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": result_text,
                                "name": function_name
                            })
                    
                    print("[Agent] Reached max tool iterations without a final answer.")
                    
    except Exception as e:
        print(f"\n[Agent Error] Failed to connect or execute: {e}")
        print("Please ensure that 'python mcp_server.py' is running in another terminal!")

async def main():
    print("=======================================")
    print("Volvo DNS TAPIR - Secure MCP Agent Demo")
    print("=======================================")
    print("Type 'quit' or 'exit' to stop.\n")
    
    while True:
        try:
            user_input = input("You: ")
        except EOFError:
            break
        if user_input.lower() in ["quit", "exit"]:
            break
        if not user_input.strip():
            continue
        await chat_with_agent(user_input)

if __name__ == "__main__":
    asyncio.run(main())
