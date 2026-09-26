import asyncio
import os
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import GoogleRateLimitError
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console
from rich.markdown import Markdown

import logging

# Suppress internal MCP and LangChain info logs
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)

# Load environment variables from .env file
load_dotenv()

# Set timezone to Rome
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

console = Console()

def print_clean_message(message):
    m_type = message.type
    
    if m_type == "ai":
        # Print tool calls if any
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                console.print(f"[{time.strftime('%X')}] 🔧 [Tool Call] Using '{tc['name']}' with args: {tc['args']}", style="bold yellow")
        
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
            console.print(f"\n[{time.strftime('%X')}] 🤖 Agent:", style="bold cyan")
            console.print(Markdown(text_content.strip()))
            
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
        console.print(f"[{time.strftime('%X')}] 📥 [Tool Output] {truncated}", style="dim")

async def main():
    # Initialize the LLM with the Google Gemini model
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.8-flash",
        request_timeout=30.0,
        temperature=0.0,
    )

    console.print(f"[{time.strftime('%X')}] Initializing MCP client and retrieving tools...", style="dim")

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
    console.print(f"[{time.strftime('%X')}] Tools retrieved successfully: {[t.name for t in tools]}", style="dim")

    # System prompt for concise LLM style
    system_prompt = (
        "Sei un assistente per una CLI tecnica. Sii chiaro, incisivo e sintetico. "
        "Privilegia risposte compatte, evita convenevoli o introduzioni prolisse."
    )

    # Create the ReAct agent with the LLM, tools, and system prompt
    agent = create_agent(llm, tools, system_prompt=system_prompt)

    console.print(f"\n[{time.strftime('%X')}] === Agent is ready! ===", style="bold green")
    console.print("Type your requests below. Type 'exit' or 'quit' to terminate.", style="dim")
    
    while True:
        try:
            prompt = input("\nYou: ")
            if not prompt.strip():
                continue
            if prompt.strip().lower() in ["exit", "quit"]:
                console.print(f"[{time.strftime('%X')}] Exiting...", style="dim")
                break
                            
            with console.status(f"[bold green][{time.strftime('%X')}] Agent is thinking...", spinner="dots"):
                response = await agent.ainvoke({"messages": [("user", prompt)]})
            
            # Print all messages generated during the process in a formatted way
            for message in response["messages"]:
                print_clean_message(message)
            console.print("-" * 40, style="dim")
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[{time.strftime('%X')}] Exiting...", style="dim")
            break
        except GoogleRateLimitError:
            console.print(f"\n[{time.strftime('%X')}] ⚠️ [Quota Exceeded] Hai raggiunto il limite temporaneo di richieste per il modello Gemini (HTTP 429). Riprova tra circa 30 secondi.", style="bold red")
            console.print("-" * 40, style="dim")
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                console.print(f"\n[{time.strftime('%X')}] ⚠️ [Quota Exceeded] Limite di richieste superato (HTTP 429). Riprova tra qualche secondo.", style="bold red")
            else:
                console.print(f"\n[{time.strftime('%X')}] ❌ [Error] Si è verificato un errore: {e}", style="bold red")
            console.print("-" * 40, style="dim")

if __name__ == "__main__":
    asyncio.run(main())