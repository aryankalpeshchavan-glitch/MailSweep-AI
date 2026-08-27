import { describe, expect, it } from "vitest";
import { formatNumber, formatPercent, humanize, riskLabel, timeAgo } from "./format";

describe("formatNumber", () => {
  it("formats with thousands separators", () => {
    expect(formatNumber(1234)).toBe("1,234");
  });
  it("returns an em dash for null/undefined/NaN", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(Number.NaN)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("rounds a 0..1 fraction to a whole percent", () => {
    expect(formatPercent(0.8642)).toBe("86%");
  });
  it("handles null", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

describe("humanize", () => {
  it("title-cases snake_case tokens", () => {
    expect(humanize("MOVE_TO_TRASH")).toBe("Move To Trash");
  });
  it("returns em dash for empty input", () => {
    expect(humanize(null)).toBe("—");
    expect(humanize("")).toBe("—");
  });
});

describe("riskLabel", () => {
  it("maps known levels to friendly labels", () => {
    expect(riskLabel("LOW")).toBe("Low");
    expect(riskLabel("MEDIUM")).toBe("Medium");
    expect(riskLabel("HIGH")).toBe("High");
  });
  it("falls back to humanize for unknown levels", () => {
    expect(riskLabel("CATASTROPHIC")).toBe("Catastrophic");
  });
  it("returns an em dash for null", () => {
    expect(riskLabel(null)).toBe("—");
  });
});

describe("timeAgo", () => {
  const now = Date.now();
  it("returns 'just now' for recent timestamps", () => {
    expect(timeAgo(new Date(now - 5_000).toISOString())).toBe("just now");
  });
  it("returns day/month/year relative labels", () => {
    expect(timeAgo(new Date(now - 3 * 86_400_000).toISOString())).toBe("3d ago");
    expect(timeAgo(new Date(now - 40 * 86_400_000).toISOString())).toBe("1mo ago");
    expect(timeAgo(new Date(now - 400 * 86_400_000).toISOString())).toBe("1y ago");
  });
  it("returns an em dash for invalid / missing input", () => {
    expect(timeAgo(null)).toBe("—");
    expect(timeAgo("not-a-date")).toBe("—");
  });
});
