import { useState } from 'react'
import { api, type UsageDailyStat } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { useProject, useT } from '../lib/store'
import { Panel, PageHeader, StateRow, Table, TD, Th } from '../components/ui'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex-1 min-w-[180px] rounded-[12px] border border-[#E2E8F0] bg-white px-4 py-3">
      <div className="text-sm text-[#62748E] mb-1">{label}</div>
      <div className="text-[22px] font-semibold leading-7 text-[#18181b]">{value}</div>
    </div>
  )
}

/** 响应只有 dailyStats，每项按接口分组。
 *  各接口的字段名不统一：addMessage / searchMemory 用 calls，
 *  chat / extractMemory 拆输入输出，rerank 只有输入。 */
const callsOf = (d: UsageDailyStat) =>
  (d.addMessage?.calls ?? 0) + (d.searchMemory?.calls ?? 0) + (d.chat ? 1 : 0) + (d.extractMemory ? 1 : 0) + (d.rerank ? 1 : 0)

const tokensOf = (d: UsageDailyStat) =>
  (d.addMessage?.totalTokens ?? 0) +
  (d.searchMemory?.totalTokens ?? 0) +
  (d.chat?.totalTokens ?? 0) +
  (d.extractMemory?.totalTokens ?? 0) +
  (d.rerank?.totalTokens ?? 0)

const ymd = (d: Date) => d.toISOString().slice(0, 10)

export function Usage() {
  const t = useT()
  const { currentProjectId } = useProject()
  const [days] = useState(() => {
    const end = new Date()
    const start = new Date(end.getTime() - 13 * 86400000)
    return { startDate: ymd(start), endDate: ymd(end) }
  })

  // projectId 留空 = 全部项目
  const { data, state, error } = useAsync(() => api.usage.query({ projectId: currentProjectId, ...days }), [currentProjectId])

  const stats = data?.dailyStats ?? []
  const totalCalls = stats.reduce((s, d) => s + callsOf(d), 0)
  const totalTokens = stats.reduce((s, d) => s + tokensOf(d), 0)
  const peak = Math.max(1, ...stats.map((d) => callsOf(d)))

  return (
    <>
      <PageHeader title={t('usage.title')} desc={t('usage.desc')} />

      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-3">
          <Stat label={t('usage.totalApiRequests')} value={totalCalls.toLocaleString()} />
          <Stat label={t('usage.totalTokens')} value={totalTokens.toLocaleString()} />
          <Stat label={t('usage.range')} value={`${days.startDate} ~ ${days.endDate}`} />
        </div>

        <Panel className="p-5">
          {state !== 'ready' ? (
            <div className="py-6 text-center text-sm text-second-gray">
              {state === 'loading' ? t('common.loading') : `${t('common.failed')}：${error}`}
            </div>
          ) : stats.length === 0 ? (
            <div className="py-6 text-center text-sm text-second-gray">{t('usage.noData')}</div>
          ) : (
            <div className="flex items-end gap-2 h-[140px]">
              {stats.map((d) => (
                <div key={d.date} className="flex-1 flex flex-col items-center gap-1 min-w-0" title={`${d.date} · ${callsOf(d)}`}>
                  <div
                    className="w-full rounded-t-[4px] bg-[#4044ed]/80"
                    style={{ height: `${Math.max(2, (callsOf(d) / peak) * 110)}px` }}
                  />
                  <span className="text-[10px] text-[#94a3b8] truncate w-full text-center">{d.date.slice(5)}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel>
          <Table
            head={
              <>
                <Th>{t('usage.col.date')}</Th>
                <Th>{t('usage.add')}</Th>
                <Th>{t('usage.search')}</Th>
                <Th>{t('usage.chat')}</Th>
                <Th>{t('usage.col.tokens')}</Th>
              </>
            }
          >
            {state !== 'ready' && <StateRow colSpan={5} state={state} error={error} />}
            {state === 'ready' && stats.length === 0 && <StateRow colSpan={5} state="ready" />}
            {state === 'ready' &&
              [...stats].reverse().map((d) => (
                <tr key={d.date}>
                  <td data-pinned="false" className={`${TD}`}>
                    {d.date}
                  </td>
                  <td data-pinned="false" className={`${TD}`}>
                    {(d.addMessage?.calls ?? 0).toLocaleString()}
                  </td>
                  <td data-pinned="false" className={`${TD}`}>
                    {(d.searchMemory?.calls ?? 0).toLocaleString()}
                  </td>
                  <td data-pinned="false" className={`${TD}`}>
                    {(d.chat?.totalTokens ?? 0).toLocaleString()}
                  </td>
                  <td data-pinned="false" className={`${TD}`}>
                    {tokensOf(d).toLocaleString()}
                  </td>
                </tr>
              ))}
          </Table>
        </Panel>
      </div>
    </>
  )
}
