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

## Code samples

Every operation in `openapi.yaml` carries an `x-codeSamples` list: a curl
call, then one sample for each official client that has a method for it.
The interactive reference shows them in each operation's language picker.

Do not edit those blocks by hand. They are built from
`code-samples/sdk-methods.yaml`, which names the method and the call of each
client for each `operationId`. After you add an operation, or after a client
release adds a method, update that file and run:

```bash
python scripts/build_code_samples.py              # rewrite the samples in openapi.yaml
python scripts/build_code_samples.py --coverage   # which client covers which operation
python scripts/build_reference.py                 # rebuild the docs
```

Read each method name from the client's source at its released version. A
client with no method for an operation gets no entry, so its sample is left
out. `scripts/build_reference.py --check` fails in CI when an operation has no
entry. It also fails when an entry names an operation the spec does not
define, or when the samples are stale. `python -m unittest scripts/test_build_code_samples.py`
breaks copies of both files and checks that each of those failures is caught.

## Versioning

Changes within `v1` are **additive only**: new endpoints, new optional fields.
Removing a field or changing its type requires `v2`, because every official SDK
promises callers that unknown fields are safe to ignore.

## Reporting a mismatch

If the live API returns something this spec doesn't describe, that's a bug in
the spec. Open an issue with the endpoint, the request, and the raw response.
