import { describe, expect, it } from "vitest";
import { parseEventBlock } from "./stream";

describe("parseEventBlock", () => {
  it("parses named events with data", () => {
    expect(parseEventBlock('event: live\ndata: [{"a":1}]')).toEqual({ event: "live", data: '[{"a":1}]' });
  });

  it("joins multi-line data and defaults the event name", () => {
    expect(parseEventBlock("data: satır 1\ndata: satır 2")).toEqual({ event: "message", data: "satır 1\nsatır 2" });
  });

  it("ignores comments, retry hints and empty blocks", () => {
    expect(parseEventBlock(": keepalive")).toBeNull();
    expect(parseEventBlock("retry: 5000")).toBeNull();
    expect(parseEventBlock("")).toBeNull();
  });
});
