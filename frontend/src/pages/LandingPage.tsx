import { forwardRef, lazy, Suspense } from "react";
import { useScrollStory } from "@/animations/useScrollStory";
import { useSceneProfile } from "@/hooks/useSceneProfile";
import { cn } from "@/lib/cn";

// WebGL scene is heavy → loaded only when needed (Phase 14).
const MailUniverseCanvas = lazy(() =>
  import("@/three/MailUniverseCanvas").then((m) => ({ default: m.MailUniverseCanvas }))
);

/** Story beats (Phase 5). The hero = first beat; the rest scroll beneath. */
const BEATS: Array<{ n: string; title: string; body: string }> = [
  { n: "01", title: "Inbox, under control.", body: "Your mail seen as a system — not a pile." },
  { n: "02", title: "Enter the universe.", body: "Every message is a point of light. Tens of thousands of them." },
  { n: "03", title: "This is chaos.", body: "Unread, unorganised, undifferentiated. Noise has no structure." },
  { n: "04", title: "MailSweep analyzes.", body: "Metadata, senders, patterns, engagement. Nothing is deleted." },
  { n: "05", title: "Emails organize.", body: "Similar mail clusters itself into readable groups." },
  { n: "06", title: "The five-year moment.", body: "Time becomes space. Old mail moves to its own region." },
  { n: "07", title: "Low-risk separates.", body: "Old, unengaged, low-risk email leaves the active zone." },
  { n: "08", title: "A recommendation forms.", body: "Confidence. Risk. Reasoning. Everything is explained." },
  { n: "09", title: "You decide.", body: "Automation never touches Gmail without you." },
  { n: "10", title: "Chaos → clarity.", body: "A calm, engineered inbox." },
];

export function MailUniversePage() {
  const profile = useSceneProfile();
  // sections: 1 hero..10 beats + 1 five-year panel + 1 safety/CTA
  const sectionCount = BEATS.length + 2;
  const { progressRef, activeIndex, setSection } = useScrollStory(sectionCount);
  // A beat is "active" when its section index (1-based) matches the active index.
  const activeBeat = activeIndex >= 1 && activeIndex <= BEATS.length ? activeIndex - 1 : null;

  return (
    <main className="relative bg-obsidian">
      {/* Fixed cinematic backdrop (3D or 2D fallback). */}
      <div className="sticky top-0 h-screen w-full">
        <Suspense
          fallback={<div className="mail-universe-fallback h-full w-full" aria-hidden="true" />}
        >
          <MailUniverseCanvas profile={profile} progressRef={progressRef} className="inset-0" />
        </Suspense>
        <div
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/60 via-transparent to-black/60"
          aria-hidden="true"
        />
      </div>

      {/* Story sections scroll over the fixed canvas. */}
      <div className="relative">
        {BEATS.map((beat, i) => {
          const idx = 1 + i;
          return (
            <StorySection
              key={beat.n}
              ref={setSection(idx)}
              active={activeIndex === idx}
              n={beat.n}
              title={beat.title}
              body={beat.body}
            />
          );
        })}

        {/* ---- The 5-Year Moment (Phase 6) ---- */}
        <section ref={setSection(1 + BEATS.length)} className="flex min-h-screen items-center justify-center px-margin-safe py-stack-lg">
          <YearsPanel active={activeIndex === 1 + BEATS.length} />
        </section>

        {/* ---- Safety / trust (Phase 7) + CTA ---- */}
        <section ref={setSection(2 + BEATS.length)} className="flex min-h-screen flex-col items-center justify-center gap-stack-lg px-margin-safe py-stack-lg text-center">
          <SafetyMoment active={activeIndex === 2 + BEATS.length} />
        </section>

        {/* Hero beat overlays the very first section for legible copy. */}
        <HeroBeat show={activeBeat === 0 || activeIndex === 0} />
      </div>
    </main>
  );
}
/* ------------------------------------------------------------------ parts */

interface SectionProps {
  active: boolean;
  n: string;
  title: string;
  body: string;
}

/** A full-height story section; fades in when it owns the viewport. */
const StorySection = forwardRef<HTMLElement, SectionProps>(function StorySection(
  { active, n, title, body },
  ref
) {
  return (
    <section
      ref={ref as React.Ref<HTMLElement>}
      className="relative flex min-h-screen items-center justify-center px-margin-safe py-stack-lg"
    >
      <div
        className="pointer-events-none max-w-2xl transition-all duration-500"
        style={{
          opacity: active ? 1 : 0,
          transform: active ? "translateY(0)" : "translateY(24px)",
        }}
      >
        <p className="data-label data-label-accent mb-3">BEAT {n}</p>
        <h2 className="text-display-xl text-white">{title}</h2>
        <p className="mt-4 text-body-lg text-neutral-grey-60">{body}</p>
      </div>
    </section>
  );
});

