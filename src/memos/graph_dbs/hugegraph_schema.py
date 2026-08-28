"""Typed schema vocabulary shared by the HugeGraph adapter and bootstrap script."""

from enum import Enum
from typing import Final


class HugeGraphVertexLabel(str, Enum):
    """Vertex labels owned by the MemOS HugeGraph integration."""

    MEMORY = "Memory"


class HugeGraphEdgeLabel(str, Enum):
    """Edge labels owned by the MemOS HugeGraph integration."""

    MEMORY_RELATION = "MEMORY_RELATION"


class HugeGraphProperty(str, Enum):
    """Fixed properties used by the MemOS HugeGraph schema."""

    ID = "id"
    MEMORY = "memory"
    RELATION_TYPE = "relation_type"
    MEMORY_TYPE = "memory_type"
    STATUS = "status"
    USER_NAME = "user_name"
    EMBEDDING = "embedding"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    MEM_CUBE_ID = "mem_cube_id"
    DELETE_RECORD_ID = "delete_record_id"
    DELETE_TIME = "delete_time"
    METADATA_JSON = "metadata_json"
    EMBEDDING_JSON = "embedding_json"


class HugeGraphMemoryStatus(str, Enum):
    """System statuses used by soft-delete and recovery operations."""

    ACTIVATED = "activated"
    DELETED = "deleted"


class HugeGraphMemoryType(str, Enum):
    """Memory types with special handling in graph recall."""

    WORKING = "WorkingMemory"
    REASONING = "reasoning"


class HugeGraphRelation(str, Enum):
    """Relations that have provider-level behavior."""

    FOLLOWS = "FOLLOWS"
    PARENT = "PARENT"


VERTEX_LABEL: Final[str] = HugeGraphVertexLabel.MEMORY.value
EDGE_LABEL: Final[str] = HugeGraphEdgeLabel.MEMORY_RELATION.value
RELATION_TYPE_KEY: Final[str] = HugeGraphProperty.RELATION_TYPE.value
ID_PROPERTY: Final[str] = HugeGraphProperty.ID.value
MEMORY_PROPERTY: Final[str] = HugeGraphProperty.MEMORY.value
USER_NAME_PROPERTY: Final[str] = HugeGraphProperty.USER_NAME.value
MEMORY_TYPE_PROPERTY: Final[str] = HugeGraphProperty.MEMORY_TYPE.value
STATUS_PROPERTY: Final[str] = HugeGraphProperty.STATUS.value
METADATA_JSON_PROPERTY: Final[str] = HugeGraphProperty.METADATA_JSON.value
EMBEDDING_JSON_PROPERTY: Final[str] = HugeGraphProperty.EMBEDDING_JSON.value

RESERVED_METADATA_FIELDS: Final[frozenset[str]] = frozenset(
    {
        HugeGraphProperty.MEMORY_TYPE.value,
        HugeGraphProperty.STATUS.value,
        HugeGraphProperty.USER_NAME.value,
        HugeGraphProperty.EMBEDDING.value,
        HugeGraphProperty.CREATED_AT.value,
        HugeGraphProperty.UPDATED_AT.value,
        HugeGraphProperty.MEM_CUBE_ID.value,
        HugeGraphProperty.DELETE_RECORD_ID.value,
        HugeGraphProperty.DELETE_TIME.value,
    }
)

EXPORT_BATCH_SIZE: Final[int] = 1000
