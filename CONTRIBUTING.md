# Contributing to Iron-Thread

First off — thank you. Iron-Thread is built for developers 
who care about reliable AI systems. Every contribution matters.

## Ways to Contribute

### 1. Report Bugs
Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your Python/Node version

### 2. Suggest Features
Open an issue tagged `enhancement`. 
The best suggestions come from real pain points — 
tell us what broke in your AI pipeline.

### 3. Submit a Pull Request
We welcome PRs for:
- Bug fixes
- New validation types
- SDK improvements
- Documentation updates
- New analytics endpoints

## Getting Started
```bash
# Clone the repo
git clone https://github.com/eugene001dayne/iron-thread.git
cd iron-thread

# Install dependencies
pip install fastapi uvicorn pydantic openai python-dotenv httpx

# Set up environment
cp .env.example .env
# Add your Supabase credentials to .env

# Run locally
python -m uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` to see all endpoints.

## Project Structure
```
iron-thread/
├── main.py              # FastAPI backend — all endpoints live here
├── sdk/
│   ├── ironthread/      # Python SDK
│   └── iron-thread-js/  # JavaScript SDK
├── .env.example         # Environment variable template
├── Procfile             # Railway deployment config
├── requirements.txt     # Python dependencies
└── README.md
```

## Code Style

- Keep it simple and readable
- Every endpoint should have a clear docstring
- New features need at least one test case
- No breaking changes to existing endpoints without discussion

## SDK Contributions

**Python SDK** lives in `sdk/ironthread/`
**JavaScript SDK** lives in `sdk/iron-thread-js/`

When updating SDKs:
- Bump the version in `pyproject.toml` or `package.json`
- Update the README in the sdk folder
- Test against the live API before submitting

## Commit Message Format
```
feat: add new analytics endpoint
fix: handle empty schema definition
docs: update README with new examples
refactor: simplify validation logic
```

## Community

- Be respectful
- Be constructive
- Help others who open issues

## Roadmap

Want to work on something meaningful? 
These are actively needed:

- [ ] AI auto-correction loop (Anthropic + OpenAI)
- [ ] Webhook alerts on validation failure
- [ ] Per-user API keys
- [ ] JavaScript SDK improvements
- [ ] More validation types (regex, range, enum)
- [ ] Batch validation endpoint

Pick one, open an issue, let's talk.

---

Part of the Thread Suite — Iron-Thread · Test-Thread · Prompt-Thread

Built by Eugene Dayne Mawuli