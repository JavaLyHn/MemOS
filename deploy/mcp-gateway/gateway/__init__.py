"""MCP 网关 — 把自部署的记忆服务以 MCP 暴露给内网其他使用者。

设计要点
========

1. 工具集对齐上游云服务的 MCP 实现中本部署能映射的部分。
   云版共 10 个工具，其中 5 个是 knowledgebase 相关（``/create/knowledgebase``、
   ``/add|get|delete/knowledgebase-file``、``/delete/knowledgebase``），本部署的
   29 条路由里没有任何对应端点，故不提供。剩下 5 个逐一对应：

   ====================  =======================  ==========================
   本网关工具             云版端点                  本部署端点
   ====================  =======================  ==========================
   add_message            /add/message             /product/add
   search_memory          /search/memory           /product/search
   delete_memory          /delete/memory           /product/delete_memory
   add_feedback           /add/feedback            /product/feedback
   get_user_profile       /get/memory              /product/get_memory
   ====================  =======================  ==========================

   名称、参数、返回结构都向云版看齐，调用方将来切云版时提示词和配置几乎不用改。

2. 多租户：调用方持 Bearer token，服务端持有 token -> user_id 的映射表。
   ``user_id`` / cube 永不作为工具参数出现 —— 模型既看不到也传不了，
   因此不存在「模型把记忆写到别人名下」的可能。这条对所有接入方一致。

3. 返回结构对齐云版：``memory_detail_list`` / ``preference_detail_list`` /
   ``tool_memory_detail_list``，字段名与云版一致（``memory_key`` /
   ``memory_value`` / ``preference`` / ``preference_type`` / ``tool_value`` /
   ``relativity``）。

4. 本部署的已知坑在这里一并处理（前一份桥接实测踩过的）：

   - 搜索会返回**已软删除**的记录（``status=deleted``，向量清理滞后）→ 过滤；
   - ``top_k`` 按桶生效（text/pref/tool/skill 各取 k）、不全局排序
     → 摊平后按 ``relativity`` 排序再截断；
   - ``delete_memory`` 只能传 ``memory_ids``，带上 ``user_id`` 会被判成
     「两个删除模式」→ **HTTP 200 + data.status="failure" 静默失败**；
   - ``POST /product/get_memory_by_ids`` 服务端返回空 → 循环调单条 GET。

5. **删除前必须自己校验归属。** 本部署的 ``/product/delete_memory`` 只认
   ``memory_ids``、不校验 owner —— 只要知道 id 就能删掉别人的记忆
   （实测：请求里不带 user_id 也能删成功）。因此 ``delete_memory`` 在真正删除
   之前会逐条查 owner，发现任何一条不属于当前调用方就**整批拒绝**。

环境变量
========

``MEMOS_API_BASE_URL``   后端地址，默认 ``http://localhost:8000``
``MEMOS_TENANTS``        token -> user_id 映射，两种写法皆可：
                         JSON: ``{"tok-a": {"user_id": "alice"}, ...}``
                         紧凑: ``tok-a:alice,tok-b:bob``
``MEMOS_ALLOWED_CUBES``  可选，cube 白名单（逗号分隔）；默认每个租户只用自己的 user_id 当 cube
``MEMOS_TIMEOUT``        单次 REST 调用超时秒数，默认 120
``MEMOS_HOST`` / ``MEMOS_PORT``  HTTP 监听地址，默认 ``0.0.0.0:8002``

运行
====

    python3 memos_gateway.py                     # Streamable HTTP（默认）
    python3 memos_gateway.py --transport stdio   # 本地 stdio 调试
"""
