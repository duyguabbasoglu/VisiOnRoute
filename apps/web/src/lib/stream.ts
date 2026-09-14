import { openAuthorizedStream } from "./api";

export type StreamStatus = "connecting" | "live" | "fallback";

export interface StreamHandlers {
  onEvent: (event: string, data: string) => void;
  onStatus: (status: StreamStatus) => void;
}

export interface ParsedEvent {
  event: string;
  data: string;
}

/** Parse one server-sent-event block (lines separated by "\n"). */
export function parseEventBlock(block: string): ParsedEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length > 0 ? { event, data: data.join("\n") } : null;
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

/**
 * Subscribe to a server-sent-event endpoint with the session's access token.
 * Reconnects when the server ends the stream, backs off on errors and reports
 * "fallback" so callers keep polling while the stream is unavailable. Stops
 * retrying on 401/403 (session or permission problem; polling surfaces it).
 */
export function subscribeToStream(path: string, handlers: StreamHandlers): () => void {
  const controller = new AbortController();
  let failures = 0;

  const run = async () => {
    while (!controller.signal.aborted) {
      try {
        const response = await openAuthorizedStream(path, controller.signal);
        if (response.status === 401 || response.status === 403) {
          handlers.onStatus("fallback");
          return;
        }
        if (!response.ok || !response.body) throw new Error("stream_unavailable");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
          let boundary = buffer.indexOf("\n\n");
          while (boundary >= 0) {
            const parsed = parseEventBlock(buffer.slice(0, boundary));
            buffer = buffer.slice(boundary + 2);
            if (parsed) {
              failures = 0;
              handlers.onStatus("live");
              handlers.onEvent(parsed.event, parsed.data);
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch {
        if (controller.signal.aborted) return;
        failures += 1;
        handlers.onStatus("fallback");
        await wait(Math.min(30_000, 1000 * 2 ** failures), controller.signal);
      }
    }
  };

  handlers.onStatus("connecting");
  void run();
  return () => controller.abort();
}
