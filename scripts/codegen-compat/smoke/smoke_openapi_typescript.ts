// Smoke call for openapi-typescript: the generated types drive openapi-fetch. GET /fixtures.
import createClient from "openapi-fetch";
import type { paths } from "./schema.js";

async function main(): Promise<void> {
  const client = createClient<paths>({ baseUrl: process.argv[2], headers: { Authorization: "Bearer test-key" } });
  const { data, error } = await client.GET("/fixtures", { params: { query: { limit: 3 } } });
  const rows = data?.data ?? [];
  if (error || rows.length !== 3 || rows[0].tournament !== "Rome") throw new Error(JSON.stringify(error ?? data));
  console.log(`openapi-typescript smoke ok: ${rows.length} fixtures, first ${rows[0].player1_name} v ${rows[0].player2_name}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
