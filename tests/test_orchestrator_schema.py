from itertools import combinations

from app.orchestrator import (
    ALWAYS_REQUIRED_AGENT2_FIELDS,
    OPTIONAL_AGENT2_FIELDS,
    _build_agent2_schema,
    _find_strict_schema_issues,
)


def test_build_agent2_schema_strict_for_all_optional_subsets():
    for size in range(len(OPTIONAL_AGENT2_FIELDS) + 1):
        for subset in combinations(OPTIONAL_AGENT2_FIELDS, size):
            schema = _build_agent2_schema(set(subset))
            issues = _find_strict_schema_issues(schema)
            assert issues == []
            required = set(schema["properties"]["bestekposten"]["items"]["required"])
            assert ALWAYS_REQUIRED_AGENT2_FIELDS.issubset(required)
            assert required == ALWAYS_REQUIRED_AGENT2_FIELDS | set(subset)
