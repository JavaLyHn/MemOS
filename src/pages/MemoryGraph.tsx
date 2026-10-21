/** 记忆星座图页面。
 *
 *  数据来自 BFF 的 `GET /api/dashboard/graph/memories`（Neo4j，不是上游 REST——
 *  上游没有任何返回「记忆之间关系」的接口）。画布在 components/Constellation.tsx。
 *
 *  ⚠️ 画布**走亮色**，跟控制台其余页面同一套。2026-10-19 之前它是固定深色
 *  （#070b16 星空底），理由是「星图这个隐喻在亮底上不成立」——那个判断是错的：
 *  控制台只有亮色主题，一块黑画布嵌在中间非常突兀（用户报的「整体主题是 light，
 *  你这个是 dark」）。改亮之后点的辨识度靠**饱和度 + 尺寸**，见 Constellation.tsx。
 */

import { useCallback, useMemo, useState } from 'react'
import { api, type GraphNode } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { useLang, useProject, useT } from '../lib/store'
import { PageHeader } from '../components/ui'
import { Constellation } from '../components/Constellation'
import { typeColor } from '../lib/constellation'
import { errText } from '../lib/i18n'
import { BTN_DIALOG_SECONDARY, BTN_PAGER, BTN_TEXT_LINK } from '../lib/cls'
import { Icon } from '../components/Icon'

const fmtTime = (iso: string) => (iso ? iso.slice(0, 19).replace('T', ' ') : '-')

