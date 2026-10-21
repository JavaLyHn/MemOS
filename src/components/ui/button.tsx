import * as React from 'react'
import { cn } from '../../lib/utils'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'destructive'
  size?: 'sm' | 'md' | 'lg' | 'icon'
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', size = 'md', ...props }, ref) => {
    const base =
      'inline-flex items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/30 disabled:pointer-events-none disabled:opacity-50 cursor-pointer active:scale-[0.98]'

    const variants = {
      primary: 'bg-accent text-on-accent shadow-sm hover:bg-accent-hover border border-transparent',
      secondary:
        'bg-surface text-ink-secondary shadow-xs border border-line hover:bg-surface-muted hover:text-ink hover:border-line-strong',
      outline: 'border border-line text-ink-secondary hover:bg-surface-muted hover:text-ink',
      ghost: 'text-ink-secondary hover:bg-surface-hover hover:text-ink border border-transparent',
      destructive: 'bg-danger-soft text-danger border border-danger/40 hover:bg-danger-soft hover:text-danger',
    }

    const sizes = {
      sm: 'h-8 px-2.5 text-xs',
      md: 'h-9 px-3.5 text-sm',
      lg: 'h-10 px-4 text-sm',
      icon: 'h-8 w-8 p-0',
    }

    return <button ref={ref} className={cn(base, variants[variant], sizes[size], className)} {...props} />
  },
)
Button.displayName = 'Button'
