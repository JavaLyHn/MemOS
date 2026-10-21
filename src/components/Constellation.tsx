/** 记忆星座图画布。
 *
 *  移植自 Hindsight 的 `constellation.tsx`（`vectorize-io/hindsight`，MIT），
 *  布局算法在 lib/constellation.ts，这里只管画和交互。保留的几处关键做法：
 *    - **不做力导向**：位置是算定的，视觉上的「活」全部来自叠加的正弦漂移/呼吸/闪烁；
 *    - 连线用略微外拱的二次贝塞尔（`mid + (dy,-dx)*0.08`），直线画出来像网格、曲线像星图；
 *    - 悬停时**只画悬停点的连线**，并在曲线上跑一颗「光珠」，其余点压到 8% 透明度；
 *    - 标签用网格去重（90px 一格，占过的格子不再放），否则密集区会糊成一片字。
 *
 *  两处刻意偏离原版：
 *    1. 配色。原版是亮底 + 冷暖色阶；这里**也走亮色**，跟控制台其余页面同一套
 *       （白底 / `#E2E8F0` 边框 / `#303133`·`#62748E` 文字）。
 *       2026-10-19 之前这里画布是**固定深色**（#070b16 星空底 + 底部辉光 + 点阵），
 *       理由是「星图这个隐喻在亮底上不成立」——那个判断是错的：控制台只有亮色主题，
 *       一块黑画布嵌在中间非常突兀（用户报的「整体主题是 light，你这个是 dark」）。
 *       改亮之后有一个必须一起调的东西：**点的辨识度**。深色底下层次靠「越亮越重要」，
 *       亮色底下没有那个空间（白底已经是最亮），所以改成靠**饱和度 + 尺寸**表达，
 *       辉光只留极淡一层，否则在浅底上会糊成一块脏印子。
 *    2. 色相编码。原版点的颜色是「关系数」的色阶；这里颜色编**记忆类型**（和区域色块一致），
 *       关系数改由**大小 + 饱和度 + 极淡的辉光**表达。理由是类型是业务能直接读懂的一维，
 *       两个颜色系统叠在一起反而谁都读不出来。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { GraphNode, MemoryGraph } from '../../shared/contract'
import { buildLayout, hexToRgba, LINK_COLORS, typeColor, type Layout } from '../lib/constellation'
import { useT } from '../lib/store'
import { useTheme } from '../lib/theme'
import { Icon } from './Icon'
import { drawMinimap, drawScene, hitTest, MINIMAP, palette, projectNodes, type Camera, type Frame } from './constellation/draw'

export interface ConstellationProps {
  graph: MemoryGraph
  /** 点了某个点。参数是节点 id */
  onSelect: (id: string | null) => void
  selectedId?: string | null
}

const fmtTime = (iso: string) => (iso ? iso.slice(0, 19).replace('T', ' ') : '-')

