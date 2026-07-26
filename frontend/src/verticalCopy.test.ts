import { describe, expect, it } from "vitest";

import { verticalCopy } from "./verticalCopy";

describe("verticalCopy", () => {
  it("maps known slugs to display copy", () => {
    expect(verticalCopy("grid_power_software").name).toBe("Energy & grid");
    expect(verticalCopy("aviation_software").name).toBe("Aviation Technology");
    expect(verticalCopy("aviation_software").blurb).toMatch(/flight data/i);
    expect(verticalCopy("robotics_software").name).toBe("Robotics");
    expect(verticalCopy("trading_software").name).toBe("Trading & Markets");
    expect(verticalCopy("trading_software").blurb).toMatch(/quant funds/i);
  });

  it("prettifies unknown slugs so a new vertical renders without a frontend release", () => {
    expect(verticalCopy("quantum_computing")).toEqual({ name: "Quantum computing", blurb: "" });
  });
});
