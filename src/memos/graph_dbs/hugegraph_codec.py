"""Serialization helpers for the MemOS HugeGraph schema."""

import json
import re

from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, TypeAlias

from memos.graph_dbs.hugegraph_schema import (
    EMBEDDING_JSON_PROPERTY,
    ID_PROPERTY,
    MEMORY_PROPERTY,
    MEMORY_TYPE_PROPERTY,
    METADATA_JSON_PROPERTY,
    RESERVED_METADATA_FIELDS,
    STATUS_PROPERTY,
    USER_NAME_PROPERTY,
)


GraphProperties: TypeAlias = dict[str, Any]
MemoryNode: TypeAlias = dict[str, Any]
FilterExpression: TypeAlias = dict[str, Any]
_VALID_PROPERTY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def now_iso() -> str:
    """Return a timezone-aware timestamp suitable for graph properties."""
    return datetime.now(UTC).isoformat()


def validate_property_name(value: str) -> str:
    """Validate a property name before it is interpolated into Gremlin."""
    if not _VALID_PROPERTY_NAME.fullmatch(value):
        raise ValueError(f"Invalid HugeGraph property name: {value!r}")
    return value


def pack_metadata(metadata: Mapping[str, Any]) -> str:
    """Serialize non-schema metadata into the single JSON property."""
    return json.dumps(
        {key: value for key, value in metadata.items() if key not in RESERVED_METADATA_FIELDS},
        ensure_ascii=False,
        default=str,
    )


def build_vertex_properties(
    node_id: str,
    memory: str,
    metadata: Mapping[str, Any],
    tenant: str,
) -> tuple[GraphProperties, list[float] | None, dict[str, Any]]:
    """Build graph properties and the normalized vector payload in one place."""
    normalized_metadata = dict(metadata)
    raw_embedding = normalized_metadata.pop("embedding", None)
    embedding = [float(value) for value in raw_embedding] if raw_embedding else None
    created_at = normalized_metadata.get("created_at", now_iso())
    updated_at = normalized_metadata.get("updated_at", now_iso())
    properties: GraphProperties = {
        ID_PROPERTY: node_id,
        MEMORY_PROPERTY: memory,
        USER_NAME_PROPERTY: tenant,
        MEMORY_TYPE_PROPERTY: normalized_metadata.get(MEMORY_TYPE_PROPERTY, ""),
        STATUS_PROPERTY: normalized_metadata.get(STATUS_PROPERTY, ""),
        "mem_cube_id": normalized_metadata.get("mem_cube_id", ""),
        "delete_record_id": normalized_metadata.get("delete_record_id", ""),
        "delete_time": normalized_metadata.get("delete_time", ""),
        "created_at": created_at,
        "updated_at": updated_at,
        METADATA_JSON_PROPERTY: pack_metadata(normalized_metadata),
        EMBEDDING_JSON_PROPERTY: json.dumps(embedding, ensure_ascii=False) if embedding else "",
    }
    return properties, embedding, normalized_metadata


def parse_valuemap(row: Mapping[str, Any]) -> GraphProperties:
    """Flatten HugeGraph's valueMap(true) response into plain properties."""
    result: GraphProperties = {}
    for key, value in row.items():
        if isinstance(value, list):
            result[key] = value[0] if len(value) == 1 else value
        else:
            result[key] = value
    return result


def unpack_node(props: Mapping[str, Any], include_embedding: bool = False) -> MemoryNode:
    """Convert stored HugeGraph properties into MemOS' node shape."""
    node_id = props.get(ID_PROPERTY, "")
    memory = props.get(MEMORY_PROPERTY, "")
    metadata: dict[str, Any] = {}
    with suppress(TypeError, json.JSONDecodeError):
        metadata.update(json.loads(props.get(METADATA_JSON_PROPERTY) or "{}"))
    for key in (
        MEMORY_TYPE_PROPERTY,
        STATUS_PROPERTY,
        USER_NAME_PROPERTY,
        "created_at",
        "updated_at",
        "mem_cube_id",
        "delete_record_id",
        "delete_time",
    ):
        if props.get(key):
            metadata[key] = props[key]
    if include_embedding and props.get(EMBEDDING_JSON_PROPERTY):
        with suppress(TypeError, json.JSONDecodeError):
            metadata["embedding"] = json.loads(props[EMBEDDING_JSON_PROPERTY])
    return {"id": str(node_id), "memory": str(memory), "metadata": metadata}


def matches_filter(record: Mapping[str, Any], expression: FilterExpression | None) -> bool:
    """Evaluate the filter shape shared by textual memory stores."""
    if not expression:
        return True
    if "and" in expression:
        clauses = expression["and"]
        return isinstance(clauses, list) and all(
            matches_filter(record, clause) for clause in clauses if isinstance(clause, dict)
        )
    if "or" in expression:
        clauses = expression["or"]
        return isinstance(clauses, list) and any(
            matches_filter(record, clause) for clause in clauses if isinstance(clause, dict)
        )

    for field, condition in expression.items():
        actual = record.get(field)
        if not isinstance(condition, dict):
            if actual != condition:
                return False
            continue
        for operator, expected in condition.items():
            if operator in {"eq", "="} and actual != expected:
                return False
            if operator in {"ne", "!="} and actual == expected:
                return False
            if operator == "in" and (
                not isinstance(expected, (list, tuple, set)) or actual not in expected
            ):
                return False
            if operator in {"nin", "not_in"} and isinstance(expected, (list, tuple, set)):
                if actual in expected:
                    return False
            elif operator in {"nin", "not_in"}:
                return False
            if operator == "contains":
                if isinstance(actual, (list, tuple, set)):
                    candidates = (
                        expected if isinstance(expected, (list, tuple, set)) else [expected]
                    )
                    if not set(actual) & set(candidates):
                        return False
                elif not isinstance(actual, str) or str(expected) not in actual:
                    return False
            if operator in {"starts_with", "ends_with"}:
                if not isinstance(actual, str) or not isinstance(expected, str):
                    return False
                if operator == "starts_with" and not actual.startswith(expected):
                    return False
                if operator == "ends_with" and not actual.endswith(expected):
                    return False
            if operator in {"gt", ">", "gte", ">=", "lt", "<", "lte", "<="}:
                try:
                    passed = {
                        "gt": actual > expected,
                        ">": actual > expected,
                        "gte": actual >= expected,
                        ">=": actual >= expected,
                        "lt": actual < expected,
                        "<": actual < expected,
                        "lte": actual <= expected,
                        "<=": actual <= expected,
                    }[operator]
                except TypeError:
                    return False
                if not passed:
                    return False
            if operator not in {
                "eq",
                "=",
                "ne",
                "!=",
                "in",
                "nin",
                "not_in",
                "contains",
                "starts_with",
                "ends_with",
                "gt",
                ">",
                "gte",
                ">=",
                "lt",
                "<",
                "lte",
                "<=",
            }:
                raise ValueError(f"Unsupported filter operator: {operator}")
    return True
