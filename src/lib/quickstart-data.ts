/** 快速开始页四种接入方式的内容。命令里的**地址**是真实值，直接可跑；
 *  **密钥一律是占位符**——见下面 `KEY_PLACEHOLDER` 的说明。 */

import type { Lang, TKey } from './i18n'
import type { ToolInfo } from './api'
import { LINKS } from './config'

/** 示例里密钥一律写成占位符，**不把真实密钥渲染进页面**。
 *
 *  ⚠️ 这里原来是把「当前项目的第一把密钥」查出来、直接嵌进每一段示例代码和提示词里，
 *  页面看着很贴心（复制即用），但代价是：一把**能用的密钥**被渲染在一个没有权限校验的
 *  静态页面上，任何能看到这个页面的人（截图、投屏、录屏）都顺手拿到了它，
 *  而页面本身**看不出来这是个秘密**。2026-10-19 用户指出后改成占位符：
 *  密钥去「接口密钥」页创建，示例里只留 `YOUR_API_KEY`。 */
const KEY_PLACEHOLDER = 'YOUR_API_KEY'

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
  /** 这一步在控制台里有对应页面时，渲染成一个跳转按钮而不是代码块。
   *  「获取 API Key」这一步就是这种：它要的是一把**用户自己的**密钥，
   *  页面能做的就是把人送到「接口密钥」。 */
  link?: { to: string; label: { zh: string; en: string } }
}

/** 接入方式的 id。
 *
 *  ⚠️ 刻意写成**联合类型**而不是 `string`：下面 `HINT_COPY` 是 `Record<AccessId, …>`，
 *  于是「加了一个页签、却忘了写它在浮层里的说明」会**编译不过**。
 *  这一页原来的毛病正是两处各写一份然后对不上——浮层里写着 Plugin，
 *  而实际上我们根本没有 Plugin 这种接入形式（2026-10-19 用户指出的）。 */
export type AccessId = 'mcp' | 'hermes' | 'prompt'

