"""
Specification for output validation. Imported from `main` on purpose: it must be the validator
the app actually uses. Section A passed with the old hand-written validator; section B is what
it got wrong (or silently ignored).
"""
import time

import pytest

from main import validate_against_schema as check


def ok(data, schema):
    return check(data, schema) == []


def bad(data, schema):
    return check(data, schema) != []


# ---- A) behaviour and wording users already depend on -------------------------------------------

INVOICE = {"type": "object", "required": ["amount"], "properties": {"amount": {"type": "number"}}}


def test_a_valid_document_passes():
    assert ok({"amount": 5}, INVOICE)


def test_a_missing_required_field_message():
    assert check({}, INVOICE) == ["Missing required field: 'amount'"]


def test_a_wrong_type_message():
    assert check({"amount": "x"}, INVOICE) == ["Field 'amount' must be a number, got str"]


def test_a_string_and_numeric_and_enum_and_array_messages():
    s = {"properties": {
        "name": {"type": "string", "minLength": 3, "maxLength": 5},
        "age": {"type": "integer", "minimum": 18, "maximum": 65},
        "tier": {"enum": ["a", "b"]},
        "tags": {"type": "array", "minItems": 2, "maxItems": 3},
    }}
    assert check({"name": "ab"}, s) == ["Field 'name' length 2 is below minimum 3"]
    assert check({"name": "abcdef"}, s) == ["Field 'name' length 6 exceeds maximum 5"]
    assert check({"age": 3}, s) == ["Field 'age' value 3 is below minimum 18"]
    assert check({"age": 99}, s) == ["Field 'age' value 99 exceeds maximum 65"]
    assert check({"tier": "z"}, s) == ["Field 'tier' value 'z' is not in allowed enum ['a', 'b']"]
    assert check({"tags": [1]}, s) == ["Field 'tags' has 1 items, minimum is 2"]
    assert check({"tags": [1, 2, 3, 4]}, s) == ["Field 'tags' has 4 items, maximum is 3"]


def test_a_nested_object_uses_a_dotted_path():
    s = {"properties": {"address": {"type": "object", "properties": {"city": {"type": "string"}}}}}
    assert check({"address": {"city": 5}}, s) == ["Field 'address.city' must be a string, got int"]


# ---- B) what the old validator got wrong --------------------------------------------------------

def test_b_top_level_type_is_checked():
    assert bad([1, 2], {"type": "object"})
    assert bad("text", {"type": "object"})


def test_b_booleans_are_not_numbers():
    s = {"properties": {"n": {"type": "integer"}, "m": {"type": "number"}}}
    assert bad({"n": True}, s)
    assert bad({"m": False}, s)


def test_b_integer_valued_floats_are_integers():
    assert ok({"n": 5.0}, {"properties": {"n": {"type": "integer"}}})
    assert bad({"n": 5.5}, {"properties": {"n": {"type": "integer"}}})


def test_b_type_lists_such_as_nullable_fields():
    s = {"properties": {"x": {"type": ["string", "null"]}}}
    assert ok({"x": None}, s) and ok({"x": "a"}, s)
    assert bad({"x": 5}, s)


def test_b_array_items_are_validated():
    s = {"properties": {"tags": {"type": "array", "items": {"type": "string"}}}}
    assert ok({"tags": ["a"]}, s)
    assert check({"tags": ["a", 2]}, s) == ["Field 'tags[1]' must be a string, got int"]


def test_b_additional_properties():
    s = {"properties": {"a": {}}, "additionalProperties": False}
    assert bad({"a": 1, "b": 2}, s)


def test_b_any_of_one_of_all_of():
    s = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert ok("x", s) and ok(3, s)
    assert bad(1.5, s)
    assert bad(1, {"oneOf": [{"type": "integer"}, {"minimum": 0}]})   # matches both -> invalid
    assert bad({"a": 1}, {"allOf": [{"required": ["a"]}, {"required": ["b"]}]})


def test_b_pattern_searches_anywhere_unless_anchored():
    s = {"properties": {"code": {"pattern": "[0-9]"}}}
    assert ok({"code": "abc1"}, s)
    assert bad({"code": "12a"}, {"properties": {"code": {"pattern": "^[0-9]+$"}}})


def test_b_constraints_inside_untyped_nested_objects():
    s = {"properties": {"addr": {"required": ["zip"]}}}
    assert bad({"addr": {}}, s)


def test_b_enum_does_not_confuse_true_with_one():
    assert bad({"x": True}, {"properties": {"x": {"enum": [1]}}})


def test_b_more_of_the_standard():
    assert bad({"n": 0}, {"properties": {"n": {"exclusiveMinimum": 0}}})
    assert bad({"n": 7}, {"properties": {"n": {"multipleOf": 5}}})
    assert bad({"k": "y"}, {"properties": {"k": {"const": "x"}}})
    assert bad([1, 1], {"uniqueItems": True})
    assert bad({"a": 1}, {"minProperties": 2})


def test_b_local_refs_work():
    s = {"$defs": {"pos": {"type": "integer", "minimum": 1}}, "properties": {"n": {"$ref": "#/$defs/pos"}}}
    assert ok({"n": 3}, s) and bad({"n": 0}, s)


def test_b_other_drafts_are_honoured_via_dollar_schema():
    s = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "required": ["a"]}
    assert ok({"a": 1}, s) and bad({}, s)


# ---- C) robustness ------------------------------------------------------------------------------

def test_c_an_invalid_schema_is_reported_not_crashed():
    result = check({"a": 1}, {"type": "strng"})
    assert len(result) == 1 and result[0].startswith("Schema is invalid:")


def test_c_remote_references_are_never_fetched():
    started = time.time()
    result = check({"a": 1}, {"$ref": "https://example.invalid/schema.json"})
    assert time.time() - started < 5            # no network wait
    assert result and "could not be evaluated" in result[0]


def test_c_errors_are_capped_and_messages_truncated():
    s = {"type": "array", "items": {"type": "string"}}
    result = check(list(range(500)), s)
    assert len(result) == 51 and result[-1].startswith("(+450 more problems")
    long_enum = {"enum": ["x" * 400]}
    assert max(len(m) for m in check("y", long_enum)) <= 400


def test_c_error_order_is_deterministic():
    s = {"properties": {"b": {"type": "string"}, "a": {"type": "string"}}}
    assert check({"b": 1, "a": 2}, s) == check({"a": 2, "b": 1}, s)


def test_c_schema_problem_helper():
    from validation import schema_problem
    assert schema_problem({"type": "object"}) is None
    assert schema_problem({"type": "strng"}) is not None
    assert schema_problem(["not", "a", "schema"]) is not None
