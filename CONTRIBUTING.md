# Contributing

## Validate your change

```bash
npx @redocly/cli lint openapi.yaml
```

Redocly rather than Spectral: this is an OpenAPI **3.1** document, and
Spectral's `oas` ruleset crashes on 3.1 nullable type-arrays combined with
`enum` (`type: [integer, "null"], enum: [1, 2, null]`), which this spec uses
throughout.

CI additionally asserts structural invariants the SDKs depend on:

- every authenticated operation documents a `401` (`/health` is exempt — it
  takes no auth)
- every operation has a unique `operationId` — generated clients name their
  methods from it, so renaming one is a **breaking change**
- the `bearerAuth` and `apiKeyHeader` schemes both still exist
- the server URL is unchanged

## Versioning

Changes within `v1` are **additive only**: new endpoints, new optional fields.
Removing a field or changing its type requires `v2`, because every official SDK
promises callers that unknown fields are safe to ignore.

## Reporting a mismatch

If the live API returns something this spec doesn't describe, that's a bug in
the spec. Open an issue with the endpoint, the request, and the raw response.