export interface AccessTab {
  id: AccessId
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

export function buildMcpConfig() {
  return `{
  "mcpServers": {
    "memory": {
      "type": "http",
      "url": "${LINKS.mcp}",
      "headers": { "Authorization": "Bearer ${KEY_PLACEHOLDER}" }
    }
  }
}`
}

/** Hermes 一条命令接入。
 *
 *  ⚠️ 这条命令**是从 Hermes 自己的 CLI 源码里读出来的**，不是照着别的客户端猜的：
 *  `hermes_cli/main.py` 里 `mcp add` 的参数是 `name` + `--url`，
 *  加完之后它会交互式问「是否需要鉴权」，回答是、把密钥粘进去即可，
 *  密钥落在 `~/.hermes/.env` 的 `MCP_<名字大写>_API_KEY`（见 `_env_key_for_server`）。
 *  用户原话是「HERMES 的话，可以直接 hermes add mcp 的命令」——真实子命令是
 *  `hermes mcp add <name> --url <url>`，别写成 `hermes add mcp`（那个不存在）。 */
const hermesCmd = `hermes mcp add memory --url ${LINKS.mcp}`

const buildPrompt = (tools: ToolInfo[]) => {
  const list = tools.length ? tools.map((x) => `${x.name}（${x.title}）`).join('、') : '若干工具'
  const n = tools.length || ''
  return `请帮我把记忆服务接入当前 Agent 的 MCP 配置。

服务地址：${LINKS.mcp}
鉴权方式：请求头 Authorization: Bearer ${KEY_PLACEHOLDER}

请完成：
1. 在 Agent 的 MCP 配置里新增一个名为 memory 的 http 类型服务，填上面的地址与鉴权头。
2. 重启 Agent 的 MCP 网关，确认连接成功。
3. 连上后应该能看到 ${n} 个工具（${list}）。
4. 调一次检索工具验证链路，返回空列表也是正常的（还没有记忆）。

如果我的客户端配置格式和上面不一样，请按它的格式改写，并告诉我改了哪个文件。`
}

/** 快速开始页提供的接入方式。
 *
 *  ⚠️ 2026-10-19 用户把这一页的「接入方式」逐条点掉了：**只提供 MCP、Hermes、
 *  让 Agent 自己配**三种。原来还有 Claude Code / cURL / JSON-RPC 三个页签、
 *  以及浮层里的 Plugin / CLI + Skill —— 那些一个都没提供，是原产品的残留。
 *  删页签比改文案重要：文案说错了只是误导，**摆一个页签就是在承诺它能用**。 */
export function buildTabs(facts: ServiceFacts): AccessTab[] {
  return [
    {
      id: 'mcp',
      label: 'MCP',
      icon: 'i-lucide:plug',
      head: bi('配置 MCP', 'Configure MCP'),
      docs: LINKS.docs,
      steps: [
        {
          n: '1',
          title: bi('获取 API Key', 'Get an API key'),
          desc: bi('在「接口密钥」页创建，或使用管理员发的那把', 'Create one on the API keys page, or use the token from your admin'),
          code: KEY_PLACEHOLDER,
          multiline: false,
          link: { to: '/cn/apikeys', label: bi('去创建密钥', 'Create a key') },
        },
        {
          n: '2',
          title: bi('配置 MCP Server', 'Add the MCP server'),
          desc: bi('把下面的配置加到你的 AI 工具的 MCP 设置里', 'Add this to the MCP settings of your AI tool'),
          code: buildMcpConfig(),
          multiline: true,
        },
      ],
    },
    {
      id: 'hermes',
      label: 'Hermes',
      icon: 'i-lucide:terminal',
      head: bi('接入 Hermes', 'Wire up Hermes'),
      docs: LINKS.docs,
      steps: [
        {
          n: '1',
          title: bi('获取 API Key', 'Get an API key'),
          code: KEY_PLACEHOLDER,
          multiline: false,
          link: { to: '/cn/apikeys', label: bi('去创建密钥', 'Create a key') },
        },
        {
          n: '2',
          title: bi('一条命令接入', 'One command'),
          desc: bi('按提示确认鉴权，再粘贴密钥。', 'Confirm auth when prompted, then paste the key.'),
          code: hermesCmd,
          multiline: true,
        },
      ],
    },
    {
      id: 'prompt',
      label: '让 Agent 自己配',
      labelEn: 'Let the agent do it',
      icon: 'i-lucide:sparkles',
      head: bi('', ''),
      docs: LINKS.docs,
      steps: [],
      prompt: bi(buildPrompt(facts.tools), buildPrompt(facts.tools)),
    },
  ]
}

export const tabLabel = (tab: AccessTab, lang: Lang) => (lang === 'en' && tab.labelEn ? tab.labelEn : tab.label)

/** 「选择哪种接入方式？」浮层里每一行的「适合场景 / 特点」。
 *
 *  ⚠️ 方式名**不写在这里**：它取自页签自己的 label（见 `AccessMethodHint` 的调用点），
 *  同一个名字只有一处维护。
 *
 *  ⚠️ 键是 `Record<AccessId, …>`：加了页签却忘了写说明，**编译期就会报错**。
 *  原来浮层里写死了三行 `Plugin / CLI + Skill / MCP`，其中两个我们都没提供
 *  （2026-10-19 用户指出「跟我们提供的接入方式还不太匹配」）。 */
export const HINT_COPY: Record<AccessId, { scene: TKey; feature: TKey }> = {
  mcp: { scene: 'quickstart.hint.mcp.scene', feature: 'quickstart.hint.mcp.feature' },
  hermes: { scene: 'quickstart.hint.hermes.scene', feature: 'quickstart.hint.hermes.feature' },
  prompt: { scene: 'quickstart.hint.prompt.scene', feature: 'quickstart.hint.prompt.feature' },
}