/** Top hero overlay — big title + CTA over the opening shot (hero beat 01). */
function HeroBeat({ show }: { show: boolean }) {
  return (
    <div
      className="pointer-events-none absolute inset-0 flex items-center justify-center px-margin-pad text-center transition-opacity duration-1000"
      style={{ opacity: show ? 1 : 0 }}
      aria-hidden={!show}
    >
      <div className="max-w-3xl">
        <p className="data-label data-label-accent mb-4">CINEMATIC EMAIL MANAGEMENT</p>
        <h1 className="font-display text-display font-bold leading-[0.96] text-white">
          Your inbox is a system.
          <br />
          <span className="text-data-blue">Let&apos;s engineer it.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-body-lg text-neutral-grey-60">
          MailSweep analyzes your mailbox, explains what it finds, and only
          ever acts with your explicit approval.
        </p>
        <a
          href="/login"
          className="pointer-events-auto btn btn-primary mt-8 rounded-full px-8 py-3 text-base"
        >
          Start the experience
        </a>
        <p className="mt-3 text-body-sm text-neutral-grey-60">
          Scroll to fly through the universe
        </p>
      </div>
    </div>
  );
}

/** The signature 5-year visualization: time rendered as space (Phase 6). */
const YEARS = ["2021", "2022", "2023", "2024", "2025", "2026"] as const;

function YearsPanel({ active }: { active: boolean }) {
  return (
    <div className="pointer-events-none w-full max-w-4xl">
      <p className="data-label data-label-accent mb-4 text-center">THE 5-YEAR MOMENT</p>

      {/* Spatial timeline: 2021 (oldest) at left → 2026 */}
      <div
        className="flex items-end justify-around gap-2 md:gap-4 transition-all duration-700"
        style={{ transform: active ? "scaleX(1)" : "scaleX(0.92)", opacity: active ? 1 : 0.6 }}
      >
        {YEARS.map((year, i) => {
          const oldest = i === 0;
          return (
            <div key={year} className="flex flex-1 flex-col items-center gap-2">
              <div
                className="w-2 rounded-full md:w-3"
                style={{
                  height: `${38 + i * 12}px`,
                  background: oldest ? "#ffc080" : "#00dbe9",
                }}
              />
              <span className="font-mono text-body-md text-neutral-grey-60">{year}</span>
            </div>
          );
        })}
      </div>

      <div className="mt-10 grid gap-4 text-center md:grid-cols-3">
        <DataChip label="OLDER THAN 5 YEARS" value="2021–2022" tone="amber" />
        <DataChip label="LOW RECENT INTERACTION" value="<1% open rate" tone="blue" />
        <DataChip label="RISK" value="Low" tone="violet" />
      </div>

      <p className="mt-6 text-center text-body-sm text-neutral-grey-60">
        Demo data shown until your analysis completes.
      </p>
    </div>
  );
}

function DataChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "amber" | "blue" | "violet";
}) {
  const toneCls =
    tone === "amber"
      ? "text-safety-amber"
      : tone === "violet"
        ? "text-neural-violet"
        : "text-data-blue";
  return (
    <div className="panel p-4">
      <p className="data-label">{label}</p>
      <p className={cn("mt-2 font-display text-headline-md", toneCls)}>{value}</p>
    </div>
  );
}

/** The trust moment: we analyze, you decide (Phase 7). */
function SafetyMoment({ active }: { active: boolean }) {
  const steps = ["Analyzes", "Recommends", "You approve", "MailSweep executes"];
  return (
    <div className="w-full max-w-3xl">
      <p className="data-label data-label-accent mb-3 text-center">ABSOLUTE SAFETY</p>
      <h2
        className="font-display text-display text-white transition-all duration-700"
        style={{ opacity: active ? 1 : 0, transform: active ? "scaleY(1)" : "scaleY(0.95)" }}
      >
        We don&apos;t delete blindly.
        <br />
        <span className="text-safety-amber">You decide.</span>
      </h2>
      <p className="mx-auto mt-6 max-w-xl text-body-md text-neutral-grey-60">
        MailSweep only ever moves mail to Gmail&apos;s Trash — recoverable — and
        only after you explicitly approve a plan. Analysis itself changes nothing.
      </p>
      <ol className="mx-auto mt-8 flex max-w-2xl flex-wrap justify-center gap-3">
        {steps.map((s, i) => (
          <li key={s} className="flex items-center gap-3">
            <span className="panel flex h-10 items-center gap-2 px-4 font-mono text-xs text-data-blue">
              {String(i + 1).padStart(2, "0")}
              <span className="text-neutral-grey-60">{s}</span>
            </span>
            {i < steps.length - 1 && <span className="text-neutral-grey-40">→</span>}
          </li>
        ))}
      </ol>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
        <a href="/login" className="btn btn-primary rounded-full px-7 py-3">
          Sign in to MailSweep
        </a>
        <a href="/recommendations" className="btn btn-ghost rounded-full px-7 py-3">
          See how decisions work
        </a>
      </div>
    </div>
  );
}