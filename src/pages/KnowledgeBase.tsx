import { api, type KnowledgeBase as KB } from '../lib/api'
import { ListPage } from '../components/ListPage'
import { useProject, useT } from '../lib/store'

export function KnowledgeBase() {
  const t = useT()
  const { currentProjectId, projects } = useProject()
  const nameOf = (id: string) => projects.find((p) => p.id === id)?.name ?? id

  return (
    <ListPage<KB>
      title={t('kb.title')}
      desc={t('kb.desc')}
      searchable
      rowKey={(k) => k.kbId}
      deps={[currentProjectId]}
      load={async (pageNum, pageSize, name) => {
        const res = await api.knowledgeBase.list(pageNum, pageSize, name, currentProjectId)
        return { items: res.records, total: res.total }
      }}
      cols={[
        { key: 'knowledgebaseName', label: t('kb.col.name'), render: (k) => k.knowledgebaseName },
        { key: 'desc', label: t('kb.col.desc'), render: (k) => k.knowledgebaseDescription || '-' },
        {
          key: 'projects',
          label: t('kb.col.projects'),
          render: (k) => (k.projectIds?.length ? k.projectIds.map(nameOf).join('、') : '-'),
        },
        {
          key: 'createTime',
          label: t('kb.col.createdAt'),
          render: (k) => String((k as unknown as Record<string, unknown>).createTime ?? '-'),
        },
      ]}
    />
  )
}
