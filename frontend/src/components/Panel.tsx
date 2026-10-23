import type { HTMLAttributes, ReactNode } from "react";

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
  /** Secondary text beside the title, e.g. a count or a unit. */
  meta?: ReactNode;
  /** Controls on the right of the title bar. */
  actions?: ReactNode;
  bodyClassName?: string;
}

/** The shared panel chrome: a thin title bar over a body that owns its own scrolling. */
export function Panel({ title, meta, actions, children, className = "", bodyClassName = "", ...rest }: PanelProps) {
  return (
    <section className={`flex min-h-0 flex-col rounded-[3px] border border-line bg-panel ${className}`} {...rest}>
      <header className="flex h-8 shrink-0 items-center gap-2 border-b border-line px-3">
        <h2 className="shrink-0 text-[12.5px] font-semibold tracking-[0.01em] whitespace-nowrap text-fg">{title}</h2>
        {meta != null && <span className="min-w-0 truncate text-[11.5px] text-dim">{meta}</span>}
        {actions != null && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </header>
      <div className={`relative min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
