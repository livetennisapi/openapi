# Code generator compatibility

Run on 8 November 2026 against `docs/openapi.json`, spec version 1.13.78 (OpenAPI 3.1.0).
Every target generated a client that builds and completes the smoke call. Three of the
seven needed a fix first, listed below. The raw rows are in
[codegen-compat.csv](codegen-compat.csv).

To repeat the run:

```bash
scripts/codegen-compat/run.sh /tmp/codegen-work results/codegen-compat.csv
```

## Results

| Generator | Version | Target | As generated | With the fix |
|---|---|---|---|---|
| openapi-generator | 7.27.0 | python | generates, imports, smoke call passes | no fix needed |
| openapi-generator | 7.27.0 | typescript-fetch | generates, type-checks, smoke call passes | no fix needed |
| openapi-generator | 7.27.0 | go | generates, does not build | builds, smoke call passes |
| openapi-generator | 7.27.0 | java | generates, compiles, smoke call passes | no fix needed |
| openapi-generator | 7.27.0 | csharp | generates, does not build | builds, smoke call passes |
| openapi-typescript | 7.13.0 | TypeScript types | generates, type-checks, smoke call passes | no fix needed |
| oapi-codegen | v2.8.2 | go | does not generate | generates, builds, smoke call passes |

## What each step means

Generate means the generator exits 0 on the spec. openapi-generator ran from the
`openapitools/openapi-generator-cli:v7.27.0` image, and it logs that its OpenAPI 3.1
support is in beta.

Build depends on the language. Python is installed into a fresh venv, byte-compiled and
imported. Both TypeScript outputs pass `tsc` 5.9.3 with `strict` on. Go runs `go build` and
`go vet` on go1.27.3. Java runs `mvn package` in `maven:3.9.16-eclipse-temurin-21`, and C#
runs `dotnet build` with SDK 10.0.403.

The smoke call is one `GET /fixtures?limit=3` with a dummy bearer key, against
`scripts/codegen-compat/mock_server.py` on localhost. The mock serves a recorded API
response, taken from the Go client's test data (committed 22 July 2026), and refuses a
request without a key. The call passes when the client sends a key, parses three rows and
reads `tournament` as `Rome`. No live API call was made and no key was used.

## The fixes

**openapi-generator, go.** `MatchDetail` is `Match` plus `analysis` and `market`, and
`Match` already has `has_analysis` and `has_market`. The generator names the field
`HasAnalysis` and also writes a `HasAnalysis()` method that reports whether `analysis` is
set, so the package does not compile. `HasMarket` clashes the same way. Rename the two
fields:

```bash
--name-mappings has_analysis=HasAnalysisFlag,has_market=HasMarketFlag
```

**openapi-generator, csharp.** The generated `ClientUtils.cs` uses
`System.Text.RegularExpressions.Match`, which collides with our `Match` model. Rename the
model:

```bash
--model-name-mappings Match=MatchModel
```

The default `generichost` library also refuses to build `DefaultApi` until a token is
registered for both of the spec's schemes, bearer and `X-API-Key`. With both registered it
sends both headers. The API accepts either one.

**oapi-codegen.** It reads OpenAPI 3.0 through kin-openapi and stops twice on our 3.1
document. First, the `player` query parameter and the `Player` schema both become the Go
type `Player`. With that renamed, it stops on a nullable enum such as
`server: {type: [integer, "null"], enum: [1, 2, null]}`, because it cannot write `null` as a
Go constant. `scripts/codegen-compat/oapi_codegen_prep.py` writes a copy of the spec with
`x-go-name: PlayerIDs` on the parameter and `null` removed from those enums. The
`type` arrays still mark the fields as nullable. The API itself is unchanged.

## Limits

One run on one machine, with the versions above. A pass means the client built and one
read worked against a recorded response. It does not cover every endpoint, every model or
the push feed.
