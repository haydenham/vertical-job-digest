import { useLayoutEffect, type RefObject } from "react";

// Scroll-reveal fallback for browsers without CSS scroll-driven animations.
//
// The primary path is pure CSS (`animation-timeline: view()` in theme.css, inside @supports) —
// it runs off the compositor and needs no JS at all. This hook exists only for browsers that
// lack it, and it deliberately does nothing when the native path is available.
//
// Two safety properties matter more than the animation itself:
//   1. Nothing is hidden unless something is guaranteed to bring it back. The `js-reveal` class
//      is what arms the hidden state in CSS, and it is only ever set after we know we have an
//      IntersectionObserver to un-hide with. No JS, no observer, no support → the page renders
//      its finished state.
//   2. Each element is unobserved the moment it fires, so scrolling back up never re-animates it.
const SUPPORTS_NATIVE_TIMELINE =
  typeof CSS !== "undefined" &&
  typeof CSS.supports === "function" &&
  CSS.supports("animation-timeline: view()");

export function useScrollReveal(containerRef: RefObject<HTMLElement | null>): void {
  // Layout effect, not a plain effect: `js-reveal` has to land before the browser paints, or the
  // content flashes in at full opacity and then hides itself to animate.
  useLayoutEffect(() => {
    if (SUPPORTS_NATIVE_TIMELINE) return;
    if (typeof IntersectionObserver === "undefined") return;
    const container = containerRef.current;
    if (!container) return;

    const root = document.documentElement;
    root.classList.add("js-reveal");

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-revealed");
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.15 },
    );
    container.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

    return () => {
      observer.disconnect();
      root.classList.remove("js-reveal");
    };
  }, [containerRef]);
}
