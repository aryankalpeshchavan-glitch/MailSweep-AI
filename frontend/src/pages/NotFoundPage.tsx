import { Link } from "react-router-dom";

/** 404 — keeps users oriented with a graceful exit back to the landing page. */
export function NotFoundPage() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-obsidian px-margin-safe text-center">
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse at 30% 20%, rgba(0,240,255,0.08), transparent 55%), radial-gradient(ellipse at 80% 90%, rgba(133,35,221,0.06), transparent 50%)",
        }}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-md">
        <p className="data-label data-label-accent mb-2">404</p>
        <h1 className="text-display-lg font-semibold text-white">
          This region of the universe is empty
        </h1>
        <p className="mt-3 text-body-md text-neutral-grey-60">
          The page you&apos;re looking for doesn&apos;t exist or has been
          archived.
        </p>
        <div className="mt-8">
          <Link to="/" className="btn btn-primary">
            Return home
          </Link>
        </div>
      </div>
    </div>
  );
}
