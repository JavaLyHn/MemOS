import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAsync } from '../lib/useAsync'
import { api } from '../lib/api'
import { Dialog, Pager, Panel, StateRow, Table, TD, Th } from '../components/ui'
import { Icon } from '../components/Icon'
import { BTN_DIALOG_PRIMARY, BTN_DIALOG_SECONDARY, BTN_PAGER } from '../lib/cls'
import { useProject, useT, useToast } from '../lib/store'

/** 标签：类型值 + i18n 词条 */
const TABS = [
  { type: 'text_mem', label: 'memory.tab.text_mem' },
  { type: 'pref_mem', label: 'memory.tab.pref_mem' },
  { type: 'event_mem', label: 'memory.tab.event_mem' },
  { type: 'profile_mem', label: 'memory.tab.profile_mem' },
  { type: 'skill_mem', label: 'memory.tab.skill_mem' },
  { type: 'tool_mem', label: 'memory.tab.tool_mem' },
] as const

const PILL_BASE =
  'h-[32px] px-[10px] flex items-center justify-center text-[14px] font-medium cursor-pointer whitespace-nowrap rounded-[6px]'
const PILL_ACTIVE = `${PILL_BASE} bg-primary text-white shadow-sm`
const PILL_IDLE = `${PILL_BASE} text-[#6B7280] hover:text-primary hover:bg-gray-50`

/** 批量删除按钮。没选中任何行时是灰的、不可点 */
const BTN_BATCH_ON =
  'inline-flex items-center py-1.5 text-sm gap-1.5 ring-inset ring-accented hover:bg-elevated active:bg-elevated focus:outline-none focus-visible:ring-2 focus-visible:ring-inverted h-8 rounded-[6px] px-4 font-medium transition-all duration-200 border bg-white text-primary border-primary cursor-pointer'
const BTN_BATCH_OFF =
  'inline-flex items-center py-1.5 text-sm gap-1.5 ring-inset ring-accented focus:outline-none h-8 rounded-[6px] px-4 font-medium transition-all duration-200 border bg-white text-[#C0C4CC] border-[#E4E7ED] cursor-not-allowed ring-0'

const SEARCH_INPUT =
  'w-full border-0 appearance-none focus:outline-none transition-colors py-1.5 gap-1.5 bg-default ring ring-inset ring-accented focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary pe-9 h-8 rounded-[6px] px-3 text-[14px] text-[#314158] placeholder:text-[#90A1B9] outline-none'

const FILTER_BTN = `${BTN_PAGER} h-8 w-8 px-0 flex justify-center`

/** 操作列的三个动作，用 <span> 而不是按钮 */
const ACTION = 'cursor-pointer text-[14px] font-medium transition-all duration-200 hover:opacity-70'

function Checkbox({ checked, indeterminate, onChange }: { checked: boolean; indeterminate?: boolean; onChange: (v: boolean) => void }) {
  const state = indeterminate ? 'indeterminate' : checked ? 'checked' : 'unchecked'
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={state === 'checked'}
      data-state={state}
      className={`rounded-sm ring ring-inset ring-accented overflow-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary size-4 flex items-center justify-center cursor-pointer ${
        state === 'unchecked' ? 'bg-default' : 'bg-primary'
      }`}
      onClick={() => onChange(!checked)}
    >
      {state !== 'unchecked' && <Icon name="i-lucide:check" className="size-3 text-white" />}
    </button>
  )
}

