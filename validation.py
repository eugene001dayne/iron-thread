"""
JSON Schema validation for Iron-Thread.

Uses the standard `jsonschema` library (Draft 2020-12 by default; a schema's own "$schema"
selects another draft). The old hand-written validator silently ignored most of the standard.

validate_against_schema() keeps the old signature and the old wording for the common errors,
so existing SDK users and auto-correct prompts see familiar messages.
"""
import json
from functools import lru_cache

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

MAX_ERRORS = 50
MAX_MESSAGE_CHARS = 300

_TYPE_WORDS = {
    "string": "a string", "integer": "an integer", "number": "a number",
    "boolean": "a boolean", "array": "an array", "object": "an object", "null": "null",
}


@lru_cache(maxsize=256)
def _compile(schema_json):
    """Returns (validator, None) or (None, problem). Cached: checking a schema is not free."""
    schema = json.loads(schema_json)
    try:
        cls = validator_for(schema)
        cls.check_schema(schema)
        return cls(schema), None
    except SchemaError as e:
        return None, e.message
    except Exception as e:  # e.g. an unknown "$schema" URI
        return None, f"{type(e).__name__}: {e}"


def _key(schema):
    return json.dumps(schema, sort_keys=True, default=str)


def schema_problem(schema):
    """None if `schema` is a valid JSON Schema, otherwise a short explanation."""
    if not isinstance(schema, (dict, bool)):
        return "a schema must be a JSON object"
    return _compile(_key(schema))[1]


def _where(error):
    """Dotted path with [index] for arrays, e.g. items[0].price. Empty for the root."""
    out = ""
    for part in error.absolute_path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _short(text):
    return text if len(text) <= MAX_MESSAGE_CHARS else text[:MAX_MESSAGE_CHARS] + "..."


def _describe(error):
    path = _where(error)
    field = f"Field '{path}'" if path else "Output"
    kind, rule, value = error.validator, error.validator_value, error.instance

    if kind == "required":
        prefix = f"{path}." if path else ""
        return [f"Missing required field: '{prefix}{name}'" for name in rule if name not in value]
    if kind == "type":
        wanted = " or ".join(_TYPE_WORDS.get(t, t) for t in ([rule] if isinstance(rule, str) else rule))
        return [f"{field} must be {wanted}, got {type(value).__name__}"]
    if kind == "minLength":
        return [f"{field} length {len(value)} is below minimum {rule}"]
    if kind == "maxLength":
        return [f"{field} length {len(value)} exceeds maximum {rule}"]
    if kind == "pattern":
        return [f"{field} does not match pattern '{rule}'"]
    if kind == "minimum":
        return [f"{field} value {value} is below minimum {rule}"]
    if kind == "maximum":
        return [f"{field} value {value} exceeds maximum {rule}"]
    if kind == "enum":
        return [_short(f"{field} value '{value}' is not in allowed enum {rule}")]
    if kind == "minItems":
        return [f"{field} has {len(value)} items, minimum is {rule}"]
    if kind == "maxItems":
        return [f"{field} has {len(value)} items, maximum is {rule}"]
    return [_short(f"{field}: {error.message}")]


def validate_against_schema(data, schema, path=""):
    """Returns a list of human-readable problems; an empty list means the data is valid."""
    validator, problem = _compile(_key(schema))
    if validator is None:
        return [f"Schema is invalid: {problem}"]
    try:
        found = sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    except Exception as e:  # e.g. a $ref that cannot be resolved (remote references are never fetched)
        return [_short(f"Schema could not be evaluated: {type(e).__name__}: {e}")]
    messages = [m for error in found for m in _describe(error)]
    if len(messages) > MAX_ERRORS:
        extra = len(messages) - MAX_ERRORS
        messages = messages[:MAX_ERRORS] + [f"(+{extra} more problems not shown)"]
    return messages
