LinOps – AI-Powered Linux Operations Agent

Overview

LinOps is an AI-powered Linux operations agent that turns plain-English instructions into safe, automated server actions.
It can:
• Chain multiple runbooks (e.g., “free up disk and check CPU”).
• Reject unsafe or destructive requests.
• Fall back to generating safe shell commands for requests outside its runbook library.
• Auto-heal common failures (e.g., restart nginx if it crashes).

Built with Modal for scalable, containerized execution and the OpenAI API for natural-language planning.

Quick Start

1. Clone the repo
   git clone https://github.com/<your-username>/linops.git
   cd linops

2. Install dependencies
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

3. Set environment variables
   export OPENAI_API_KEY="your-openai-api-key"
   export OPS_APP="ops-agent"
   export AUTOHEAL_APP="ops-agent-autoheal"

4. Deploy to Modal
   modal deploy apps/modal_app.py
   modal deploy apps/auto_heal.py

5. Run commands via CLI
   python -m cli.main list
   python -m cli.main plan "free up disk and check cpu"
   python -m cli.main do "free up disk and check cpu" --yes
   modal run apps/auto_heal.py::watch_once

Example Demo Flow 1. Chain runbooks:
• Command: python -m cli.main do "free up disk and check cpu" --yes | tee demo/disk_cpu.json
• Shows automatic chaining of disk cleanup + CPU/memory check. 2. Fallback safe shell:
• Command: python -m cli.main do "list running processes" --yes | tee demo/list_processes.json
• Demonstrates generating and executing a safe command outside runbook library. 3. Auto-heal:
• Simulate failure: stop nginx.
• Run: modal run apps/auto_heal.py::watch_once | tee demo/autoheal_fix.json
• Shows nginx restarted automatically.

How It Works 1. Planner – Uses OpenAI to map natural-language requests to runbooks. 2. Safety Layer – Blocks dangerous commands (e.g., rm -rf /, shutdown). 3. Modal Functions – Run each operation inside a containerized, scalable environment. 4. Auto-Heal – Periodic check for known failures; automatically runs safe fixes.
