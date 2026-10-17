# MemOS Dashboard

MemOS 记忆服务的 Web 控制台。

前端与后端的接口定义见 `openapi.json`（OpenAPI 3.1，37 条路径），后端地址由 `VITE_API_BASE` 指定。

## 快速开始

```bash
pnpm install
pnpm dev:all    # 同时起 mock 后端(5280) 与前端(5274)
```

打开 <http://localhost:5274/cn/apikeys>。

需要 Node 20+ 与 pnpm。仓库自带一个 mock 后端（`server/mock/`），用于本地开发。

其他命令：

```bash
pnpm mock       # 只起 mock 后端
pnpm dev        # 只起前端（/api 代理到 mock）
pnpm build      # 产物在 dist/
pnpm preview    # 预览构建产物，同样走代理
pnpm verify     # typecheck + lint + format:check + build
```

两个端口都用 `--strictPort`，被占用时直接报错，不会静默换端口。

## 页面与路由

| 页面 | 路由 | 数据来源 |
|---|---|---|
| 快速开始 | `/cn/quickstart` | `/api/meta` 的接入参数 |
| 接口密钥 | `/cn/apikeys` | 当前项目的密钥，增删查可用，复制走独立接口 |
| 调用日志 | `/cn/requests` | 分页 + 关键词搜索 + 事件类型筛选，点行看请求/响应详情 |
| 知识库 | `/cn/knowledgeBase` | 列表 |
| 记忆列表 | `/cn/memoryList` | 6 个记忆类型标签 + 分页 + 搜索 + 批量删除 |
| 模型列表 | `/cn/models` | 静态 JSON（`public/tech-config/`），**不走后端接口** |
| 属性树模板 | `/cn/profileTemplate` | 列表 / 新建 / 详情 |
| 自定义抽取 | `/cn/customExtraction` | Prompt 配置与快速调试两个标签 |
| 用量监控 | `/cn/usage` | 按天聚合的调用量与 token，图表 + 明细 |
| 接口文档 | `/cn/docs` | 服务地址、MCP 接入配置 |
| 关于 | `/cn/about` | 接口说明 |

未匹配的路径回落到接口密钥页。侧栏还有两个交互：**收起/展开**（记住选择）、**项目切换**（所有业务接口的 `projectId` 都跟着变）。

## 目录索引

| 想找什么 | 去哪里 |
|---|---|
| 后端要实现哪些接口 | `openapi.json` —— 接口的权威定义；任务书见 [#1](https://github.com/hugegraph/MemOS/issues/1) |
| 前端怎么调这些接口 | `src/lib/api.ts` —— 路径、请求体、返回类型 |
| mock 后端怎么实现的 | `server/mock/server.ts` —— 一张 `"方法 路径" → 处理函数` 的路由表 |
| 路由表 | `src/App.tsx` |
| 侧栏与导航结构 | `src/lib/nav.ts` |
| 中英文文案 | `src/lib/i18n.ts` |
| 全局状态（语言、项目、运行信息、Toast） | `src/lib/store.tsx` |
| 接口地址等外部配置 | `src/lib/config.ts` |
| 样式入口 | `src/index.css`（按顺序 `@import` 下面几张表） |
| 自己新写的工具类 | `src/styles/console-extra.css` |

```
src/
  components/   AppShell / Sidebar / TopBar / Icon / Logo / ui / ListPage
                / FilterPopover / AccessMethodHint
  pages/        11 个页面，一个页面一个文件
  lib/          api / config / i18n / store / nav / cls / useAsync / quickstart-data
  styles/       base.css（基础样式表）、theme-runtime.css（主题变量）、
                components.css（组件样式）、icons.css（图标字体）、
                console-extra.css（本项目新写的类）
public/         图标与品牌资源、tech-config/（模型清单静态文件）
server/mock/    data.ts（数据集）、store.ts（内存态 + 落盘）、server.ts（HTTP 路由表）
openapi.json    接口定义
```

## 接口定义

接口的权威定义是仓库根目录的 `openapi.json`（OpenAPI 3.1，37 条路径）；前端侧的路径、请求体与返回类型在 `src/lib/api.ts`。

几条容易踩的约定：

- **除少数 GET 外都是 POST + JSON body**，参数不放 query。
- **统一返回格式 `{ code, data, message }`**，`code === 0` 时前端取 `data`，非 0 时把 `message` 弹成提示。HTTP 状态码不参与判断。
- **分页参数叫 `pageNum` / `pageSize`**，从 1 开始。
- **列表响应的键各接口不同**：`records`（项目 / 密钥 / 知识库）、`logs`（调用日志）、`memListItemResponseList`（记忆）、`list`（属性树模板）。`api.ts` 如实透传，不做归一化，页面自己挑。
- **日志详情的 `requestBody` / `responseBody` 是 JSON 字符串**，前端要二次 parse。
- **密钥列表下发的是完整密钥**，前端自己截成 `前7位*******后8位` 展示；复制走 `keys/copy` 单独取。

校验 spec：

```bash
npx @redocly/cli lint openapi.json
```

### mock 后端是独立进程

`server/mock/` 是一个独立的 HTTP 服务（`pnpm mock`，默认 5280），实现的接口与后端一致，包括各接口不一样的列表键和返回格式。

mock 不挂在 Vite 中间件上，而是独立进程：挂在中间件上的话它只在 `pnpm dev` 里存在，构建产物部署出去没有后端，前端也不会走真实的 HTTP 调用链。

结构上也不写死：`data.ts` 是数据集，`store.ts` 管内存态与落盘（`.data/mock-db.json`，带 schema 版本），`server.ts` 只有一张路由表。加一个接口 = 在路由表里加一行。

## 环境变量

见 `.env.example`。三个都用 `VITE_` 前缀，构建时注入：

| 变量 | 作用 |
|---|---|
| `VITE_API_BASE` | 后端 origin。留空 = 同源，走 `/api` |
| `VITE_SERVICE_BASE` | 记忆服务对外地址，用于落地页/文档/快速开始展示 |
| `VITE_TECH_CONFIG_URL` | 模型清单的静态目录 |

`/api/meta` 返回的 `mode` 决定顶栏显示「真实数据」还是「示例数据」：mock 返回 `sample`，真实后端返回 `live`。

## 验证

```bash
pnpm verify      # typecheck + lint + format:check + build
pnpm typecheck   # 只跑类型检查
pnpm lint        # 只跑 ESLint
```

## 当前状态

后端接口尚未接入，页面数据来自 mock 后端；`pnpm verify` 全绿。后端要实现哪些接口见 [#1](https://github.com/hugegraph/MemOS/issues/1)。
