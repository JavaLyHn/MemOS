# HugeGraph 原型 Compose 启动

`docker/docker-compose.hugegraph.yml` 会启动：

- MemOS Python API
- Qdrant 向量数据库

HugeGraph 不包含在 Compose 中，需要提前准备好 HugeGraph Server、GraphSpace 和 graph，并通过根目录 `.env` 中的 `HUGEGRAPH_*` 变量连接。

## 启动

```bash
cp docker/.env.hugegraph.example .env
# 编辑 .env，填写 LLM、embedding、HugeGraph 凭据
cd docker
docker compose -f docker-compose.hugegraph.yml up --build
```

验证：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:6333/healthz
```

浏览器演示：

```text
http://127.0.0.1:8000/hugegraph-demo
```

首次启动前，HugeGraph 中必须已经存在对应 graph，例如 `socgs/mem_graph`。`HUGEGRAPH_AUTO_CREATE_SCHEMA=true` 只会创建 MemOS provider 所需 schema；确认完成后建议改成 `false`。

## 网络地址规则

MemOS 容器内连接 Qdrant 使用 `qdrant:6333`，Compose 已自动注入。连接宿主机上的 HugeGraph 时，macOS/Windows 可使用 `host.docker.internal`；Linux 请将 `HUGEGRAPH_URL` 改成宿主机可达 IP，或使用实际的 HugeGraph 服务地址。

默认 embedding 配置使用外部 OpenAI-compatible 服务。Qdrant 只负责存储和相似度检索，不负责生成 embedding。
