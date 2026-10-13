import type { OpenSession, Step } from "./types.ts";

export class LedgerClient {
  private baseUrl: string;
  constructor(baseUrl: string) { this.baseUrl = baseUrl; }
  private async request(path: string, method = "GET", body?: unknown) {
    const response = await fetch(new URL(path, this.baseUrl), {
      method, headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(`Ledger ${response.status}: ${result.error}`);
    return result;
  }
  open(input: OpenSession) { return this.request("/sessions", "POST", input); }
  step(id: string, step: Step) { return this.request(`/sessions/${id}/steps`, "POST", step); }
  session(id: string) { return this.request(`/sessions/${id}`); }
  checkpoint(id: string) { return this.request(`/sessions/${id}/checkpoint`, "POST"); }
  close(id: string) { return this.request(`/sessions/${id}/close`, "POST"); }
  abort(id: string) { return this.request(`/sessions/${id}/abort`, "POST"); }
}
