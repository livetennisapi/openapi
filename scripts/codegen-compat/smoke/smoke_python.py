"""Smoke call for the openapi-generator python client: GET /fixtures."""
import sys

import livetennisapi_gen as gen

cfg = gen.Configuration(host=sys.argv[1], access_token="test-key")
with gen.ApiClient(cfg) as client:
    page = gen.DefaultApi(client).list_fixtures(limit=3)
row = page.data[0]
assert row.tournament == "Rome", row
assert len(page.data) == 3, page
print(f"python smoke ok: {len(page.data)} fixtures, first {row.player1_name} v {row.player2_name}")
