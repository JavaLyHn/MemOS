# HugeGraph 原型 Compose 启动

`docker/docker-compose.hugegraph.yml` 会启动：

- MemOS Python API
- Qdrant 向量数据库

HugeGraph 不包含在 Compose 中，需要提前准备好 HugeGraph Server、GraphSpace 和 graph，并通过根目录 `.env` 中的 `HUGEGRAPH_*` 变量连接。

## Python 依赖

HugeGraph provider 使用可选依赖组安装：

```bash
pip install "MemoryOS[hugegraph]"
```

该命令会直接安装 `hugegraph-python`（代码中的 import 名是 `pyhugegraph`）。`MemoryOS` 基础安装
不会隐式安装 HugeGraph SDK；这样不使用 HugeGraph 的部署不会被额外依赖和安装失败影响。代码中的
`require_python_package` 只负责在用户遗漏该依赖组时给出明确提示，不会在运行时修改环境或执行 pip。

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

首次启动前，HugeGraph 中必须已经存在对应 graph，例如 `socgs/mem_graph`，并执行
`docker/hugegraph-schema.groovy` 创建 MemOS provider 所需 schema。当前 provider 不会在运行时
修改 schema，`HUGEGRAPH_AUTO_CREATE_SCHEMA` 不是受支持的配置项。

`Memory` 顶点标签必须使用 `CUSTOMIZE_STRING` ID 策略。这样 HugeGraph 顶点 ID、MemOS memory
ID 与向量库 point ID 才是同一个 UUID。旧原型如果已用 `PRIMARY_KEY` 创建了 `Memory`，
`ifNotExist()` 不会改变已有标签；请先导出旧数据，在一个新 graph 上执行最新 schema 后再导入。
不要直接在原 graph 上覆盖 ID 策略。

当前 `hugegraph-python` 客户端固定使用 HTTP。`HUGEGRAPH_URL` 因此只接受 `http://`；需要
TLS 时，应在受信网络内通过反向代理终止 TLS，并让 MemOS 到 HugeGraph 的内部链路使用 HTTP。

## 网络地址规则

MemOS 容器内连接 Qdrant 使用 `qdrant:6333`，Compose 已自动注入。连接宿主机上的 HugeGraph 时，macOS/Windows 可使用 `host.docker.internal`；Linux 请将 `HUGEGRAPH_URL` 改成宿主机可达 IP，或使用实际的 HugeGraph 服务地址。

HugeGraph 的向量索引通过 `HUGEGRAPH_VECTOR_BACKEND` 选择，支持 `qdrant`（默认）、`milvus` 和
`none`。选择 Milvus 时设置 `MILVUS_URI`、`MILVUS_USER_NAME`、`MILVUS_PASSWORD`，并可用
`HUGEGRAPH_MILVUS_COLLECTION_NAME` 指定集合；选择 `none` 可只使用图存储，不初始化外部向量库。

默认 embedding 配置使用外部 OpenAI-compatible 服务。Qdrant 只负责存储和相似度检索，不负责生成 embedding。

要把 memmy-agent 自带 Desktop/Agent Runtime 接到该存储链路，参见
[memmy-agent Desktop 接入 MemOS HugeGraph](memmy-agent-hugegraph.md)。需要按步骤部署和验收时，
参见[带逐步流程图的本地部署指南](memmy-agent-memos-deployment.md)。