export function Constellation({ graph, onSelect, selectedId }: ConstellationProps) {
  const t = useT()
  const { resolved: theme } = useTheme()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const miniRef = useRef<HTMLCanvasElement>(null)
  const tipRef = useRef<HTMLDivElement>(null)
  const animRef = useRef(0)
  const clockRef = useRef({ seconds: 0, lastMs: 0 })

  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [motion, setMotion] = useState(true)
  const [full, setFull] = useState(false)
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null)
  const motionRef = useRef(true)

  /** 过滤掉被关掉的类型。连线不用跟着过滤——buildLayout 会丢掉端点不存在的边。 */
  const layout = useMemo<Layout>(() => {
    const nodes = hidden.size ? graph.nodes.filter((n) => !hidden.has(n.memoryType)) : graph.nodes
    return buildLayout({ ...graph, nodes })
  }, [graph, hidden])

  const layoutRef = useRef(layout)
  /* 动画循环是一个长驻的 rAF，不能把 theme 放进它的依赖里（那会每切一次主题就重启循环）。
     用 ref 传递，循环每帧读当前值。 */
  const themeRef = useRef(theme)
  useEffect(() => {
    themeRef.current = theme
  }, [theme])
  const cbRef = useRef({ onSelect, t, selectedId, hidden })
  // 每帧都要读这几个回调/文案，但把它们放进动画循环的依赖会让循环反复重启，所以走 ref
  useEffect(() => {
    cbRef.current = { onSelect, t, selectedId, hidden }
  })

  /** 上一帧的屏幕坐标快照。点击要**现算**命中：`left_click` 这类合成事件里
   *  mousedown/mouseup 可能落在同一 tick，动画循环还没来得及刷新 hoverIndex，
   *  只看上一帧的 hoverIndex 会让「点得很快」变成点空。 */
  const frameRef = useRef<Frame>({ sx: new Float32Array(0), sy: new Float32Array(0), visible: new Uint8Array(0), n: 0 })

  const stateRef = useRef<Camera>({
    panX: 0,
    panY: 0,
    zoom: 0.4,
    tPanX: 0,
    tPanY: 0,
    tZoom: 0.4,
    mouseX: -1,
    mouseY: -1,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    panStartX: 0,
    panStartY: 0,
    hoverIndex: -1,
    prevHoverIndex: -2,
    W: 0,
    H: 0,
    dpr: 1,
    fit: 0.4,
  })

  /* ------------------------------------------------------------ 动画循环 */

  /* ⚠️ 循环要「下一帧再调自己」，但 `const animate` 在自己的初始化里引用自己会撞 TDZ
   *  （lint 的 no-use-before-declare 也会拦）。所以走一层 ref 间接调用：
   *  `animateRef` 每次渲染后指向最新的 animate，而 animate 本身始终是同一个函数引用，
   *  这样事件绑定的 effect 不会因为依赖变化而反复重建。 */
  const animateRef = useRef<() => void>(() => {})

  const animate = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) {
      animRef.current = requestAnimationFrame(() => animateRef.current())
      return
    }
    const L = layoutRef.current
    const s = stateRef.current
    const { t: tr, selectedId: sel } = cbRef.current

    const lerp = (a: number, b: number, k: number) => a + (b - a) * k
    s.panX = lerp(s.panX, s.tPanX, 0.12)
    s.panY = lerp(s.panY, s.tPanY, 0.12)
    s.zoom = lerp(s.zoom, s.tZoom, 0.12)

    const now = performance.now()
    const clock = clockRef.current
    if (motionRef.current && clock.lastMs > 0) clock.seconds += (now - clock.lastMs) / 1000
    clock.lastMs = now
    const time = clock.seconds

    // 坐标投影与命中检测用同一份屏幕坐标，见 constellation/draw.ts
    const frame = projectNodes(L, s, time)
    frameRef.current = frame

    if (s.mouseX >= 0 && !s.dragging) s.hoverIndex = hitTest(frame, s.mouseX, s.mouseY, s.zoom)

    /* 悬停变化时更新 React 侧（tooltip 内容 + 高亮）。**只在变化时** setState，
     * 不能每帧都调——那会变成 60 次/秒的重渲染。 */
    if (s.hoverIndex !== s.prevHoverIndex) {
      s.prevHoverIndex = s.hoverIndex
      if (s.hoverIndex >= 0) {
        const nd = L.nodes[s.hoverIndex]
        // 位置在这里就算好并夹进画布内——render 期间不能读 ref（lint 会拦，
        // 而且那样在并发渲染下本来就不安全）
        setHover({
          id: nd.id,
          x: Math.min(frame.sx[s.hoverIndex] + 16, Math.max(8, s.W - 312)),
          y: Math.min(frame.sy[s.hoverIndex] + 16, Math.max(8, s.H - 190)),
        })
      } else {
        setHover(null)
      }
    }

    drawScene({ ctx, L, s, frame, time, hoverIndex: s.hoverIndex, selectedId: sel, t: tr, theme: themeRef.current })

    const mini = miniRef.current
    if (mini) drawMinimap(mini, L, s, themeRef.current)

    animRef.current = requestAnimationFrame(() => animateRef.current())
  }, [])

  useEffect(() => {
    animateRef.current = animate
  }, [animate])

  /* -------------------------------------------------------------- 尺寸 */

  const measure = useCallback(() => {
    const canvas = canvasRef.current
    const mini = miniRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const r = canvas.getBoundingClientRect()
    canvas.width = Math.max(1, Math.round(r.width * dpr))
    canvas.height = Math.max(1, Math.round(r.height * dpr))
    if (mini) {
      mini.width = Math.round(MINIMAP * dpr)
      mini.height = Math.round(MINIMAP * dpr)
    }
    const s = stateRef.current
    s.dpr = dpr
    s.W = r.width
    s.H = r.height
  }, [])

  /** 自适应缩放：让整片星云（含 2.5 倍余量）落进视口 */
  const fit = useCallback(() => {
    const s = stateRef.current
    const L = layoutRef.current
    if (!s.W || !s.H) return
    // 2.2 = 留 10% 边距。原来取 2.5，星云只占视口高度的 80%，
    // 在 2:1 的宽画布上两边会空出一大片
    const z = L.maxR > 0 ? Math.min(s.W, s.H) / (L.maxR * 2.2) : 0.5
    const clamped = Math.max(0.02, Math.min(4, z))
    s.fit = clamped
    s.zoom = clamped
    s.tZoom = clamped
    s.panX = 0
    s.panY = 0
    s.tPanX = 0
    s.tPanY = 0
  }, [])

  // 布局变了（换租户 / 切类型过滤）就重新量一次并复位视角
  useEffect(() => {
    layoutRef.current = layout
    measure()
    fit()
  }, [layout, measure, fit])

  /* ------------------------------------------------------------ 事件绑定 */

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const s = stateRef.current

    measure()
    fit()
    animRef.current = requestAnimationFrame(animate)

    const onResize = () => measure()

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      // 以光标为锚点缩放：先记下光标下的世界坐标，缩放后把它挪回原位
      const wx = (mx - s.W / 2 - s.tPanX) / s.tZoom
      const wy = (my - s.H / 2 - s.tPanY) / s.tZoom
      const next = Math.max(0.02, Math.min(8, s.tZoom * (e.deltaY > 0 ? 0.9 : 1.1)))
      s.tZoom = next
      s.tPanX = mx - s.W / 2 - wx * next
      s.tPanY = my - s.H / 2 - wy * next
    }

    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      s.mouseX = e.clientX - rect.left
      s.mouseY = e.clientY - rect.top
      if (s.dragging) {
        s.tPanX = s.panStartX + (e.clientX - s.dragStartX)
        s.tPanY = s.panStartY + (e.clientY - s.dragStartY)
        canvas.style.cursor = 'grabbing'
      } else {
        canvas.style.cursor = s.hoverIndex >= 0 ? 'pointer' : 'grab'
      }
    }

    const onDown = (e: MouseEvent) => {
      s.dragging = true
      s.dragStartX = e.clientX
      s.dragStartY = e.clientY
      s.panStartX = s.panX
      s.panStartY = s.panY
    }

    const onUp = (e: MouseEvent) => {
      if (!s.dragging) return
      // 位移小于 3px 才算点击——否则每次平移结束都会误开抽屉
      const moved = Math.abs(s.panX - s.panStartX) + Math.abs(s.panY - s.panStartY)
      // ⚠️ 用**事件自带**的坐标而不是 s.mouseX：合成点击（CDP / 自动化）
      // 可能把 mousemove 与 mouseup 挤在同一个 tick，那时 s.mouseX 还是 -1，
      // 于是「点得很快」会变成点空。
      const rect = canvas.getBoundingClientRect()
      const idx = hitTest(frameRef.current, e.clientX - rect.left, e.clientY - rect.top, s.zoom)
      const nd = idx >= 0 ? layoutRef.current.nodes[idx] : undefined
      if (moved < 3 && idx >= 0 && nd) {
        s.hoverIndex = idx
        cbRef.current.onSelect(nd.id)
      }
      s.dragging = false
      canvas.style.cursor = s.hoverIndex >= 0 ? 'pointer' : 'grab'
    }

    const onLeave = () => {
      s.mouseX = -1
      s.mouseY = -1
      s.dragging = false
      s.hoverIndex = -1
    }

    window.addEventListener('resize', onResize)
    canvas.addEventListener('wheel', onWheel, { passive: false })
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mousedown', onDown)
    canvas.addEventListener('mouseup', onUp)
    canvas.addEventListener('mouseleave', onLeave)
    // 容器尺寸变化（抽屉开合、全屏切换）不一定触发 window resize，
    // 不重测的话位图会被 CSS 拉伸，字和点都糊
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => measure()) : null
    ro?.observe(canvas)

    return () => {
      cancelAnimationFrame(animRef.current)
      window.removeEventListener('resize', onResize)
      ro?.disconnect()
      canvas.removeEventListener('wheel', onWheel)
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mousedown', onDown)
      canvas.removeEventListener('mouseup', onUp)
      canvas.removeEventListener('mouseleave', onLeave)
    }
  }, [animate, measure, fit, full])

  /* ------------------------------------------------------------ 缩略图导航 */

  const miniJump = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const mini = miniRef.current
    if (!mini) return
    const L = layoutRef.current
    const s = stateRef.current
    const rect = mini.getBoundingClientRect()
    const R = Math.max(L.maxR * 1.08, 1)
    const k = MINIMAP / (2 * R)
    // 缩略图坐标 → 世界坐标 → 反解出让该点居中的 pan
    const wx = (e.clientX - rect.left - MINIMAP / 2) / k
    const wy = (e.clientY - rect.top - MINIMAP / 2) / k
    s.tPanX = -wx * s.tZoom
    s.tPanY = -wy * s.tZoom
  }, [])

  /* ---------------------------------------------------------------- 渲染 */

  const toggleType = (name: string) => {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const toggleMotion = () => {
    setMotion((prev) => {
      const next = !prev
      motionRef.current = next
      return next
    })
  }

  /** 工具栏的放大 / 缩小。锚点是画布中心（滚轮那套才以光标为锚点）。 */
  const zoomBy = useCallback((k: number) => {
    const s = stateRef.current
    s.tZoom = Math.max(0.02, Math.min(8, s.tZoom * k))
  }, [])

  const hoveredNode: GraphNode | undefined = useMemo(
    () => (hover ? graph.nodes.find((x) => x.id === hover.id) : undefined),
    [hover, graph.nodes],
  )
  const linkCountOf = useMemo(() => {
    if (!hover) return 0
    let c = 0
    for (const l of graph.links) if (l.source === hover.id || l.target === hover.id) c++
    return c
  }, [hover, graph.links])

  const types = graph.stats?.types ?? []
  const btn =
    'h-8 w-8 rounded-md border border-line bg-surface/90 text-ink-secondary hover:bg-surface hover:text-ink shadow-xs flex items-center justify-center transition-all cursor-pointer active:scale-95'

  return (
    // ⚠️ 根节点**只能有一个定位类**：同时写 `relative` 与 `absolute` 时，编译产物里
    // `.relative` 排在 `.absolute` 之后会静默胜出，容器高度塌成 0，画布一片空白。
    <div
      className={`${full ? 'fixed inset-0 z-100' : 'absolute inset-0'} overflow-hidden`}
      style={{
        backgroundColor: palette(theme).bg,
        backgroundImage:
          theme === 'dark'
            ? 'radial-gradient(72% 62% at 50% 104%, rgba(129,140,248,0.10) 0%, rgba(129,140,248,0.03) 55%, rgba(129,140,248,0) 100%),' +
              'radial-gradient(circle, rgba(148,163,184,0.16) 1px, transparent 1px)'
            : 'radial-gradient(72% 62% at 50% 104%, rgba(99,102,241,0.08) 0%, rgba(99,102,241,0.02) 55%, rgba(99,102,241,0) 100%),' +
              'radial-gradient(circle, rgba(148,163,184,0.22) 1px, transparent 1px)',
        backgroundSize: 'auto, 26px 26px',
      }}
    >
      <canvas ref={canvasRef} className="absolute inset-0 block h-full w-full cursor-grab" />

      {/* 悬浮工具栏 (Frosted Glass Floating Island) */}
      <div className="absolute left-3.5 top-3.5 flex items-center gap-1.5 p-1 rounded-lg border border-line bg-surface/80 shadow-xs backdrop-blur-md">
        <button type="button" className={btn} title={t('graph.zoomIn')} aria-label={t('graph.zoomIn')} onClick={() => zoomBy(1.25)}>
          <Icon name="i-lucide:plus" className="size-4" />
        </button>
        <button type="button" className={btn} title={t('graph.zoomOut')} aria-label={t('graph.zoomOut')} onClick={() => zoomBy(0.8)}>
          <Icon name="i-lucide:minus" className="size-4" />
        </button>
        <button type="button" className={btn} title={t('graph.fit')} aria-label={t('graph.fit')} onClick={fit}>
          <Icon name="i-lucide:crosshair" className="size-4" />
        </button>
        <button
          type="button"
          className={btn}
          title={motion ? t('graph.motionOff') : t('graph.motionOn')}
          aria-label={motion ? t('graph.motionOff') : t('graph.motionOn')}
          aria-pressed={motion}
          onClick={toggleMotion}
        >
          <Icon name={motion ? 'i-lucide:pause' : 'i-lucide:play'} className="size-4" />
        </button>
        <button
          type="button"
          className={btn}
          title={full ? t('graph.exitFullscreen') : t('graph.fullscreen')}
          aria-label={full ? t('graph.exitFullscreen') : t('graph.fullscreen')}
          onClick={() => setFull((v) => !v)}
        >
          <Icon name={full ? 'i-lucide:minimize' : 'i-lucide:maximize'} className="size-4" />
        </button>
      </div>

      {/* 操作提示 */}
      <div className="pointer-events-none absolute left-4 text-[11px] font-medium text-ink-faint" style={{ top: 62 }}>
        {t('graph.instructions')}
      </div>

      {/* 图例：毛玻璃浮岛设计 */}
      <div className="absolute right-3.5 top-3.5 w-[196px] rounded-xl border border-line bg-surface/85 p-3.5 shadow-xs backdrop-blur-md">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{t('graph.legendTypes')}</div>
        <div className="flex flex-col gap-1.5">
          {types.map((ty) => {
            const off = hidden.has(ty.name)
            return (
              <button
                key={ty.name}
                type="button"
                onClick={() => toggleType(ty.name)}
                aria-pressed={!off}
                className="flex items-center gap-2 text-left text-[11px] text-ink-secondary hover:text-ink"
                style={{ opacity: off ? 0.4 : 1 }}
              >
                <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: typeColor(ty.name) }} />
                <span className="flex-1 truncate">{t(`graph.type.${ty.name}` as 'graph.type.Other')}</span>
                <span className="tabular-nums text-ink-faint">{ty.count}</span>
              </button>
            )
          })}
        </div>
        <div className="mt-3 border-t border-line pt-2">
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{t('graph.legendLinks')}</div>
          {(['session', 'parent', 'merged', 'derived'] as const).map((k) => (
            <div key={k} className="flex items-center gap-2 text-[11px] text-ink-secondary">
              <span className="h-px w-4 shrink-0" style={{ backgroundColor: LINK_COLORS[k] }} />
              <span className="truncate">{t(`graph.link.${k}` as 'graph.link.session')}</span>
            </div>
          ))}
          {/* 图例到「点越大 / 关系越多」为止。
              2026-10-19 用户把下面这几句一起删了（原话是「这个文案给去掉」）：
                「归纳关系」是洞察记忆的「归纳自哪几条记忆」——上游把它存在节点属性里…
                点越大 = 关系越多
                散点 = 没有会话归属的记忆（N 条）
                上下文这类连关系边也没有
              前两句和后两句都是**为了解释「为什么图上长这样」**补的（前一句回应
              「为什么这些洞察记忆一条边都没有」，后两句回应「用户记忆难道不跟会话关联」）。
              用户看过之后判断不需要，那就不要——**别再自作主张加回去**。 */}
        </div>
      </div>

      {/* 缩略图：星云整体轮廓 + 当前视口框，点一下跳过去 */}
      <div className="absolute bottom-3 right-3 overflow-hidden rounded-[8px] border border-line bg-surface/90">
        <canvas
          ref={miniRef}
          width={MINIMAP}
          height={MINIMAP}
          style={{ width: MINIMAP, height: MINIMAP }}
          className="block cursor-pointer"
          onClick={miniJump}
          aria-label={t('graph.minimap')}
        />
      </div>

      {/* 悬停卡。内容走 React（记忆正文来自上游，必须走转义路径，不能 innerHTML） */}
      {hover && hoveredNode && (
        <div
          ref={tipRef}
          className="pointer-events-none absolute z-10 w-[300px] rounded-[8px] border border-line bg-surface/95 p-3 text-[12px] leading-5 text-ink-secondary shadow-xl"
          style={{ left: hover.x, top: hover.y }}
        >
          <div className="mb-1.5 flex items-center gap-2">
            <span
              className="rounded-[4px] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: typeColor(hoveredNode.memoryType), backgroundColor: hexToRgba(typeColor(hoveredNode.memoryType), 0.16) }}
            >
              {t(`graph.type.${hoveredNode.memoryType}` as 'graph.type.Other')}
            </span>
            <span className="text-[10px] text-ink-faint">{t('graph.linkCount')(linkCountOf)}</span>
          </div>
          <div className="mb-2" style={{ display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {hoveredNode.label || hoveredNode.id}
          </div>
          <div className="flex flex-col gap-0.5 border-t border-line pt-2 text-[11px] text-ink-muted">
            <span>{fmtTime(hoveredNode.createdAt)}</span>
            {hoveredNode.sessionId && <span className="truncate font-mono text-[10px]">{hoveredNode.sessionId}</span>}
          </div>
        </div>
      )}

      {graph.stats.truncated && (
        <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-[6px] border border-warning/40 bg-warning-soft px-3 py-1 text-[11px] text-warning">
          {t('graph.truncated')(graph.stats.nodes)}
        </div>
      )}
    </div>
  )
}
