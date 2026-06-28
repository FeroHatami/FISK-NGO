import { Link } from "@tanstack/react-router";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link
      to="/app"
      className={`group block ${className}`}
      aria-label="Burundi Kids workspace"
    >
      <div className="flex items-center gap-3 px-1 py-1">
        <div className="relative grid size-11 place-items-center rounded-xl bg-white ring-1 ring-hairline shadow-[0_1px_2px_rgba(20,20,20,0.04)] transition group-hover:ring-ink/15">
          <img
            src="/burundi-kids-icon.png"
            alt=""
            className="h-9 w-9 object-contain"
            draggable={false}
          />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-[13px] font-semibold tracking-tight text-ink">
            Burundi Kids
          </span>
          <span className="text-[11px] text-ink-faint">Workspace</span>
        </div>
      </div>
    </Link>
  );
}
