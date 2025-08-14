# ops-agent — AI Linux Ops Agent (Modal-backed)

Type a request, the agent plans a safe fix, and executes it inside a secure Linux container on Modal.

## Quickstart

```bash
python -m pip install -U modal typer openai python-dotenv
cp .env.example .env  # add OPENAI_API_KEY=... (optional)
modal deploy apps/modal_app.py

# Examples
python -m cli.main hello
python -m cli.main do "install postgres" --yes
python -m cli.main do "free up disk space"       # dry-run
python -m cli.main do "free up disk space" --yes # actually cleans
python -m cli.main do "nginx crashed — fix it" --yes
```
