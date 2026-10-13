export type Step = {
  version: 1;
  session_id: string;
  step_index: number;
  tool: string;
  provider: string;
  outcome: "success" | "error" | "denied" | "cache_hit";
  cost_usdc_base_units: number;
  provider_latency_ms: number;
  looprail_overhead_ms: number | null;
  cache_hit: boolean;
  occurred_at: string;
  reason?: string;
  retry_count?: number;
  retry_backoff_ms?: number;
};

export type OpenSession = {
  session_id: string;
  policy_hash: string;
  budget_usdc_base_units: number;
  owner: string;
  authority: string;
  tools: string[];
  providers: string[];
};

export interface ChainPort {
  open(input: OpenSession): Promise<{ address: string; signature: string }>;
  delegate(input: OpenSession, address: string): Promise<string>;
  record(input: OpenSession, address: string, step: Step): Promise<string>;
  count(address: string): Promise<number>;
  checkpoint(input: OpenSession, address: string): Promise<string>;
  close(input: OpenSession, address: string): Promise<string>;
  abort(input: OpenSession, address: string): Promise<string>;
}
