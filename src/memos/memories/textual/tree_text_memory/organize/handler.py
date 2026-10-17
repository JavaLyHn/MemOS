import json
import re

from datetime import datetime

from dateutil import parser

from memos.embedders.base import BaseEmbedder
from memos.graph_dbs.base import BaseGraphDB
from memos.llms.base import BaseLLM
from memos.log import get_logger, preview_text
from memos.memories.textual.item import TextualMemoryItem, TreeNodeTextualMemoryMetadata
from memos.templates.tree_reorganize_prompts import (
    MEMORY_RELATION_DETECTOR_PROMPT,
    MEMORY_RELATION_RESOLVER_PROMPT,
)


logger = get_logger(__name__)

# 融合结果的长度上限。LLM 的输出长度不受控，超过这个量级的不可能是"一条记忆"。
MAX_RESOLVED_MEMORY_CHARS = 8192


def _relation_text(item) -> str:
    """判重/融合用文本：偏好类记忆取 metadata.preference（抽象偏好本身），其余取 memory 叙述。

    原实现一律用 memory 叙述（含 URL/时间戳等任务实例细节），导致"同一偏好、不同任务实例"
    被 LLM 判为 independent，去重失效——同一偏好可堆积上百份副本。
    """
    pref = getattr(getattr(item, "metadata", None), "preference", None)
    if isinstance(pref, str) and pref.strip():
        return pref.strip()
    return item.memory


