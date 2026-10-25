/** 全站动效的单一来源。
 *
 *  曲线都是 cubic-bezier 的控制点（motion 的 `ease` 直接吃四元组），和
 *  `index.css` 里的 `--ease-*` 变量是同一组值——CSS 关键帧和 JS 动画看起来才是
 *  同一种手感，而不是「有的地方弹、有的地方滑」。
 *
 *  - `EASE_OUT_EXPO`：快起慢收。前段跑掉大半位移，同样的时长看起来更跟手，
 *    停在终点时又不显得拖沓。进入、强调、指示块滑动都用它。
 *  - `EASE_OUT_SOFT`：比 expo 克制一点。长距离位移（页面切换）用它不会「冲」过头。
 *  - `EASE_IN_FAST`：退出专用。关闭动作要干脆，越晚收尾越显得迟钝。
 *
 *  时长同理，只给三档：120ms 以下的反馈用户感觉不到，320ms 以上会显得卡。
 */
export const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]
export const EASE_OUT_SOFT: [number, number, number, number] = [0.22, 1, 0.36, 1]
export const EASE_IN_FAST: [number, number, number, number] = [0.4, 0, 1, 1]

export const DUR = {
  /** 退出 / 轻反馈 */
  fast: 0.12,
  /** 常规进入 */
  base: 0.22,
  /** 页面切换 */
  page: 0.26,
} as const
