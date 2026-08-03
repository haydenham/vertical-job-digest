/**
 * Guards the favicon set, which nothing else can catch: a bad `href` costs a blank tab, and a blank
 * tab is silent — every test still passes, the build still succeeds, and only a human looking at a
 * browser notices. So this asserts on the files themselves rather than on a component.
 *
 * Vite's `?raw` + `import.meta.glob` do the reading (not `node:fs`), so the suite needs no
 * `@types/node` and stays a browser-target module like every other file in `src/`.
 */
import { describe, expect, it } from "vitest";

import themeCss from "./theme.css?raw";
import indexHtml from "../index.html?raw";
import manifestRaw from "../public/site.webmanifest?raw";

/** Every file Vite will copy to `dist/` root, keyed the way the browser will request it. */
const publicFiles = new Set(
  Object.keys(import.meta.glob("../public/*")).map((path) => path.replace("../public", "")),
);

/** `href`s of the head's icon/manifest links — the ones that must resolve to a real file. */
const linkedHrefs = [...indexHtml.matchAll(/<link\b[^>]*>/g)]
  .map(([tag]) => tag)
  .filter((tag) => /rel="(icon|apple-touch-icon|manifest)"/.test(tag))
  .map((tag) => /href="([^"]+)"/.exec(tag)?.[1]);

const manifest = JSON.parse(manifestRaw) as {
  name: string;
  short_name: string;
  theme_color: string;
  background_color: string;
  icons: { src: string }[];
};

describe("favicon assets", () => {
  it("links the four icons/manifest from index.html", () => {
    expect(linkedHrefs).toEqual([
      "/apple-touch-icon.png",
      "/favicon-32x32.png",
      "/favicon-16x16.png",
      "/site.webmanifest",
    ]);
  });

  it("resolves every linked href to a file that ships", () => {
    for (const href of linkedHrefs) expect(publicFiles).toContain(href);
  });

  it("resolves every manifest icon to a file that ships", () => {
    expect(manifest.icons.length).toBeGreaterThan(0);
    for (const icon of manifest.icons) expect(publicFiles).toContain(icon.src);
  });

  it("ships favicon.ico even though nothing links it", () => {
    // Browsers request /favicon.ico at the root on their own; it is the legacy fallback, which is
    // exactly why it has no <link> to catch its deletion.
    expect(publicFiles).toContain("/favicon.ico");
  });

  it("names the app in the manifest", () => {
    // favicon.io generates these empty; an empty name is what a re-download would reintroduce.
    expect(manifest.name).toBe("Rolefeed");
    expect(manifest.short_name).toBe("Rolefeed");
  });
});

describe("browser chrome colour", () => {
  // The dark background lives in four places and cannot live in one: neither index.html nor a JSON
  // manifest can read a CSS custom property. This is what keeps them in step with the palette.
  const bg = /^\s*--bg:\s*(#[0-9a-f]{6});/im.exec(themeCss)?.[1];
  const themeColorMeta = /<meta\s+name="theme-color"\s+content="([^"]+)"/.exec(indexHtml)?.[1];

  it("matches --bg in theme.css everywhere it is duplicated", () => {
    expect(bg).toBeDefined();
    expect(themeColorMeta).toBe(bg);
    expect(manifest.theme_color).toBe(bg);
    expect(manifest.background_color).toBe(bg);
  });
});
