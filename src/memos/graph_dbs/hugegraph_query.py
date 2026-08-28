"""Formatting helpers for HugeGraph Gremlin queries."""

from textwrap import dedent


def format_gremlin_query(query: str) -> str:
    """Normalize a readable multiline Gremlin template for the SDK."""
    return "".join(line.strip() for line in dedent(query).splitlines() if line.strip())
