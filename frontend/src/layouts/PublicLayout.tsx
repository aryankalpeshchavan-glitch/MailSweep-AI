import { Link, Outlet } from "react-router-dom";
import { useAuth } from "@/context/useAuth";

/** Minimal chrome for public routes (landing + login). The landing page
 *  manages its own cinematic layer; this just paints a top bar. */
export function PublicLayout() {
  const { isAuthenticated } = useAuth();
  return (
    <div className="flex min-h-screen flex-col bg-obsidian">
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-center justify-between px-margin-safe py-5">
        <Link to="/" className="pointer-events-auto flex items-center gap-2 font-display text-lg font-semibold text-white">
          <span className="inline-block h-2 w-2 rounded-full bg-data-blue" aria-hidden="true" />
          MailSweep
          <span className="text-neutral-grey-60">AI</span>
        </Link>
        <nav className="pointer-events-auto flex items-center gap-stack-sm" aria-label="Primary">
          {isAuthenticated ? (
            <Link to="/dashboard" className="btn btn-primary text-sm">
              Dashboard
            </Link>
          ) : (
            <Link to="/login" className="btn btn-secondary text-sm">
              Sign in
            </Link>
          )}
        </nav>
      </header>
      <Outlet />
    </div>
  );
}