import React from "react";

export default function StudioMenu({ label, children, disabled = false, className = "" }: {
  label: string;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const root = React.useRef<HTMLDivElement>(null);
  const trigger = React.useRef<HTMLButtonElement>(null);
  React.useEffect(() => {
    if (!open) return;
    function outside(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);
  return (
    <div ref={root} className={`studio-menu ${className}`} onKeyDown={(event) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
      if (open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
        event.preventDefault();
        const items = Array.from(root.current?.querySelectorAll<HTMLElement>(".studio-menu-panel button:not(:disabled), .studio-menu-panel select, .studio-menu-panel input") ?? []);
        const index = items.indexOf(document.activeElement as HTMLElement);
        items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
      }
    }}>
      <button ref={trigger} type="button" disabled={disabled} aria-expanded={open} onClick={() => setOpen(!open)}>{label}</button>
      {open && <div className="studio-menu-panel" aria-label={label} onClick={(event) => {
        if ((event.target as HTMLElement).closest("button")) {
          setOpen(false);
          trigger.current?.focus();
        }
      }}>{children}</div>}
    </div>
  );
}
