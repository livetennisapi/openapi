// Smoke call for the openapi-generator typescript-fetch client: GET /fixtures.
import { Configuration, DefaultApi } from "./gen/index";

async function main(): Promise<void> {
  const api = new DefaultApi(new Configuration({ basePath: process.argv[2], accessToken: "test-key" }));
  const page = await api.listFixtures({ limit: 3 });
  const row = page.data![0];
  if (row.tournament !== "Rome" || page.data!.length !== 3) throw new Error(JSON.stringify(page));
  console.log(`typescript-fetch smoke ok: ${page.data!.length} fixtures, first ${row.player1Name} v ${row.player2Name}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
