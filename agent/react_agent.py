import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

# Load environment variables from .env file
load_dotenv()

def print_clean_message(message):
    m_type = message.type
    
    if m_type == "ai":
        # Print tool calls if any
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                print(f"🔧 [Tool Call] Using '{tc['name']}' with args: {tc['args']}")
        
        # Extract text content
        content = message.content
        text_content = ""
        if isinstance(content, str):
            text_content = content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_content += part.get("text", "")
                elif isinstance(part, str):
                    text_content += part
        
        if text_content.strip():
            print(f"\n🤖 Agent:\n{text_content.strip()}")
            
    elif m_type == "tool":
        content = message.content
        text_content = ""
        if isinstance(content, str):
            text_content = content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_content += part.get("text", "")
                elif isinstance(part, str):
                    text_content += part
        
        # Truncate tool output to prevent cluttering
        max_len = 250
        truncated = text_content.strip()
        if len(truncated) > max_len:
            truncated = truncated[:max_len] + "... [truncated]"
        print(f"📥 [Tool Output] {truncated}")

async def main():
    # Initialize the Google Gemini LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash", 
        temperature=0.0 # Deterministic output
    )

    # Initialize the MCP client to connect to our EchoServer and PetstoreServer
    client = MultiServerMCPClient({
        "echo_server": {
            "command": "python",
            "args": ["mcp_server/echo_mcp_server.py"],
            "transport": "stdio" # Specifies that the client will communicate with the server via stdio
        },
        "petstore_server": {
            "command": "python",
            "args": ["mcp_server/petstore_mcp_server.py"],
            "transport": "stdio"
        }
    })
    
    # Connect to the MCP servers and retrieve the available tools
    tools = await client.get_tools()
    print(f"Available tools retrieved: {[t.name for t in tools]}")

    # Create the ReAct agent with the LLM and the retrieved tools
    agent = create_agent(llm, tools)

    print("\n=== Agent is ready! ===")
    print("Type your requests below. Type 'exit' or 'quit' to terminate.")
    
    while True:
        try:
            prompt = input("\nYou: ")
            if not prompt.strip():
                continue
            if prompt.strip().lower() in ["exit", "quit"]:
                print("Exiting...")
                break
                
            print("\n--- Starting Agent Execution ---\n")
            
            # Invoke the agent with the prompt and await the response
            response = await agent.ainvoke({"messages": [("user", prompt)]})
            
            # Print all messages generated during the process in a formatted way
            for message in response["messages"]:
                print_clean_message(message)
            print("-" * 40)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break

if __name__ == "__main__":
    asyncio.run(main())