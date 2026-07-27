import { render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useScrollReveal } from "./useScrollReveal";

// jsdom ships no IntersectionObserver, which is also exactly the condition the hook's safety
// path guards against — so the default environment tests the "never hide it" branch for free,
// and this stand-in tests the branch that actually animates.
class FakeObserver {
  static instances: FakeObserver[] = [];
  readonly observed = new Set<Element>();
  readonly unobserved: Element[] = [];
  disconnected = false;

  constructor(
    private readonly callback: IntersectionObserverCallback,
    readonly options?: IntersectionObserverInit,
  ) {
    FakeObserver.instances.push(this);
  }

  observe(el: Element) {
    this.observed.add(el);
  }
  unobserve(el: Element) {
    this.observed.delete(el);
    this.unobserved.push(el);
  }
  disconnect() {
    this.disconnected = true;
    this.observed.clear();
  }

  intersect(el: Element) {
    this.callback([{ target: el, isIntersecting: true } as IntersectionObserverEntry], this as never);
  }
}

function Fixture() {
  const ref = useRef<HTMLDivElement>(null);
  useScrollReveal(ref);
  return (
    <div ref={ref}>
      <p className="reveal" data-testid="first">
        first
      </p>
      <p className="reveal" data-testid="second">
        second
      </p>
      <p data-testid="plain">not a reveal target</p>
    </div>
  );
}

function installFakeObserver() {
  FakeObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", FakeObserver);
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.classList.remove("js-reveal");
});

describe("useScrollReveal", () => {
  it("never arms the hidden state when there is no IntersectionObserver to un-hide with", () => {
    // No stub: this is jsdom's real environment, and stands in for any browser lacking both
    // paths. Hiding content here would leave the landing page permanently blank.
    render(<Fixture />);
    expect(document.documentElement).not.toHaveClass("js-reveal");
  });

  it("observes only .reveal elements inside the container, at threshold 0.15", () => {
    installFakeObserver();
    const { getByTestId } = render(<Fixture />);

    expect(document.documentElement).toHaveClass("js-reveal");
    const observer = FakeObserver.instances[0];
    expect(observer.options).toEqual({ threshold: 0.15 });
    expect([...observer.observed]).toEqual([getByTestId("first"), getByTestId("second")]);
    expect(observer.observed.has(getByTestId("plain"))).toBe(false);
  });

  it("reveals an element once and stops watching it, so scrolling back up never replays it", () => {
    installFakeObserver();
    const { getByTestId } = render(<Fixture />);
    const observer = FakeObserver.instances[0];
    const first = getByTestId("first");

    observer.intersect(first);

    expect(first).toHaveClass("is-revealed");
    expect(observer.unobserved).toEqual([first]);
    expect(observer.observed.has(first)).toBe(false);
    // its sibling is untouched until it intersects on its own
    expect(getByTestId("second")).not.toHaveClass("is-revealed");
  });

  it("disconnects and disarms the hidden state on unmount", () => {
    installFakeObserver();
    const { unmount } = render(<Fixture />);

    unmount();

    expect(FakeObserver.instances[0].disconnected).toBe(true);
    expect(document.documentElement).not.toHaveClass("js-reveal");
  });

  it("stays out of the way entirely when the browser has native scroll timelines", async () => {
    // The support check runs at module load, so the stub has to precede a fresh import.
    vi.stubGlobal("CSS", { supports: (q: string) => q === "animation-timeline: view()" });
    installFakeObserver();
    vi.resetModules();
    const { useScrollReveal: freshHook } = await import("./useScrollReveal");

    function NativeFixture() {
      const ref = useRef<HTMLDivElement>(null);
      freshHook(ref);
      return (
        <div ref={ref}>
          <p className="reveal">first</p>
        </div>
      );
    }
    render(<NativeFixture />);

    expect(FakeObserver.instances).toHaveLength(0);
    expect(document.documentElement).not.toHaveClass("js-reveal");
  });
});
