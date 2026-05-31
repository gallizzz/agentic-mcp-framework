import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

# Load environment variables from .env file
load_dotenv()

async def main():
    # Initialize the Google Gemini LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0.0 # Deterministic output
    )

    # Initialize the MCP client to connect to our EchoServer
    client = MultiServerMCPClient({
        "echo_server": {
            "command": "python",
            "args": ["mcp_server/echo_mcp_server.py"],
            "transport": "stdio" # Specifies that the client will communicate with the server via stdio
        }
    })
    
    # Connect to the MCP server and retrieve the available tools
    tools = await client.get_tools()
    print(f"Available tools retrieved: {[t.name for t in tools]}")

    # Create the ReAct agent with the LLM and the retrieved tools
    agent = create_agent(llm, tools)

    # Define the prompt for the agent
    prompt = (
        "Generate a brief greeting message. "
        "Subsequently, use the available tool to echo this greeting."
    )
    
    print("\n--- Starting Agent Execution ---\n")
    
    # Invoke the agent with the prompt and await the response
    response = await agent.ainvoke({"messages": [("user", prompt)]})
    
    # Print all messages generated during the process in a formatted way
    for message in response["messages"]:
        message.pretty_print()
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())