export function Memories() {
  const t = useT()
  const toast = useToast()
  const { currentProjectId } = useProject()
  const [tab, setTab] = useState<string>(TABS[0].type)
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState('')
  const [q, setQ] = useState('')
  const [tick, setTick] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null)

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
        toast(e instanceof Error ? e.message : String(e), 'err')
      }
    },
    [tab, t, toast],
  )

  const showProfileTree = tab === 'profile_mem'
  const showSkillName = tab === 'skill_mem'
  const showDownload = tab === 'skill_mem'
  const colCount = 4 + (showProfileTree ? 1 : 0) + (showSkillName ? 1 : 0) + 2

  /** 只认当前页还在的 id，翻页、换标签、重新取数后旧选中自动失效 */
  const liveSelected = useMemo(() => {
    const ids = new Set(rows.map((m) => m.memoryId))
    return selected.filter((id) => ids.has(id))
  }, [rows, selected])

  const allChecked = rows.length > 0 && liveSelected.length === rows.length
  const someChecked = liveSelected.length > 0 && !allChecked

  const countLabel = useMemo(() => (type: string) => `（${counts[type] ?? 0}）`, [counts])

  return (
    <>
      <div data-v-1df75f9b="" className="w-full h-full flex flex-col gap-y-4">
        <div className="flex justify-between items-center">
          <div className="flex-1 flex items-center gap-x-2">
            <div className="shrink-0 text-[18px] font-semibold text-second-gray">{t('memory.title')}</div>
            <div className="flex-1 h-5 w-fit max-w-full leading-5 text-[14px] text-[#6B7280] text-ellipsis overflow-hidden whitespace-nowrap">
              <span className="text-[14px] truncate">{t('memory.desc')}</span>
            </div>
          </div>
          <div className="flex items-center gap-x-2">
            <div className="relative group">
              <button
                type="button"
                disabled={liveSelected.length === 0}
                className={liveSelected.length === 0 ? BTN_BATCH_OFF : BTN_BATCH_ON}
                onClick={() => setPendingDelete(liveSelected)}
              >
                {t('memory.action.batchDelete')}
              </button>
            </div>
            <div className="relative inline-flex items-center w-[250px]">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== 'Enter') return
                  setQ(draft.trim())
                  setPage(1)
                }}
                placeholder={t('memory.searchPlaceholder')}
                className={SEARCH_INPUT}
              />
              <span className="absolute inset-y-0 end-0 flex items-center pe-2.5">
                <Icon name="i-ri:search-line" className="shrink-0 text-dimmed size-5" />
              </span>
            </div>
            <div className="relative">
              <button
                type="button"
                className={FILTER_BTN}
                aria-label={t('memory.action.filter')}
                onClick={() => toast(t('memory.filterTodo'))}
              >
                <Icon name="i-db-filter-line" className="shrink-0 size-5" />
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-white p-[4px] rounded-[8px] w-fit">
          {TABS.map((x) => (
            <div
              key={x.type}
              role="tab"
              aria-selected={tab === x.type}
              className={tab === x.type ? PILL_ACTIVE : PILL_IDLE}
              onClick={() => {
                setTab(x.type)
                setPage(1)
              }}
            >
              {t(x.label)}
              {countLabel(x.type)}
            </div>
          ))}
        </div>

        <div className="flex-1 min-h-0 overflow-hidden">
          <div className="h-full flex flex-col justify-between">
            <Panel className="memory-list-table">
              <Table
                head={
                  <>
                    <Th>
                      <div className="relative items-start flex-row flex justify-center">
                        <div className="flex items-center h-5">
                          <Checkbox
                            checked={allChecked}
                            indeterminate={someChecked}
                            onChange={(v) => setSelected(v ? rows.map((m) => m.memoryId) : [])}
                          />
                        </div>
                      </div>
                    </Th>
                    <Th>{t('memory.col.createdAt')}</Th>
                    <Th>{t('memory.col.subjectType')}</Th>
                    <Th>{t('memory.col.subjectId')}</Th>
                    {showProfileTree && <Th>{t('memory.col.profileTreeId')}</Th>}
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
                            onChange={(v) => setSelected((prev) => (v ? [...prev, m.memoryId] : prev.filter((x) => x !== m.memoryId)))}
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
                      {showProfileTree && (
                        <td data-pinned="false" className={`${TD} max-w-[180px] truncate`}>
                          {m.profileTemplateId || m.profileInstanceId || '-'}
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
                        <div className="flex gap-4">
                          <span className={ACTION} style={{ color: '#4044ED' }} onClick={() => toast(t('memory.detailTodo'))}>
                            {t('memory.action.detail')}
                          </span>
                          {showDownload && (
                            <span className={ACTION} style={{ color: '#4044ED' }} onClick={() => toast(t('memory.downloadTodo'))}>
                              {t('memory.action.download')}
                            </span>
                          )}
                          <span className={ACTION} style={{ color: '#4044ED' }} onClick={() => setPendingDelete([m.memoryId])}>
                            {t('memory.action.delete')}
                          </span>
                        </div>
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
            <button type="button" className={BTN_DIALOG_PRIMARY} onClick={() => pendingDelete && doDelete(pendingDelete)}>
              {t('common.confirm')}
            </button>
            <button type="button" className={BTN_DIALOG_SECONDARY} onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </button>
          </>
        }
      >
        {t('memory.deleteConfirm')(pendingDelete?.length ?? 0)}
      </Dialog>
    </>
  )
}
