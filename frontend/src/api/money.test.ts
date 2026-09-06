import { describe, expect, it } from "vitest";
import {
  add, dec, delta, formatAmount, formatCompact, formatExact, formatMoney, formatPct,
  formatQty, formatScore, riskBandFor, sortKey, sub,
} from "./money";

/**
 * Money is the one place a rendering bug becomes a correctness bug, so these
 * assert against the exact strings the backend returns for the canonical
 * seeded quote.
 */
describe("decimal handling", () => {
  it("never loses precision the way a float would", () => {
    // The classic float failure, which must not occur here.
    expect(0.1 + 0.2).not.toBe(0.3);
    expect(add("0.1", "0.2")).toBe("0.3");
    expect(sub("132710.00", "124310.00")).toBe("8400");
  });

  it("treats empty and null as zero rather than NaN", () => {
    expect(dec(null).toString()).toBe("0");
    expect(dec(undefined).toString()).toBe("0");
    expect(dec("").toString()).toBe("0");
    expect(formatAmount(null)).toBe("0.00");
  });

  it("preserves the backend's full precision for inspection", () => {
    expect(formatExact("24.4970")).toBe("24.497");
    expect(formatExact("0.00000001")).toBe("1e-8");
  });
});

describe("formatting the canonical quote", () => {
  it("groups money to two decimal places", () => {
    expect(formatAmount("160800.00")).toBe("160,800.00");
    expect(formatAmount("132710.00")).toBe("132,710.00");
    expect(formatAmount("100200.00")).toBe("100,200.00");
    expect(formatAmount("32510.00")).toBe("32,510.00");
    expect(formatMoney("124310.00")).toBe("$124,310.00");
  });

  it("renders percentages at display precision without mutating the source", () => {
    expect(formatPct("24.4970")).toBe("24.50%");
    expect(formatPct("19.3951")).toBe("19.40%");
    expect(formatPct("24.4970", 4)).toBe("24.4970%");
  });

  it("renders risk scores at one decimal", () => {
    expect(formatScore("32.4440")).toBe("32.4");
    expect(formatScore("51.3557", 2)).toBe("51.36");
  });

  it("trims trailing zeros from quantities", () => {
    expect(formatQty("100.0000")).toBe("100");
    expect(formatQty("1.5000")).toBe("1.5");
    expect(formatQty("0.0000")).toBe("0");
  });

  it("compacts large values for tight layouts", () => {
    expect(formatCompact("132710.00")).toBe("$132.7k");
    expect(formatCompact("1327100.00")).toBe("$1.33M");
  });

  it("signs a delta and uses a real minus sign", () => {
    // v1 -> v2 after the 25% counter-offer
    expect(delta("132710.00", "124310.00")).toBe("\u22128,400.00");
    expect(delta("124310.00", "132710.00")).toBe("+8,400.00");
    // No movement renders unsigned, so an unchanged field reads as "0.00".
    expect(delta("100.00", "100.00")).toBe("0.00");
  });
});

describe("risk banding matches the backend thresholds", () => {
  it("bands the canonical scores", () => {
    expect(riskBandFor("32.4440")).toBe("MEDIUM"); // v1
    expect(riskBandFor("51.3557")).toBe("HIGH"); // v2 after the counter
  });

  it("bands the boundaries inclusively upward", () => {
    expect(riskBandFor("0")).toBe("NONE");
    expect(riskBandFor("0.0001")).toBe("LOW");
    expect(riskBandFor("24.9999")).toBe("LOW");
    expect(riskBandFor("25")).toBe("MEDIUM");
    expect(riskBandFor("50")).toBe("HIGH");
    expect(riskBandFor("75")).toBe("CRITICAL");
  });
});

describe("sortKey", () => {
  it("orders money correctly", () => {
    const rows = ["132710.00", "9750.00", "124310.00", "41000.00"];
    expect([...rows].sort((a, b) => sortKey(a) - sortKey(b))).toEqual([
      "9750.00", "41000.00", "124310.00", "132710.00",
    ]);
  });
});