class NodeHandler:
    EMBEDDING_THRESHOLD: float = 0.8  # Threshold for embedding similarity to consider conflict

    def __init__(self, graph_store: BaseGraphDB, llm: BaseLLM, embedder: BaseEmbedder):
        self.graph_store = graph_store
        self.llm = llm
        self.embedder = embedder

    def detect(self, memory, top_k: int = 5, scope=None, user_name: str | None = None):
        # 1. Search for similar memories based on embedding
        embedding = memory.metadata.embedding
        embedding_candidates_info = self.graph_store.search_by_embedding(
            embedding,
            top_k=top_k,
            scope=scope,
            # 只拿 activated 作候选：归档节点（含已被合并掉的、以及"出生即归档"的合并产物）
            # 若仍参与判重，会把新写入的记忆再并进一个归档节点，形成链式重合并。
            status="activated",
            threshold=self.EMBEDDING_THRESHOLD,
            user_name=user_name,
        )
        # 2. Filter based on similarity threshold
        embedding_candidates_ids = [
            info["id"] for info in embedding_candidates_info if info["id"] != memory.id
        ]
        # 3. Judge conflicts using LLM
        embedding_candidates = self.graph_store.get_nodes(
            embedding_candidates_ids, user_name=user_name
        )
        detected_relationships = []
        for embedding_candidate in embedding_candidates:
            embedding_candidate = TextualMemoryItem.from_dict(embedding_candidate)
            prompt = [
                {
                    "role": "user",
                    "content": MEMORY_RELATION_DETECTOR_PROMPT.format(
                        statement_1=_relation_text(memory),
                        statement_2=_relation_text(embedding_candidate),
                    ),
                }
            ]
            result = self.llm.generate(prompt).strip()
            if result == "contradictory":
                logger.info(
                    f'detected "{_relation_text(memory)}" <==CONFLICT==> "{_relation_text(embedding_candidate)}"'
                )
                detected_relationships.append([memory, embedding_candidate, "contradictory"])
            elif result == "redundant":
                logger.info(
                    f'detected "{_relation_text(memory)}" <==REDUNDANT==> "{_relation_text(embedding_candidate)}"'
                )
                detected_relationships.append([memory, embedding_candidate, "redundant"])
            elif result == "independent":
                pass
            else:
                pass
        return detected_relationships

    def resolve(
        self,
        memory_a: TextualMemoryItem,
        memory_b: TextualMemoryItem,
        relation,
        user_name: str | None = None,
    ) -> None:
        """
        Resolve detected conflicts between two memory items using LLM fusion.
        Args:
            memory_a: The first conflicting memory item.
            memory_b: The second conflicting memory item.
            relation: relation
            user_name: Optional user name for multi-tenant isolation.
        Returns:
            A fused TextualMemoryItem representing the resolved memory.
        """

        # ———————————— 1. LLM generate fused memory ————————————
        metadata_for_resolve = ["key", "background", "confidence", "updated_at"]
        metadata_1 = memory_a.metadata.model_dump_json(include=metadata_for_resolve)
        metadata_2 = memory_b.metadata.model_dump_json(include=metadata_for_resolve)
        prompt = [
            {
                "role": "user",
                "content": MEMORY_RELATION_RESOLVER_PROMPT.format(
                    relation=relation,
                    statement_1=_relation_text(memory_a),
                    metadata_1=metadata_1,
                    statement_2=_relation_text(memory_b),
                    metadata_2=metadata_2,
                ),
            },
        ]
        response = self.llm.generate(prompt).strip()

        # ———————————— 2. Parse the response ————————————
        try:
            matched = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
            answer = matched.group(1).strip() if matched else ""

            # —————— 2.1 Can't resolve conflict, hard update by comparing timestamp ————
            # 三种情况都按"解不出来"处理，退回按时间戳硬更新：
            #   ① 没有 <answer> 标签（原实现这里会 AttributeError：re.search 返回 None，
            #      而 except 只接 JSONDecodeError，等于没接住）；
            #   ② 回答为空——原实现会走进下面的 else，拿空串当融合结果覆盖 keeper，把正文清掉；
            #   ③ 回答长到不可能是"一条记忆"。这不是假想：实测有一次 LLM 返回了约 173 MB 的
            #      反斜杠，原实现把它原样写进 merged_memory，一条日志记录就是 173 MB（日志文件
            #      因此涨到 176 MB），并且准备把这个体积的东西当记忆写进图库。
            # 上限 8192 字符，与 MOS_MAX_TOKENS 同量级；正常融合结果是几十到几百字符。
            if (
                not answer
                or len(answer) > MAX_RESOLVED_MEMORY_CHARS
                or (len(answer) <= 10 and "no" in answer.lower())
            ):
                logger.warning(
                    f"{relation} between {memory_a.id} and {memory_b.id} could not be resolved. "
                    f"answer_chars={len(answer)}"
                )
                self._hard_update(memory_a, memory_b, user_name=user_name)
            # —————— 2.2 Conflict resolved, update metadata and memory ————
            else:
                fixed_metadata = self._merge_metadata(answer, memory_a.metadata, memory_b.metadata)
                merged_memory = TextualMemoryItem(memory=answer, metadata=fixed_metadata)
                logger.info(f"Resolved result: {preview_text(merged_memory)}")
                self._resolve_in_graph(memory_a, memory_b, merged_memory, user_name=user_name)
        except json.decoder.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {preview_text(response, 500)}")

    def _hard_update(
        self,
        memory_a: TextualMemoryItem,
        memory_b: TextualMemoryItem,
        user_name: str | None = None,
    ):
        """
        Hard update: compare updated_at, keep the newer one, overwrite the older one's metadata.
        """
        time_a = parser.isoparse(memory_a.metadata.updated_at)
        time_b = parser.isoparse(memory_b.metadata.updated_at)

        newer_mem = memory_a if time_a >= time_b else memory_b
        older_mem = memory_b if time_a >= time_b else memory_a

        self.graph_store.delete_node(older_mem.id, user_name=user_name)
        logger.warning(
            f"Delete older memory {older_mem.id}: <{older_mem.memory}> due to conflict with {newer_mem.id}: <{newer_mem.memory}>"
        )

    def _resolve_in_graph(
        self,
        conflict_a: TextualMemoryItem,
        conflict_b: TextualMemoryItem,
        merged: TextualMemoryItem,
        user_name: str | None = None,
    ):
        # 就地合并：把"较新的一方"（conflict_a，本次新写入的节点）原地升级为融合结果，
        # 只归档较旧的一方（conflict_b）。
        #
        # 原实现每次合并都新建一个节点，并把双方的边全部复制到新节点上。这带来两个后果：
        #   ① 同一批里多条并行合并会各自产出"兄弟"新节点，同一偏好永远收敛不到一条；
        #   ② 复制 MERGED_TO 边让合并关系变成多叉并成环（实测 8,974 条偏好产出 1,898 个
        #      合并产物、37,566 条 MERGED_TO、56 个环、最大环 862 节点）。
        # add_node 用的是 MERGE，传同一个 id 就是原地更新（neo4j 与 qdrant 一并覆盖）。
        keeper, loser = conflict_a, conflict_b

        self.graph_store.add_node(
            keeper.id,
            merged.memory,
            merged.metadata.model_dump(exclude_none=True),
            user_name=user_name,
        )

        # 只继承非 MERGED_TO 的边（如 PARENT 层级），避免合并关系自我繁殖。
        for edge in self.graph_store.get_edges(
            loser.id, type="ANY", direction="ANY", user_name=user_name
        ):
            if edge["type"] == "MERGED_TO":
                continue
            new_from = keeper.id if edge["from"] == loser.id else edge["from"]
            new_to = keeper.id if edge["to"] == loser.id else edge["to"]
            if new_from == new_to:
                continue
            if not self.graph_store.edge_exists(
                new_from, new_to, edge["type"], direction="ANY", user_name=user_name
            ):
                self.graph_store.add_edge(new_from, new_to, edge["type"], user_name=user_name)

        self.graph_store.update_node(loser.id, {"status": "archived"}, user_name=user_name)
        # update_node 只改 neo4j 节点，不同步 qdrant payload；而检索侧按 payload.status 过滤，
        # 不同步会让刚归档的节点继续"幽灵激活"进入召回。实测活跃租户每天累积约 500 条，
        # 与存量 keeper（490 条）同量级，等于候选池一半是幽灵。外部巡检只是兜底，
        # 这里就地闭环。
        _vec_db = getattr(self.graph_store, "vec_db", None)
        if _vec_db is not None:
            try:
                _vec_db.update(
                    loser.id,
                    {"id": loser.id, "vector": None, "payload": {"status": "archived"}},
                )
            except Exception as e:  # a vector-store hiccup must not undo the merge
                logger.warning(f"[VecDB] status sync failed for {loser.id}: {e}")
        self.graph_store.add_edge(loser.id, keeper.id, type="MERGED_TO", user_name=user_name)
        logger.debug(f"Merged {loser.id} into {keeper.id} in place.")

    def _merge_metadata(
        self,
        memory: str,
        metadata_a: TreeNodeTextualMemoryMetadata,
        metadata_b: TreeNodeTextualMemoryMetadata,
    ) -> TreeNodeTextualMemoryMetadata:
        metadata_1 = metadata_a.model_dump()
        metadata_2 = metadata_b.model_dump()
        merged_metadata = {
            "sources": (metadata_1["sources"] or []) + (metadata_2["sources"] or []),
            "embedding": self.embedder.embed([memory])[0],
            "update_at": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat(),
        }
        # 注意：不要把 status 写死成 activated。就地合并时产物就是 conflict_a 本身，
        # 状态应当继承它自己的状态；调用方（handle_add）已保证参与合并的节点是 activated。
        for key in metadata_1:
            if key in merged_metadata:
                continue
            merged_metadata[key] = (
                metadata_1[key] if metadata_1[key] is not None else metadata_2[key]
            )
        return TreeNodeTextualMemoryMetadata.model_validate(merged_metadata)
