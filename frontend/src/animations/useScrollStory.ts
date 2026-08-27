import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Drives the cinematic landing: a normalized 0..1 scroll progress (consumed by
 * the 3D camera) plus the index of the currently-active story beat.
 *
 * The 3D layer reads `progressRef.current` each frame — updated here without
 * React re-renders — while `activeIndex` drives the DOM overlay in React.
 */
export function useScrollStory(sectionCount: number) {
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);
  const progressRef = useRef(0);
  const [activeIndex, setActiveIndex] = useState(0);

  const setSectionRef = useCallback(
    (index: number) => (el: HTMLElement | null) => {
      sectionRefs.current[index] = el;
    },
    []
  );

  useEffect(() => {
    let raf = 0;

    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const vh = window.innerHeight;
        const doc = document.documentElement;
        const max = Math.max(1, doc.scrollHeight - vh);
        progressRef.current = Math.min(1, Math.max(0, window.scrollY / max));

        // Which section owns the midpoint of the viewport?
        for (let i = sectionCount - 1; i >= 0; i--) {
          const el = sectionRefs.current[i];
          if (el) {
            const rect = el.getBoundingClientRect();
            if (rect.top <= vh * 0.5) {
              setActiveIndex(i);
              break;
            }
          }
        }
      });
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [sectionCount]);

  return { progressRef, activeIndex, setSection: setSectionRef };
}