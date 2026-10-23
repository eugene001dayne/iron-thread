# Contributing to Iron-Thread

Thank you. Iron-Thread is built for developers who care about reliable AI systems, and every contribution
helps. This is the short version of how to help.

## Ways to contribute

- **Report a bug.** Say what you expected, what happened, the steps to reproduce it, and your Python version
  and operating system.
- **Suggest a feature.** The best suggestions come from real pain: tell us what broke in your AI pipeline.
- **Send a pull request.** Bug fixes, validation behaviour, documentation and tests are all welcome.

## Set up

```bash
git clone https://github.com/eugene001dayne/iron-thread.git
cd iron-thread
python -m venv .venv
source .venv/bin/activate          # Git Bash on Windows: source .venv/Scripts/activate
pip install -r requirements.txt pytest
pytest -q                          # the whole suite
python -m uvicorn main:app --reload
```

The interactive docs are at `http://localhost:8000/docs`. No accounts are needed. Copy `.env.example` to
`.env` only if you want to change a setting, and uncomment just the lines you need.

The README's *Development* section lists what each file does.

## Rules of the road

- **Every change comes with a test.** Run `pytest -q` before you open a pull request. CI runs the suite on
  Windows and Linux for Python 3.10 to 3.14, and a pull request needs to be green.
- **Be careful with anything that is signed or security-relevant** (`attestation.py`, `attest_store.py`,
  `attest_keys.py`, `verify_offline.py`, `auth.py`, `validation.py`). Changing what a receipt signs changes
  the `it-attest/1` format and needs a version bump and tests; please open an issue first.
- **Dependencies are added on purpose.** `requirements.txt` has one package per line, and
  `tests/test_requirements.py` checks it. If you add a dependency, add it to that test too.
- **Keep pull requests small and focused**, with small commits that each leave the tests passing.
- **No breaking changes to existing endpoints** without discussion.

## Reporting a security problem

Please do not describe a vulnerability in a public issue. Use the repository's **Security** tab and choose
"Report a vulnerability". If that is not available, open an issue that asks for a private way to reach the
maintainer, without any details of the problem.

## Commit messages

Start with one of `feat`, `fix`, `perf`, `docs`, `test`, `ci` or `chore`, then a short description:
   feat: add a new analytics endpoint
   fix: handle an empty schema definition
   perf: keep SQLite connections open per thread
   docs: update the quickstart


## SDKs

The Python SDK lives in `sdk/ironthread/` and the JavaScript SDK in `sdk/iron-thread-js/`. They are at version
0.3.0 and are behind the server: they do not yet send API keys or expose receipts and offline verification.
Bringing them up to date is a good contribution. When you change an SDK, bump the version in `pyproject.toml`
or `package.json` and update its README.

## Roadmap

These are actively wanted:

- [ ] Automatic anchoring of head hashes outside the operator's control
- [ ] A JavaScript verifier (it would also test our canonical JSON across languages)
- [ ] Updated SDKs: API keys, receipts, offline verification
- [ ] RFC 8785 canonical JSON
- [ ] An independent review of the cryptography
- [ ] Provider-agnostic auto-correction (today it uses Gemini only)

Pick one, open an issue, and let's talk.

---

Part of the Thread Suite. Built by Eugene Dayne Mawuli.