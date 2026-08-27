// MemOS HugeGraph Schema — run this once in Gremlin Console or HugeGraph Studio
// before starting the MemOS service.
//
// Usage (Gremlin Console):
//   :remote connect tinkerpop.server conf/remote.yaml
//   :remote console
//   :load hugegraph-schema.groovy
//
// Usage (REST API):
//   POST http://<host>:8080/apis/raft/leader/transfer  (if cluster)
//   POST http://<host>:8080/gremlin  with body: { "gremlin": "<content>" }

schema = hugegraph.schema()

// ── Property Keys ──────────────────────────────────────────────────────────
schema.propertyKey("id").asText().ifNotExist().create()
schema.propertyKey("memory").asText().ifNotExist().create()
schema.propertyKey("user_name").asText().ifNotExist().create()
schema.propertyKey("memory_type").asText().ifNotExist().create()
schema.propertyKey("status").asText().ifNotExist().create()
schema.propertyKey("created_at").asText().ifNotExist().create()
schema.propertyKey("updated_at").asText().ifNotExist().create()
schema.propertyKey("metadata_json").asText().ifNotExist().create()
schema.propertyKey("embedding_json").asText().ifNotExist().create()
schema.propertyKey("mem_cube_id").asText().ifNotExist().create()
schema.propertyKey("relation_type").asText().ifNotExist().create()
schema.propertyKey("delete_record_id").asText().ifNotExist().create()
schema.propertyKey("delete_time").asText().ifNotExist().create()

// ── Vertex Label ───────────────────────────────────────────────────────────
schema.vertexLabel("Memory")
    .useCustomizeStringId()
    .properties(
        "id", "memory", "user_name", "memory_type", "status",
        "created_at", "updated_at", "metadata_json", "embedding_json", "mem_cube_id",
        "delete_record_id", "delete_time"
    )
    .nullableKeys(
        "memory", "user_name", "memory_type", "status",
        "created_at", "updated_at", "metadata_json", "embedding_json", "mem_cube_id",
        "delete_record_id", "delete_time"
    )
    .ifNotExist()
    .create()

// ── Edge Label ─────────────────────────────────────────────────────────────
schema.edgeLabel("MEMORY_RELATION")
    .sourceLabel("Memory")
    .targetLabel("Memory")
    .properties("relation_type", "user_name")
    .nullableKeys("user_name")
    .ifNotExist()
    .create()

// ── Index Labels ───────────────────────────────────────────────────────────
schema.indexLabel("memoryByUserId")
    .onV("Memory")
    .by("user_name")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("memoryByMemoryType")
    .onV("Memory")
    .by("memory_type")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("memoryByStatus")
    .onV("Memory")
    .by("status")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("memoryByUserAndType")
    .onV("Memory")
    .by("user_name", "memory_type")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("memoryByUserAndStatus")
    .onV("Memory")
    .by("user_name", "status")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("memoryByMemCubeId")
    .onV("Memory")
    .by("mem_cube_id")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("relationByUser")
    .onE("MEMORY_RELATION")
    .by("user_name")
    .secondary()
    .ifNotExist()
    .create()

schema.indexLabel("memoryByText")
    .onV("Memory")
    .by("memory")
    .search()
    .ifNotExist()
    .create()
