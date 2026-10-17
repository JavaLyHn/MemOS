/** 快速开始页四种接入方式的内容。命令里的地址与 token 都是真实值，直接可跑。 */

import type { Lang } from './i18n'
import type { ToolInfo } from './api'
import { LINKS } from './config'

/** 服务暴露的工具清单由 /api/meta 提供，示例命令据此生成，不写死在前端 */
export interface ServiceFacts {
  tools: ToolInfo[]
}

const bi = (zh: string, en: string) => ({ zh, en })

export interface Step {
  n: string
  title: { zh: string; en: string }
  desc?: { zh: string; en: string }
  code: string
  /** 多行代码用 <pre>，单行用 <code> */
  multiline: boolean
}

export interface AccessTab {
  id: string
  /** 归在哪张卡片下：Agent 接入 / 代码集成 */
  card: 'agent' | 'code'
  label: string
  /** 少数标签需要中英两版 */
  labelEn?: string
  icon: string
  head: { zh: string; en: string }
  docs: string
  steps: Step[]
  /** 「提示词」走另一套版式：一段可复制的提示词 */
  prompt?: { zh: string; en: string }
}

export function buildMcpConfig(apiKey: string) {
  return `{
  "mcpServers": {
    "memory": {
      "type": "http",
      "url": "${LINKS.mcp}",
      "headers": { "Authorization": "Bearer ${apiKey}" }
    }
  }
}`
}

const claudeCmd = `claude mcp add --transport http memory ${LINKS.mcp} -H "Authorization: Bearer <你的 API Key>"`

const curlCmd = `curl -s ${LINKS.mcp} \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -H 'Content-Type: application/json' \\
  -H 'Accept: application/json, text/event-stream' \\
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize",
       "params":{"protocolVersion":"2025-06-18","capabilities":{},
                 "clientInfo":{"name":"curl","version":"1"}}}'`

/** 挑一个「检索类」工具当示例；没有就退回第一个，再没有就用占位符 */
function pickExampleTool(tools: ToolInfo[]): string {
  const hit = tools.find((x) => /search|retriev|recall|query/i.test(x.name))
  return hit?.name ?? tools[0]?.name ?? 'YOUR_TOOL'
}

const jsonRpcCall = (apiKey: string, tool: string) => `curl -s ${LINKS.mcp} \\
  -H 'Authorization: Bearer ${apiKey}' \\
  -H 'Content-Type: application/json' \\
  -H 'Accept: application/json, text/event-stream' \\
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"${tool}",
                 "arguments":{"query":"用户偏好","top_k":5}}}'`

const buildPrompt = (apiKey: string, tools: ToolInfo[]) => {
  const list = tools.length ? tools.map((x) => `${x.name}（${x.title}）`).join('、') : '若干工具'
  const n = tools.length || ''
  return `请帮我把记忆服务接入当前 Agent 的 MCP 配置。

服务地址：${LINKS.mcp}
鉴权方式：请求头 Authorization: Bearer ${apiKey}

请完成：
1. 在 Agent 的 MCP 配置里新增一个名为 memory 的 http 类型服务，填上面的地址与鉴权头。
2. 重启 Agent 的 MCP 网关，确认连接成功。
3. 连上后应该能看到 ${n} 个工具（${list}）。
4. 调一次检索工具验证链路，返回空列表也是正常的（还没有记忆）。

如果我的客户端配置格式不同（如 .mcp.json、claude_desktop_config.json），
请按该格式改写，并告诉我改了哪个文件。`
}

export function buildTabs(apiKey: string, facts: ServiceFacts): AccessTab[] {
  const key = apiKey || 'YOUR_API_KEY'
  const tool = pickExampleTool(facts.tools)
  return [
    {
      id: 'mcp',
      card: 'agent',
      label: 'MCP',
      icon: 'i-lucide:plug',
      head: bi('配置 MCP', 'Configure MCP'),
      docs: LINKS.docs,
      steps: [
        {
          n: '1',
          title: bi('获取 API Key', 'Get an API key'),
          desc: bi('在「接口密钥」页创建，或使用管理员发的那把', 'Create one on the API keys page, or use the token from your admin'),
          code: key,
          multiline: false,
        },
        {
          n: '2',
          title: bi('配置 MCP Server', 'Add the MCP server'),
          desc: bi('把下面的配置加到你的 AI 工具的 MCP 设置里', 'Add this to the MCP settings of your AI tool'),
          code: buildMcpConfig(key),
          multiline: true,
        },
      ],
    },
    {
      id: 'claude',
      card: 'agent',
      label: 'Claude Code',
      icon: 'i-lucide:terminal',
      head: bi('接入 Claude Code', 'Wire up Claude Code'),
      docs: LINKS.docs,
      steps: [
        {
          n: '1',
          title: bi('获取 API Key', 'Get an API key'),
          code: key,
          multiline: false,
        },
        {
          n: '2',
          title: bi('一条命令接入', 'One command'),
          desc: bi('-H 指定鉴权头，token 放 Authorization', '-H sets the auth header; the token goes in Authorization'),
          code: claudeCmd,
          multiline: true,
        },
      ],
    },
    {
      id: 'curl',
      card: 'code',
      label: 'cURL',
      icon: 'i-lucide:code',
      head: bi('用 cURL 验证', 'Verify with cURL'),
      docs: LINKS.docs,
      steps: [
        {
          n: '1',
          title: bi('获取 API Key', 'Get an API key'),
          code: key,
          multiline: false,
        },
        {
          n: '2',
          title: bi('握手一次', 'Do a handshake'),
          desc: bi('把 YOUR_API_KEY 换成上面那把；返回 serverInfo 就算通了', 'Replace YOUR_API_KEY; a serverInfo response means it works'),
          code: curlCmd,
          multiline: true,
        },
      ],
    },
    {
      id: 'jsonrpc',
      card: 'code',
      label: 'JSON-RPC',
      icon: 'i-lucide:braces',
      head: bi('用 JSON-RPC 调用工具', 'Call a tool over JSON-RPC'),
      docs: LINKS.docs,
      steps: [
        {
          n: '1',
          title: bi('获取 API Key', 'Get an API key'),
          code: key,
          multiline: false,
        },
        {
          n: '2',
          title: bi('调用检索工具', 'Call the search tool'),
          desc: bi('记忆服务的每个能力都是一个 MCP 工具，用 tools/call 调即可', 'Every capability is an MCP tool; call it with tools/call'),
          code: jsonRpcCall(key, tool),
          multiline: true,
        },
      ],
    },
    {
      id: 'prompt',
      card: 'agent',
      label: '让 Agent 自己配',
      labelEn: 'Let the agent do it',
      icon: 'i-lucide:sparkles',
      head: bi('', ''),
      docs: LINKS.docs,
      steps: [],
      prompt: bi(buildPrompt(key, facts.tools), buildPrompt(key, facts.tools)),
    },
  ]
}

export const tabLabel = (tab: AccessTab, lang: Lang) => (lang === 'en' && tab.labelEn ? tab.labelEn : tab.label)

export const TRY_NOTE_KEYS = {
  items: [bi('第一次会话：', 'First session: '), bi('第二次会话（新启动）：', 'Second session (fresh start): ')],
}
