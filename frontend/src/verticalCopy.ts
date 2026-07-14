// Display copy for vertical slugs (UI rework PR 2, D-080). `GET /api/verticals` returns raw
// config slugs and the API contract is frozen for this block, so the human name + blurb live
// here, keyed by slug. Unknown slugs prettify ("foo_bar" → "Foo bar") with an empty blurb, so a
// new vertical's config landing never blocks on a frontend release — it ships without a blurb
// until its copy is added below.
export interface VerticalCopy {
  name: string;
  blurb: string;
}

const COPY: Record<string, VerticalCopy> = {
  aviation_software: {
    name: "Aviation Technology",
    blurb:
      "Airline ops and tech arms, flight data and tracking, avionics, and the platforms behind them.",
  },
  grid_power_software: {
    name: "Energy & grid",
    blurb:
      "Grid operators, power-market software, storage and DER, nuclear, and utility innovation arms.",
  },
  robotics_software: {
    name: "Robotics",
    blurb: "Autonomy, industrial robotics, and the software that moves real machines.",
  },
};

export function verticalCopy(slug: string): VerticalCopy {
  const known = COPY[slug];
  if (known) return known;
  const pretty = slug.replaceAll("_", " ").trim();
  return { name: pretty.charAt(0).toUpperCase() + pretty.slice(1), blurb: "" };
}
