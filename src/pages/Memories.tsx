import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAsync } from '../lib/useAsync'
import { api, type Memory } from '../lib/api'
import { Dialog, Pager, Panel, SearchBox, StateRow, Table, TD, Th } from '../components/ui'
import { Tabs } from '../components/ui/tabs'
import { RowActions } from '../components/ui/row-actions'
import { Checkbox } from '../components/ui/checkbox'
import { Button } from '../components/ui/button'
import { useProject, useT, useToast, useLang } from '../lib/store'
import { errText } from '../lib/i18n'

/** 标签：类型值 + i18n 词条 */
const TABS = [
  { type: 'text_mem', label: 'memory.tab.text_mem' },
  { type: 'pref_mem', label: 'memory.tab.pref_mem' },
  { type: 'event_mem', label: 'memory.tab.event_mem' },
  { type: 'profile_mem', label: 'memory.tab.profile_mem' },
  { type: 'skill_mem', label: 'memory.tab.skill_mem' },
  { type: 'tool_mem', label: 'memory.tab.tool_mem' },
] as const

/** 批量删除按钮。没选中任何行时是灰的、不可点 */
const BTN_BATCH_ON =
  'inline-flex items-center h-8 px-3 text-xs font-medium rounded-lg border border-danger/40 bg-danger-soft text-danger hover:bg-danger-soft transition-colors cursor-pointer shadow-2xs'
const BTN_BATCH_OFF =
  'inline-flex items-center h-8 px-3 text-xs font-medium rounded-lg border border-line bg-surface-muted/50 text-ink-faint cursor-not-allowed'

