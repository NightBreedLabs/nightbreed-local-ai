#!/usr/bin/env python3
"""Optional Antigravity SDK example: external Ollama server as the agent's own model.
Requires the Google Antigravity SDK, installed in a separate venv; never modifies the IDE.
"""
import asyncio
import os
import sys

async def main():
    try:
        from google.antigravity import Agent, LocalOpenAIAgentConfig
    except ImportError:
        sys.exit('Install the Google Antigravity SDK into a dedicated virtual environment first. See README.md.')
    model = os.environ.get('NBAI_SDK_MODEL', 'qwen2.5-coder:7b')
    if model.endswith(':cloud'):
        sys.exit('Cloud model rejected by local-only example.')
    config = LocalOpenAIAgentConfig(model=model, base_url='http://127.0.0.1:11434/v1').lightweight()
    async with Agent(config) as agent:
        response = await agent.chat(' '.join(sys.argv[1:]) or 'Explain three practical uses for local AI on Linux.')
        async for token in response:
            print(token,end='',flush=True)
        print()

if __name__ == '__main__':
    asyncio.run(main())
