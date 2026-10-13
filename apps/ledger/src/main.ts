import { anchorChainFromEnv } from "./anchor-chain.ts";
import { createLedgerServer } from "./http.ts";
import { Ledger } from "./ledger.ts";

const chain = await anchorChainFromEnv();
const port = Number(process.env.LOOPRAIL_LEDGER_PORT ?? "8787");
createLedgerServer(new Ledger(chain)).listen(port, "127.0.0.1", () => {
  console.log(`LoopRail ledger listening on http://127.0.0.1:${port}`);
});