export function Memories() {
  const t = useT()
  const { lang } = useLang()
  const toast = useToast()
  const { currentProjectId, ready } = useProject()
  const [tab, setTab] = useState<(typeof TABS)[number]['type']>(TABS[0].type)
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState('')
  const [q, setQ] = useState('')
  const [tick, setTick] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null)
  /** 详情弹窗。`null` = 关着。点「查看详情」时才按 id 取那**一条**（不是把列表整页拿来用）。 */
  const [detail, setDetail] = useState<{ loading: boolean; error: string; memory: Memory | null } | null>(null)

  const pageSize = 10

  const { data, state, error } = useAsync(
    () =>
      api.memory.list({
        projectId: currentProjectId,
        memoryDetailType: tab,
        pageNum: page,
        pageSize,
        memSearchContent: q,
      }),
    [currentProjectId, tab, page, q, tick],
    // 字典没回来之前 `currentProjectId` 是空串，发出去必被 BFF 拒（40000 未知项目），
    // 页面会先闪一段「请求失败」再打第二遍
    { skip: !ready },
  )
  const rows = useMemo(() => data?.memListItemResponseList ?? [], [data])
  const total = data?.total ?? 0

  /** 标签上的条数：每种类型各取一次 total，只取 1 条 */
  useEffect(() => {
    if (!currentProjectId) return
    let alive = true
    Promise.all(
      TABS.map((x) =>
        api.memory
          .list({ projectId: currentProjectId, memoryDetailType: x.type, pageNum: 1, pageSize: 1 })
          .then((r) => [x.type, r.total] as const)
          .catch(() => [x.type, 0] as const),
      ),
    ).then((pairs) => {
      if (alive) setCounts(Object.fromEntries(pairs))
    })
    return () => {
      alive = false
    }
  }, [currentProjectId, tick])

  const doDelete = useCallback(
    async (ids: string[]) => {
      setPendingDelete(null)
      try {
        await api.memory.remove(ids, tab)
        toast(t('memory.deleteDone')(ids.length))
        setTick((x) => x + 1)
      } catch (e) {
        toast(errText(lang, e), 'err')
      }
    },
    [tab, t, toast, lang],
  )

  /** 取单条详情。
   *
   *  ⚠️ 按 id 单取，**不要**改成「从当前页的 rows 里找」：上游的列表接口走白名单投影，
   *  本来就没有详情需要的全部字段；而且列表是分页的，翻页后当前页的 rows 就换了。
   *  BFF 的 `memory/detail` 走 `GET /product/get_memory/{id}`，只取一条。 */
  const openDetail = useCallback(
    async (memoryId: string) => {
      setDetail({ loading: true, error: '', memory: null })
      try {
        const m = await api.memory.detail(memoryId, tab)
        setDetail({ loading: false, error: '', memory: m })
      } catch (e) {
        setDetail({ loading: false, error: errText(lang, e), memory: null })
      }
    },
    [tab, lang],
  )

  const showSkillName = tab === 'skill_mem'
  /** 「事件记忆」里混着两种类型（Context / InsightMemory），必须列出来才分得清。
   *  其余页签一个页签只有一种类型，再列一列是噪音。 */
  const showMemoryType = tab === 'event_mem'
  const colCount = 4 + (showSkillName ? 1 : 0) + (showMemoryType ? 1 : 0) + 2

  /* 「用户记忆」标签上原来还有一列「画像模板 ID」（模板 id / 实例 id）。
   * 2026-10-19 去掉：这个部署的上游**不下发**模板 id（实测 110 条 UserMemory 里 0 条有
   * `template_id`），而实例 id 早先是从 `working_binding` 取的——那是 WorkingMemory 的
   * 血缘 id，多数还等于这条记忆自己的 id，等于在「画像模板 ID」底下把行 id 又印一遍。
   * 两处都取不到值，那一列在页面上就是一片 `-`。
   *
   * 详情抽屉里那段（`detail.memory.profileTemplateId && …`）**留着**：它自带判断，
   * 上游哪天真的下发模板 id 就会自己出现。 */

  /** 只认当前页还在的 id，翻页、换标签、重新取数后旧选中自动失效 */
  const liveSelected = useMemo(() => {
    const ids = new Set(rows.map((m) => m.memoryId))
    return selected.filter((id) => ids.has(id))
  }, [rows, selected])

  const allChecked = rows.length > 0 && liveSelected.length === rows.length
  const someChecked = liveSelected.length > 0 && !allChecked

  return (
    <>
      <div data-v-1df75f9b="" className="w-full h-full flex flex-col gap-y-4">
        <div className="flex justify-between items-center">
          <div className="flex-1 flex items-center gap-x-3">
            <h2 className="text-lg font-semibold text-ink leading-6">{t('memory.title')}</h2>
            <p className="text-xs text-ink-muted truncate max-w-xl">{t('memory.desc')}</p>
          </div>
          <div className="flex items-center gap-x-2">
            <button
              type="button"
              disabled={liveSelected.length === 0}
              className={liveSelected.length === 0 ? BTN_BATCH_OFF : BTN_BATCH_ON}
              onClick={() => setPendingDelete(liveSelected)}
            >
              {t('memory.action.batchDelete')}
            </button>
            <SearchBox
              value={draft}
              onChange={setDraft}
              onSubmit={() => {
                setQ(draft.trim())
                setPage(1)
              }}
              placeholder={t('memory.searchPlaceholder')}
            />
          </div>
        </div>

        <Tabs
          label={t('memory.title')}
          value={tab}
          onChange={(k) => {
            setTab(k)
            setPage(1)
          }}
          items={TABS.map((x) => ({ key: x.type, label: t(x.label), count: counts[x.type] ?? 0 }))}
        />

        <div className="flex-1 min-h-0 overflow-hidden">
          <div className="flex h-full min-h-0 flex-col gap-3">
            <Panel className="memory-list-table flex-1 min-h-0">
              <Table
                head={
                  <>
                    <Th>
                      <div className="relative items-start flex-row flex justify-center">
                        <div className="flex items-center h-5">
                          <Checkbox
                            checked={allChecked}
                            indeterminate={someChecked}
                            onCheckedChange={(v) => setSelected(v ? rows.map((m) => m.memoryId) : [])}
                          />
                        </div>
                      </div>
                    </Th>
                    <Th>{t('memory.col.createdAt')}</Th>
                    <Th>{t('memory.col.subjectType')}</Th>
                    <Th>{t('memory.col.subjectId')}</Th>
                    {showMemoryType && <Th>{t('memory.col.memoryType')}</Th>}
                    {showSkillName && <Th>{t('memory.col.skillName')}</Th>}
                    <Th>{t('memory.col.content')}</Th>
                    <Th>{t('memory.col.action')}</Th>
                  </>
                }
              >
                {state !== 'ready' && <StateRow colSpan={colCount} state={state} error={error} />}
                {state === 'ready' && rows.length === 0 && <StateRow colSpan={colCount} state="ready" />}
                {state === 'ready' &&
                  rows.map((m) => (
                    <tr key={m.memoryId} className="data-[selected=true]:bg-elevated/50">
                      <td data-pinned="false" className={TD}>
                        <div className="flex justify-center">
                          <Checkbox
                            checked={liveSelected.includes(m.memoryId)}
                            onCheckedChange={(v) =>
                              setSelected((prev) => (v ? [...prev, m.memoryId] : prev.filter((x) => x !== m.memoryId)))
                            }
                          />
                        </div>
                      </td>
                      <td data-pinned="false" className={TD}>
                        {m.createTime}
                      </td>
                      <td data-pinned="false" className={TD}>
                        {t(`memory.subjectType.${m.subjectType}` as 'memory.subjectType.user')}
                      </td>
                      <td data-pinned="false" className={TD}>
                        {m.externalUserId}
                      </td>
                      {showMemoryType && (
                        <td data-pinned="false" className={`${TD} whitespace-nowrap`}>
                          {m.memoryType ? t(`graph.type.${m.memoryType}` as 'graph.type.Other') : '-'}
                        </td>
                      )}
                      {showSkillName && (
                        <td data-pinned="false" className={`${TD} truncate`}>
                          {m.skillName ?? '-'}
                        </td>
                      )}
                      <td data-pinned="false" className={`${TD} max-w-[520px] truncate`}>
                        {m.memoryContent}
                      </td>
                      <td data-pinned="false" className={TD}>
                        <RowActions
                          actions={[
                            { label: t('memory.action.detail'), icon: 'i-lucide:eye', onClick: () => openDetail(m.memoryId) },
                            {
                              label: t('memory.action.delete'),
                              icon: 'i-lucide:trash-2',
                              tone: 'danger',
                              onClick: () => setPendingDelete([m.memoryId]),
                            },
                          ]}
                        />
                      </td>
                    </tr>
                  ))}
              </Table>
            </Panel>
            <Pager page={page} pageSize={pageSize} total={total} onPage={setPage} />
          </div>
        </div>
      </div>

      <Dialog
        open={!!pendingDelete}
        title={t('memory.action.deleteConfirmTitle')}
        onClose={() => setPendingDelete(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={() => pendingDelete && doDelete(pendingDelete)}>
              {t('common.confirm')}
            </Button>
          </>
        }
      >
        {t('memory.deleteConfirm')(pendingDelete?.length ?? 0)}
      </Dialog>

      <Dialog
        open={!!detail}
        title={t('memory.detailTitle')}
        onClose={() => setDetail(null)}
        footer={
          <Button variant="secondary" onClick={() => setDetail(null)}>
            {t('common.close')}
          </Button>
        }
      >
        {detail?.loading && <p className="text-sm text-ink-muted">{t('common.loading')}</p>}
        {detail?.error && <p className="text-sm text-warning">{detail.error}</p>}
        {detail?.memory && (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-ink-muted">{t('memory.col.content')}</dt>
            <dd className="text-ink-secondary whitespace-pre-wrap break-words">{detail.memory.memoryContent || '-'}</dd>
            <dt className="text-ink-muted">{t('memory.col.subjectType')}</dt>
            <dd className="text-ink-secondary">{t(`memory.subjectType.${detail.memory.subjectType}` as 'memory.subjectType.user')}</dd>
            <dt className="text-ink-muted">{t('memory.col.subjectId')}</dt>
            <dd className="text-ink-secondary break-all">{detail.memory.externalUserId || '-'}</dd>
            <dt className="text-ink-muted">{t('memory.col.createdAt')}</dt>
            <dd className="text-ink-secondary">{detail.memory.createTime || '-'}</dd>
            {detail.memory.memoryType && (
              <>
                <dt className="text-ink-muted">{t('memory.col.memoryType')}</dt>
                <dd className="text-ink-secondary">{t(`graph.type.${detail.memory.memoryType}` as 'graph.type.Other')}</dd>
              </>
            )}
            {detail.memory.profileTemplateId && (
              <>
                <dt className="text-ink-muted">{t('memory.col.profileTreeId')}</dt>
                <dd className="text-ink-secondary break-all">{detail.memory.profileTemplateId}</dd>
              </>
            )}
            {detail.memory.skillName && (
              <>
                <dt className="text-ink-muted">{t('memory.col.skillName')}</dt>
                <dd className="text-ink-secondary break-all">{detail.memory.skillName}</dd>
              </>
            )}
            <dt className="text-ink-muted">{t('memory.detailId')}</dt>
            <dd className="text-ink-secondary break-all font-mono text-xs">{detail.memory.memoryId}</dd>
          </dl>
        )}
      </Dialog>
    </>
  )
}
