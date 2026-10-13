import { createServer, type Server } from "node:http";
import { Ledger, LedgerError, parseOpen, parseStep } from "./ledger.ts";

export function createLedgerServer(ledger: Ledger): Server {
  return createServer(async (req, res) => {
    const send = (status: number, value: unknown) => {
      res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(value));
    };
    try {
      const path = new URL(req.url ?? "/", "http://localhost").pathname;
      const match = /^\/sessions\/([0-9a-f]{64})(?:\/(steps|checkpoint|close|abort))?$/.exec(path);
      if (req.method === "POST" && path === "/sessions") return send(201, await ledger.open(parseOpen(await body(req))));
      if (match) {
        const [, id, action] = match;
        if (req.method === "GET" && !action) return send(200, ledger.snapshot(id));
        if (req.method === "POST" && action === "steps") return send(202, ledger.enqueue(id, parseStep(await body(req), id)));
        if (req.method === "POST" && action === "checkpoint") return send(200, await ledger.checkpoint(id));
        if (req.method === "POST" && action === "close") return send(200, await ledger.close(id));
        if (req.method === "POST" && action === "abort") return send(200, await ledger.abort(id));
      }
      send(404, { error: "Not found" });
    } catch (error) {
      send(error instanceof LedgerError ? error.status : 503, { error: String(error instanceof Error ? error.message : error) });
    }
  });
}

async function body(req: import("node:http").IncomingMessage): Promise<unknown> {
  let raw = "";
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 65536) throw new LedgerError(413, "Body too large");
  }
  try { return JSON.parse(raw); }
  catch { throw new LedgerError(400, "Invalid JSON"); }
}
