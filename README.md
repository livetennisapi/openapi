<div align="center">

<img src="https://raw.githubusercontent.com/livetennisapi/.github/main/profile/banner.jpg" alt="Live Tennis API" width="640">

# OpenAPI Specification

The machine-readable contract for **[Live Tennis API](https://livetennisapi.com)** — real-time
tennis scores, players, rankings, match-winner market prices and model win-probability
over REST and WebSocket, across ATP, WTA, Challenger, ITF and juniors.

[![lint](https://github.com/livetennisapi/openapi/actions/workflows/lint.yml/badge.svg)](https://github.com/livetennisapi/openapi/actions/workflows/lint.yml)
[![pages](https://github.com/livetennisapi/openapi/actions/workflows/pages.yml/badge.svg)](https://github.com/livetennisapi/openapi/actions/workflows/pages.yml)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)

[**Documentation**](https://docs.livetennisapi.com) · [**Website**](https://livetennisapi.com) · [**Get a free key**](https://livetennisapi.com/subscribe/free) · [**Pricing**](https://livetennisapi.com/#pricing) · [**Discord**](https://discord.gg/f8WUZHgDm6)

</div>

---

## What's here

| File | Purpose |
|---|---|
| [`openapi.yaml`](openapi.yaml) | The specification — OpenAPI 3.1.0, 35 operations (34 paths), 37 schemas |
| [`docs/`](docs/) | Rendered reference, published to <https://docs.livetennisapi.com> |

The spec is the **source of truth** for our official SDKs. If the spec and an SDK disagree,
the spec is right and the SDK has a bug.

## Use it

Point any OpenAPI-compatible tool at the raw file:

```
https://raw.githubusercontent.com/livetennisapi/openapi/main/openapi.yaml
```

Generate a client in your language of choice:

```bash
# openapi-generator
openapi-generator generate \
  -i https://raw.githubusercontent.com/livetennisapi/openapi/main/openapi.yaml \
  -g go -o ./livetennis-go
```

Or import it into Postman, Insomnia, Bruno, Hoppscotch, or Scalar directly.

> **Prefer an official SDK?** They handle auth, retries, pagination, tier errors and the
> WebSocket feed for you. See the [organisation profile](https://github.com/livetennisapi)
> for the current list.

## Quick reference

**Base URL** — `https://api.livetennisapi.com/api/public/v1`

**Auth** — `Authorization: Bearer` is preferred; the `X-API-Key` header also works,
and the WebSocket feed additionally accepts `?token=` for header-less clients:

```
Authorization: Bearer twjp_…
X-API-Key: twjp_…
```

**Tiers** — FREE (live & upcoming matches, scores, players, fixtures, tournaments,
your own usage stats — self-serve, no card:
<https://livetennisapi.com/subscribe/free>) · BASIC (+ history in two halves: the
point-by-point tape (2023→now) and the results archive (1968–2022) with `/h2h` and
career aggregates) · PRO (+ events, market prices, bulk packages, the rankings
listing) · ULTRA (+ analysis, model fields, in-play statistics, per-player as-of
rankings, rally construction, shot-level charting, WebSocket + the `/ws-token`
push feed, webhooks).
Calling above your tier returns `403 {"error":"upgrade_required"}`.

**Quotas**

| Tier | Requests/min | Requests/day |
|---|---|---|
| FREE | 30 | 100 |
| BASIC | 60 | 1,000 |
| PRO | 300 | 10,000 |
| ULTRA | 600 | 500,000 |

On a FREE key (100/day), poll no faster than every 15 minutes; an always-on
dashboard should run on BASIC or above. Going over returns `429` with a
`Retry-After` header — the body says whether the minute limit or the daily
quota tripped (`resets_at` gives the exact daily reset instant).

**Conventions**

- Timestamps are UTC ISO 8601 with a `Z` suffix.
- Lists return `{data, meta}`; single resources return the object directly.
- `limit` defaults to 50, caps at 200; paginate with `offset`.
- **Ignore unknown fields.** Additive changes ship within `v1` — a client that rejects
  unrecognised fields will break. Every official SDK parses permissively for this reason.

## Versioning

The spec is versioned alongside the API's `v1` surface. Changes within `v1` are **additive
only** — new endpoints, new optional fields. Removing a field or changing its type would
require `v2`.

CI lints every change with [Redocly CLI](https://redocly.com/docs/cli/) and runs a
structural contract check (server URL, both auth schemes, `operationId` on every
operation, a documented 401 on every authenticated operation) on every push.

## Contributing

Found a mismatch between this spec and what the API actually returns? That's a bug worth
reporting — [open an issue](https://github.com/livetennisapi/openapi/issues) with the
endpoint, the request, and the response you got.

## Related

Everything in the Live Tennis API developer surface:

| | Install | Source | Package |
|---|---|---|---|
| Python client | `pip install livetennisapi` | [repo](https://github.com/livetennisapi/livetennisapi-python) | [package](https://pypi.org/project/livetennisapi/) |
| JavaScript / TypeScript client | `npm install livetennisapi` | [repo](https://github.com/livetennisapi/livetennisapi-js) | [package](https://www.npmjs.com/package/livetennisapi) |
| MCP server for LLM agents | `npx livetennisapi-mcp` | [repo](https://github.com/livetennisapi/livetennisapi-mcp) | [package](https://www.npmjs.com/package/livetennisapi-mcp) |

- **API reference** — <https://docs.livetennisapi.com> ([plain-HTML version](https://docs.livetennisapi.com/reference.html), no JavaScript required)
- **Website and plans** — <https://livetennisapi.com>
- **Get a free key** — <https://livetennisapi.com/subscribe/free>
- **Discord** — <https://discord.gg/f8WUZHgDm6>
- **GitHub organisation** — <https://github.com/livetennisapi>

## Licence

The specification document in this repository is MIT licensed — generate clients, vendor
it, do what you like with it.

Use of the **API service itself** is governed by the
[Terms of Service](https://livetennisapi.com/terms).

## Affiliate program

Know developers who need tennis data? The [affiliate program](https://affiliates.livetennisapi.com/program) pays 51% recurring commission for the life of every referred subscription — 30-day cookie, and the people you refer get 10% off.
