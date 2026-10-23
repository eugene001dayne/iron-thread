from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REQUIRED = {"fastapi", "uvicorn", "pydantic", "python-dotenv", "httpx", "slowapi",
            "google-genai", "cryptography", "jsonschema"}


def test_requirements_txt_lists_exactly_the_expected_packages_one_per_line():
    text = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    names = {canonicalize_name(Requirement(line).name) for line in lines if line and not line.startswith("#")}
    wanted = {canonicalize_name(n) for n in REQUIRED}
    assert names >= wanted, f"missing, or glued onto another line: {sorted(wanted - names)}"
    assert names <= wanted, (f"unexpected entries {sorted(names - wanted)}; if you added a dependency "
                             "on purpose, add it to REQUIRED in this test")
