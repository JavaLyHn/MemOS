export interface NavItem {
  label: string
  to: string
  icon?: string
  /** 选中态图标类名；缺省时沿用 icon */
  iconActive?: string
  /** 少数条目用的是位图而不是图标字体 */
  img?: string
}

export interface NavGroup {
  title: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: 'group.接入',
    items: [
      { label: 'nav.quickstart', to: '/cn/quickstart', icon: 'i-db-quickstart', iconActive: 'i-db-quickstart-fill' },
      { label: 'nav.apikeys', to: '/cn/apikeys', icon: 'i-db-key', iconActive: 'i-db-key-fill' },
    ],
  },
  {
    title: 'group.资源',
    items: [
      { label: 'nav.requests', to: '/cn/requests', icon: 'i-db-log', iconActive: 'i-db-log-fill' },
      { label: 'nav.knowledgeBase', to: '/cn/knowledgeBase', icon: 'i-db-knowledge-base' },
      { label: 'nav.memoryList', to: '/cn/memoryList', img: '/icons/memory-list.svg' },
      { label: 'nav.models', to: '/cn/models', icon: 'i-db-model', iconActive: 'i-db-model-fill' },
    ],
  },
  {
    title: 'group.设置',
    items: [
      { label: 'nav.profileTemplate', to: '/cn/profileTemplate', icon: 'i-db-project', iconActive: 'i-db-project-fill' },
      { label: 'nav.customExtraction', to: '/cn/customExtraction', icon: 'i-db-skill', iconActive: 'i-db-skill-fill' },
      { label: 'nav.usage', to: '/cn/usage', icon: 'i-db-chart' },
    ],
  },
]

/** 路径 → 面包屑文案 */
export const PAGE_TITLES: Record<string, string> = Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items.map((i) => [i.to, i.label])))

/** 属性树模板的新建 / 详情是子路由，先按前缀兜一层再退回精确匹配 */
export function pageTitleKey(pathname: string): string | undefined {
  if (pathname.startsWith('/cn/profileTemplate/')) return 'profile.detail.title'
  return PAGE_TITLES[pathname]
}