export function MemoryGraph() {
  const t = useT()
  const { lang } = useLang()
  const { currentProjectId, currentProjectName, ready } = useProject()
  const [selected, setSelected] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const { data, state, error } = useAsync(() => api.graph.memories({ tenant: currentProjectId || undefined }), [currentProjectId, tick], {
    // 没有这一条的话，首帧会先用「无租户」打一次 585 KB（BFF 会退回当前活跃租户，
    // 拿到的就是同一份数据），字典回来后再打一次带 tenant 的——同一张图下载两遍，
    // 星云还要重新布局一次
    skip: !ready,
  })

  const selectedNode: GraphNode | undefined = useMemo(
    () => (selected ? data?.nodes.find((n) => n.id === selected) : undefined),
    [selected, data],
  )

  /** 选中的洞察记忆「归纳自几条记忆」。
   *
   *  ⚠️ 原来这里还给第二个数——「其中几条**还在这张图上**」——配一句
   *  「没画出来的那些来源记忆已经归档或删除，图上只画还活着的」。
   *  2026-10-19 用户要求去掉，原话是「为啥要写这种文案？自报家门了属于是」：
   *  那句话是在跟业务说「你的记忆被归档/删除了，我们只给你看剩下的」。
   *  留下一个总数就够了——**别再把这个数拆回去**。 */
  const sourceTotal = useMemo(
    () => (selectedNode && selectedNode.sourceIds.length > 0 ? selectedNode.sourceIds.length : null),
    [selectedNode],
  )

  /** 选中点所在会话的规模。抽屉里告诉业务「这条不是孤立的」，比只给一个 id 有用。 */
  const sessionSize = useMemo(() => {
    if (!selectedNode || !data) return 0
    if (!selectedNode.sessionId) return 1
    return data.nodes.filter((n) => n.sessionId === selectedNode.sessionId).length
  }, [selectedNode, data])

  const onSelect = useCallback((id: string | null) => setSelected(id), [])

  /** 抽屉里正文的**展开态**。
   *
   *  图谱接口为了体积只给截断到 120 字的 `label`（见 BFF `mappers/graph.ts`），
   *  长记忆在抽屉里看起来就是「被截断了」。展开时才去取全文——
   *  不展开不发这次请求（用户 2026-10-19 报的：「记忆详情，记忆被截断了」）。
   *
   *  ⚠️ 三份状态都**按节点 id 存**，不在切换选中时清空：用 effect 清会在切换的那一帧
   *  闪一下上一条的全文。比较 id 就够——显示时对不上自然退回截断正文。 */
  const [fullText, setFullText] = useState<{ id: string; text: string } | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [failText, setFailText] = useState<{ id: string; msg: string } | null>(null)

  const nodeId = selectedNode?.id ?? ''
  const shownText = fullText?.id === nodeId ? fullText.text : null
  const expanding = busyId === nodeId
  const expandFail = failText?.id === nodeId ? failText.msg : ''

  const toggleFull = async () => {
    if (!selectedNode) return
    const id = selectedNode.id
    if (fullText?.id === id) {
      setFullText(null)
      return
    }
    setBusyId(id)
    setFailText(null)
    try {
      // 走**图库**取全文，不走 `/project/memory/detail`：那条是上游 REST，而洞察记忆
      // （dream 归纳出来的）在上游 `get_memory/<id>` 里查不到，会回「记忆不存在」
      // ——用户 2026-10-19 就是这么撞上的。点的是画布上的节点，全文就跟节点同源。
      const m = await api.graph.memory(id, currentProjectId || undefined)
      setFullText({ id, text: m.memory || selectedNode.label })
    } catch (e) {
      setFailText({ id, msg: errText(lang, e) })
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <div className="flex h-full w-full flex-col gap-y-4">
        <PageHeader
          title={t('graph.title')}
          desc={currentProjectName ? `${t('graph.desc')} · ${currentProjectName}` : t('graph.desc')}
          actions={
            <button type="button" className={BTN_PAGER} onClick={() => setTick((x) => x + 1)} title={t('graph.reload')}>
              <Icon name="i-lucide:rotate-ccw" className="size-4" />
              <span className="text-xs">{t('graph.reload')}</span>
            </button>
          }
        />

        <div className="relative min-h-0 flex-1 overflow-hidden rounded-[12px] border border-line">
          {state === 'ready' && data && data.nodes.length > 0 && <Constellation graph={data} onSelect={onSelect} selectedId={selected} />}

          {state === 'loading' && (
            <div className="absolute inset-0 flex items-center justify-center bg-surface text-sm text-ink-muted">{t('common.loading')}</div>
          )}

          {state === 'error' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-surface px-8 text-center">
              <div className="text-sm text-warning">{error || t('common.failed')}</div>
              <div className="max-w-[520px] text-xs leading-5 text-ink-faint">{t('graph.errorHint')}</div>
            </div>
          )}

          {state === 'ready' && (!data || data.nodes.length === 0) && (
            <div className="absolute inset-0 flex items-center justify-center bg-surface text-sm text-ink-muted">{t('graph.empty')}</div>
          )}

          {/* 详情抽屉。**覆盖**在画布上而不是挤压它**：挤压会触发 ResizeObserver，
              每开一次抽屉星云就重排一次，看着像页面在抖。 */}
          {selectedNode && (
            <aside className="absolute right-0 top-0 z-20 flex h-full w-[360px] flex-col border-l border-line bg-surface shadow-2xl">
              <div className="flex items-center justify-between border-b border-line px-5 py-4">
                <h3 className="text-base font-semibold text-ink">{t('graph.detailTitle')}</h3>
                <button
                  type="button"
                  className="cursor-pointer p-1 text-ink-secondary hover:text-ink"
                  aria-label={t('common.close')}
                  onClick={() => setSelected(null)}
                >
                  <Icon name="i-lucide:x" className="size-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                <span
                  className="mb-3 inline-flex items-center rounded-[6px] px-2 py-0.5 text-xs font-medium"
                  style={{ color: typeColor(selectedNode.memoryType), backgroundColor: `${typeColor(selectedNode.memoryType)}1f` }}
                >
                  {t(`graph.type.${selectedNode.memoryType}` as 'graph.type.Other')}
                </span>
                <div className="mb-5">
                  <p className="text-sm leading-6 break-words whitespace-pre-wrap text-ink-secondary">
                    {shownText ?? (selectedNode.label || t('graph.noContent'))}
                  </p>
                  {/* 「展开全文」只在**真的被截断**时才出现（BFF 现算的 `labelTruncated`）。
                      正文不长的记忆这里什么都不显示——摆一个点了没反应的按钮比不摆更糟。 */}
                  {selectedNode.labelTruncated && (
                    <div className="mt-1.5 flex items-center gap-3">
                      <button type="button" className={BTN_TEXT_LINK} disabled={expanding} onClick={toggleFull}>
                        {expanding ? t('common.loading') : shownText !== null ? t('graph.collapse') : t('graph.expand')}
                      </button>
                      {expandFail && <span className="text-xs leading-5 text-warning">{expandFail}</span>}
                    </div>
                  )}
                </div>

                <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2.5 text-sm">
                  <dt className="text-ink-muted">{t('memory.col.createdAt')}</dt>
                  <dd className="text-ink-secondary">{fmtTime(selectedNode.createdAt)}</dd>

                  <dt className="text-ink-muted">{t('graph.fieldSession')}</dt>
                  <dd className="font-mono text-xs break-all text-ink-secondary">{selectedNode.sessionId || t('graph.noSession')}</dd>

                  <dt className="text-ink-muted">{t('graph.fieldSessionSize')}</dt>
                  <dd className="text-ink-secondary">{t('graph.sessionSize')(sessionSize)}</dd>

                  {sourceTotal !== null && (
                    <>
                      <dt className="text-ink-muted">{t('graph.fieldSources')}</dt>
                      <dd className="text-ink-secondary">{t('graph.sources')(sourceTotal)}</dd>
                    </>
                  )}

                  <dt className="text-ink-muted">{t('graph.fieldTenant')}</dt>
                  <dd className="break-all text-ink-secondary">{selectedNode.userId || '-'}</dd>

                  <dt className="text-ink-muted">{t('memory.detailId')}</dt>
                  <dd className="font-mono text-xs break-all text-ink-secondary">{selectedNode.id}</dd>
                </dl>
              </div>

              <div className="border-t border-line px-5 py-4">
                <button type="button" className={BTN_DIALOG_SECONDARY} onClick={() => setSelected(null)}>
                  {t('common.close')}
                </button>
              </div>
            </aside>
          )}
        </div>

        {/* 这里原来有一行「共 N 条记忆、M 条连线；分布在 K 个会话里……」的统计说明。
            2026-10-19 用户要求删掉：这些数字画布左下角的 HUD 里本来就有（记忆/可见/连线/缩放），
            图例上还有逐类型的条数，再来一行长句只是把画布挤矮。 */}
      </div>
    </>
  )
}
