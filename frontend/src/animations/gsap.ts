import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Register once, globally. Guarantees ScrollTrigger is available to every
// consumer without re-registering and without side effects on import twice.
if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

export { gsap, ScrollTrigger };