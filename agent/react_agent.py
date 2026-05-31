import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

# Load the environment variables from the .env file
load_dotenv()

async def main():
    # Instance of the LLM with deterministic settings
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0.0  # Zero temperature for deterministic output
    )

    # Connect to the Echo MCP Server and retrieve the available tools
    async with MultiServerMCPClient() as client:
        await client.connect_to_server(
            "echo_server",
            command="python",
            args=["mcp_server/echo_mcp_server.py"]
        )
        
        tools = client.get_tools()
        print(f"Available tools: {[t.name for t in tools]}")

        # Create the ReAct agent with the LLM and the retrieved tools
        agent = create_react_agent(llm, tools)

        # Define the prompt for the agent to generate a greeting and use the echo tool
        prompt = (
            "Generate a brief greeting message. "
            "Subsequently, use the available tool to echo this greeting."
        )
        
        print("\n--- Starting Agent Execution ---\n")
        
        # Stream the agent's reasoning process and tool usage in real-time
        async for event in agent.astream({"messages": [("user", prompt)]}):
            for node_name, node_data in event.items():
                if node_name == "agent":
                    message_content = node_data['messages'][0].content
                    if message_content:
                        print(f"[Agent]: {message_content}")
                    else:
                        print(f"[Agent is calling a tool...]")
                elif node_name == "tools":
                    print(f"[System]: Tool executed.")

if __name__ == "__main__":
    asyncio.run(main())