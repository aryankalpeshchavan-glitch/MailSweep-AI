import { buildGoogleLoginUrl } from "@/api/endpoints";
import { Icon } from "@/components/Icon";

/**
 * Sign-in entry. Google OAuth runs as a top-level navigation (no fetch/token
 * handling here). Session rides an HttpOnly cookie; nothing is stored in
 * localStorage (Phase 11).
 */
export function LoginPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-obsidian px-margin-safe pb-[10vh] pt-24">
      {/* Soft cinematic backdrop, no 3D needed on the gate screen. */}
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse at 30% 20%, rgba(0,240,255,0.08), transparent 55%), radial-gradient(ellipse at 80% 90%, rgba(133,35,221,0.06), transparent 50%)",
        }}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-md">
        <p className="data-label data-label-accent mb-2 text-center">MAILSWEEP AI</p>
        <h1 className="text-center text-display-lg font-semibold text-white">Sign in</h1>
        <p className="mt-3 text-center text-body-md text-neutral-grey-60">
          Connect your Google account to begin. MailSweep reads mailbox metadata
          only — it never touches email bodies.
        </p>

        <div className="panel mt-8 p-6">
          <ul className="mb-6 space-y-3 text-body-sm text-neutral-grey-60">
            <li className="flex items-start gap-2">
              <Icon name="shield" className="mt-0.5 text-data-blue" />
              <span>HttpOnly session cookie; nothing stored in your browser&apos;s storage.</span>
            </li>
            <li className="flex items-start gap-2">
              <Icon name="science" className="mt-0.5 text-data-blue" />
              <span>Analysis only — no mail is deleted or modified without approval.</span>
            </li>
          </ul>

          <a
            href={buildGoogleLoginUrl("/dashboard")}
            className="btn btn-primary w-full py-3"
          >
            <Icon name="rocket_launch" />
            Continue with Google
          </a>
        </div>

        <p className="mt-6 text-center text-xs text-neutral-grey-60">
          By signing in you understand MailSweep&apos;s privacy model (metadata only).
        </p>
      </div>
    </div>
  );
}