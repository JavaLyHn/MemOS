import { useState } from 'react'
import { api, EVENT_TYPES, type LogDetail, type RequestLog } from '../lib/api'
import { ListPage } from '../components/ListPage'
import { Dialog, Tag, TextLinkButton } from '../components/ui'
import { FilterDateRange, FilterField, FilterFieldRow, FilterInput, FilterPopover, FilterSelect } from '../components/FilterPopover'
import { FILTER_LABEL } from '../lib/cls'
import { useProject, useT } from '../lib/store'

/** extractMemoryDirect 展示成 extractMemory */
const displayEvent = (e: string) => (e === 'extractMemoryDirect' ? 'extractMemory' : e)

/** 约定：SUCCESS / success 都算成功 */
const isOk = (s: string) => s === 'SUCCESS' || s === 'success'

const joinIds = (ids?: string[]) => (ids && ids.length ? ids.join(', ') : '-')

/** 把后端下发的 JSON 字符串解析出来；解析不了就原样展示 */
function pretty(raw?: string) {
  if (!raw) return '-'
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

interface LogFilters {
  eventType: string
  subjectType: string
  subjectId: string
  startTime: string
  endTime: string
}

const NO_FILTER: LogFilters = { eventType: '', subjectType: '', subjectId: '', startTime: '', endTime: '' }

export function Requests() {
  const t = useT()
  const { currentProjectId } = useProject()
  const [filters, setFilters] = useState<LogFilters>(NO_FILTER)
  const [draft, setDraft] = useState<LogFilters>(NO_FILTER)
  const [detail, setDetail] = useState<LogDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<'request' | 'response'>('request')

  const patch = (p: Partial<LogFilters>) => setDraft((d) => ({ ...d, ...p }))

  const openDetail = async (row: RequestLog) => {
    setLoading(true)
    setDetail(null)
    try {
      setDetail(await api.log.detail(row.id))
    } catch {
      setDetail({ ...row, requestBody: '', responseBody: '' } as LogDetail)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <ListPage<RequestLog>
        title={t('requests.title')}
        desc={t('requests.desc')}
        searchable
        searchPlaceholder={t('requests.searchPlaceholder')}
        panelClassName="max-h-[calc(100vh-200px)]"
        rowKey={(r) => r.id}
        deps={[currentProjectId, filters]}
        onRowClick={openDetail}
        filter={(close) => (
          <FilterPopover
            open
            onFilter={() => {
              setFilters(draft)
              close()
            }}
            onReset={() => {
              setDraft(NO_FILTER)
              setFilters(NO_FILTER)
            }}
          >
            <FilterField label={t('filter.createdAt')}>
              <FilterDateRange
                start={draft.startTime}
                end={draft.endTime}
                onChange={(startTime, endTime) => patch({ startTime, endTime })}
              />
            </FilterField>

            <FilterFieldRow>
              <div>
                <label className={FILTER_LABEL}>{t('filter.subjectType')}</label>
                <FilterSelect
                  value={draft.subjectType}
                  onChange={(subjectType) => patch({ subjectType })}
                  placeholder={t('filter.all')}
                  options={[
                    { value: 'user', label: t('filter.subjectUser') },
                    { value: 'agent', label: t('filter.subjectAgent') },
                  ]}
                />
              </div>
              <div>
                <label className={FILTER_LABEL}>{t('filter.subjectId')}</label>
                <FilterInput
                  value={draft.subjectId}
                  onChange={(subjectId) => patch({ subjectId })}
                  placeholder={t('filter.subjectIdPlaceholder')}
                />
              </div>
            </FilterFieldRow>

            <FilterField label={t('filter.eventType')}>
              <FilterSelect
                value={draft.eventType}
                onChange={(eventType) => patch({ eventType })}
                placeholder={t('filter.selectEventType')}
                options={EVENT_TYPES.map((x) => ({ value: x, label: x }))}
              />
            </FilterField>
          </FilterPopover>
        )}
        load={async (pageNum, pageSize, query) => {
          const res = await api.log.list({
            projectId: currentProjectId,
            pageNum,
            pageSize,
            query,
            eventType: filters.eventType,
            subjectType: filters.subjectType,
            subjectId: filters.subjectId,
            startTime: filters.startTime,
            endTime: filters.endTime,
          })
          return { items: res.logs, total: res.total }
        }}
        cols={[
          { key: 'createTime', label: t('requests.col.createdAt'), render: (r) => r.createTime },
          {
            key: 'eventType',
            label: t('requests.col.eventType'),
            render: (r) => <div className="font-mono text-sm">{displayEvent(r.eventType)}</div>,
          },
          { key: 'userIds', label: t('requests.col.userId'), render: (r) => joinIds(r.userIds) },
          { key: 'agentIds', label: t('requests.col.agentId'), render: (r) => joinIds(r.agentIds) },
          {
            key: 'status',
            label: t('requests.col.status'),
            render: (r) => <Tag text={r.status} tone={isOk(r.status) ? 'ok' : 'warn'} />,
          },
          {
            key: 'duration',
            label: t('requests.col.latency'),
            render: (r) => (r.duration != null ? `${r.duration}ms` : '-'),
          },
          {
            key: 'action',
            label: t('requests.col.action'),
            render: (r) => <TextLinkButton onClick={() => openDetail(r)}>{t('requests.viewDetails')}</TextLinkButton>,
          },
        ]}
      />

      <Dialog open={loading || !!detail} title={t('requests.detail.title')} onClose={() => setDetail(null)}>
        {loading && <p className="text-[#62748E]">{t('common.loading')}</p>}
        {detail && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {(
                [
                  ['traceId', detail.traceId],
                  ['status', detail.status],
                  ['duration', detail.duration != null ? `${detail.duration}ms` : '-'],
                  ['createTime', detail.createTime],
                  ['userId', detail.userId],
                  ['agentId', detail.agentId],
                  ['requestTokens', detail.requestTokens],
                  ['responseTokens', detail.responseTokens],
                ] as const
              ).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="w-[120px] shrink-0 text-[#62748E]">{k}</span>
                  <span className="min-w-0 break-all text-[#314158]">{v ?? '-'}</span>
                </div>
              ))}
            </div>

            <div className="flex gap-2 border-b border-[#E2E8F0]">
              {(
                [
                  ['request', t('requests.detail.request')],
                  ['response', t('requests.detail.response')],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${
                    tab === k ? 'border-[#4044ed] text-[#4044ed]' : 'border-transparent text-[#62748E]'
                  }`}
                  onClick={() => setTab(k)}
                >
                  {label}
                </button>
              ))}
            </div>

            <pre className="max-h-[320px] overflow-auto rounded-[8px] border border-[#E2E8F0] bg-[#f7f8fb] p-3 font-mono text-xs whitespace-pre-wrap break-all">
              {pretty(tab === 'request' ? detail.requestBody : detail.responseBody)}
            </pre>
            <p className="text-xs text-[#90A1B9]">{t('requests.detail.bodyNote')}</p>
          </div>
        )}
      </Dialog>
    </>
  )
}
