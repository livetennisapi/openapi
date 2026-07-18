<div align="center">

<img src="https://raw.githubusercontent.com/livetennisapi/.github/main/profile/banner.jpg" alt="Live Tennis API" width="640">

# OpenAPI Specification

The machine-readable contract for **[Live Tennis API](https://livetennisapi.com)** — real-time
tennis scores, players, rankings, match-winner market prices and model win-probability
over REST and WebSocket.

[**Documentation**](https://docs.livetennisapi.com) · [**Website**](https://livetennisapi.com) · [**Get a key**](https://livetennisapi.com/#pricing)

</div>

---

## What's here

| File | Purpose |
|---|---|
| [`openapi.yaml`](openapi.yaml) | The specification — OpenAPI 3.1.0, 12 endpoints, 11 schemas |
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

**Auth** — either header works:

```
Authorization: Bearer twjp_…
X-API-Key: twjp_…
```

**Tiers** — BASIC (matches, scores, players, fixtures, history) · PRO (+ events, markets)
· ULTRA (+ analysis, model fields, WebSocket). Calling above your tier returns
`403 {"error":"upgrade_required"}`.

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

CI lints every change with [Spectral](https://github.com/stoplightio/spectral) and fails
the build on a breaking diff against `main`.

## Contributing

Found a mismatch between this spec and what the API actually returns? That's a bug worth
reporting — [open an issue](https://github.com/livetennisapi/openapi/issues) with the
endpoint, the request, and the response you got.

## Licence

The specification document in this repository is MIT licensed — generate clients, vendor
it, do what you like with it.

Use of the **API service itself** is governed by the
[Terms of Service](https://livetennisapi.com/terms).
