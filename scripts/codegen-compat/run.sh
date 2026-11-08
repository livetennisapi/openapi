#!/usr/bin/env bash
# Generate clients from docs/openapi.json with pinned generators, build each
# one, and make one smoke call (GET /fixtures) against mock_server.py.
#
#   scripts/codegen-compat/run.sh WORK_DIR [CSV_OUT]
#
# Needs docker, go, node/npm and python3 on the host. Java and C# build in
# Docker images, so neither JDK nor .NET is needed locally. No API key is
# used: the smoke call goes to a local mock serving a recorded response.
# Steps run one at a time, so the machine never holds two builds at once.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
W="${1:?usage: run.sh WORK_DIR [CSV_OUT]}"
CSV="${2:-$W/codegen-compat.csv}"
PORT="${PORT:-18765}"
BASE="http://127.0.0.1:$PORT/api/public/v1"

# Pinned versions. Change one here, rerun, and commit the new results.
OAG_IMAGE="openapitools/openapi-generator-cli:v7.27.0"
OAPI_CODEGEN="v2.8.2"
OPENAPI_TS="7.13.0"
OPENAPI_FETCH="0.17.0"
TYPESCRIPT="5.9.3"
TYPES_NODE="22"
MAVEN_IMAGE="maven:3.9.16-eclipse-temurin-21"
DOTNET_IMAGE="mcr.microsoft.com/dotnet/sdk:10.0"

mkdir -p "$W"
W="$(cd "$W" && pwd)"
cp "$REPO/docs/openapi.json" "$W/openapi.json"
RUN_DATE="$(date -u +%Y-%m-%d)"
SPEC_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["info"]["version"])' "$W/openapi.json")"
U="$(id -u):$(id -g)"

echo "run_date,generator,generator_version,target,attempt,generate,build,smoke,notes,spec_version" > "$CSV"
# row GENERATOR VERSION TARGET ATTEMPT GENERATE BUILD SMOKE NOTES
row() { echo "$RUN_DATE,$1,$2,$3,$4,$5,$6,$7,\"$8\",$SPEC_VERSION" >> "$CSV"; echo "== $1 $3 ($4): generate=$5 build=$6 smoke=$7 ${8:+[$8]}"; }
ok() { if "$@" >> "$W/run.log" 2>&1; then echo pass; else echo fail; fi; }
# why STATUS TEXT: the failure note, printed only when the step did fail.
why() { if [ "$1" = fail ]; then echo "$2"; fi; }

python3 -I "$HERE/mock_server.py" "$PORT" 2>> "$W/mock.log" &
MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
sleep 1

oag() { # oag TARGET OUTDIR [extra generator args...]
    local target="$1" out="$2"; shift 2
    rm -rf "$W/$out"
    docker run --rm -u "$U" -v "$W:/w" "$OAG_IMAGE" generate -i /w/openapi.json -g "$target" \
        -o "/w/$out" "$@" >> "$W/run.log" 2>&1
}
OAG_VERSION="$(docker run --rm "$OAG_IMAGE" version 2>/dev/null | tail -1)"

# --- openapi-generator: python ---------------------------------------------
g=$(ok oag python out-python --additional-properties=packageName=livetennisapi_gen)
rm -rf "$W/venv-py"
b=$(ok sh -c "python3 -m venv '$W/venv-py' && '$W/venv-py/bin/pip' install -q '$W/out-python' \
    && '$W/venv-py/bin/python' -m compileall -q '$W/out-python/livetennisapi_gen' \
    && '$W/venv-py/bin/python' -c 'import livetennisapi_gen'")
s=$(ok "$W/venv-py/bin/python" -I "$HERE/smoke/smoke_python.py" "$BASE")
row openapi-generator "$OAG_VERSION" python as-generated "$g" "$b" "$s" ""

# --- toolchain for both TypeScript rows -----------------------------------
mkdir -p "$W/tsenv"
( cd "$W/tsenv" && [ -f package.json ] || npm init -y >/dev/null ) >> "$W/run.log" 2>&1
( cd "$W/tsenv" && npm install --no-audit --no-fund "typescript@$TYPESCRIPT" \
    "openapi-typescript@$OPENAPI_TS" "openapi-fetch@$OPENAPI_FETCH" "@types/node@$TYPES_NODE" ) >> "$W/run.log" 2>&1
TSC="$W/tsenv/node_modules/.bin/tsc"

# --- openapi-generator: typescript-fetch -----------------------------------
g=$(ok oag typescript-fetch out-typescript-fetch)
rm -rf "$W/ts-fetch" && mkdir -p "$W/ts-fetch"
cp -r "$W/out-typescript-fetch" "$W/ts-fetch/gen"
cp "$HERE/smoke/smoke_typescript_fetch.ts" "$W/ts-fetch/smoke.ts"
cat > "$W/ts-fetch/tsconfig.json" <<EOF
{ "compilerOptions": { "target": "es2022", "module": "commonjs", "lib": ["es2022", "dom"], "strict": true,
  "outDir": "dist", "types": ["node"], "typeRoots": ["$W/tsenv/node_modules/@types"] }, "files": ["smoke.ts"] }
EOF
b=$(ok "$TSC" -p "$W/ts-fetch")
s=$(ok node "$W/ts-fetch/dist/smoke.js" "$BASE")
row openapi-generator "$OAG_VERSION" typescript-fetch as-generated "$g" "$b" "$s" ""

# --- openapi-generator: go ---------------------------------------------------
# As generated, `has_analysis` and `has_market` collide with the HasAnalysis()
# and HasMarket() presence methods made for `analysis` and `market`.
g=$(ok oag go out-go --git-user-id livetennisapi --git-repo-id gen-go --additional-properties=packageName=ltapi)
b=$(ok sh -c "cd '$W/out-go' && go mod tidy && go build ./...")
row openapi-generator "$OAG_VERSION" go as-generated "$g" "$b" "skipped" "$(why "$b" "has_analysis and has_market clash with generated HasAnalysis() and HasMarket()")"
g=$(ok oag go out-go --git-user-id livetennisapi --git-repo-id gen-go --additional-properties=packageName=ltapi \
    --name-mappings has_analysis=HasAnalysisFlag,has_market=HasMarketFlag)
b=$(ok sh -c "cd '$W/out-go' && go mod tidy && go build ./... && go vet .")
rm -rf "$W/go-smoke" && mkdir -p "$W/go-smoke" && cp "$HERE/smoke/go-openapi-generator/main.go" "$W/go-smoke/"
s=$(ok sh -c "cd '$W/go-smoke' && go mod init smoke && go mod edit -require github.com/livetennisapi/gen-go@v0.0.0 \
    -replace github.com/livetennisapi/gen-go=../out-go && go mod tidy && go run . '$BASE'")
row openapi-generator "$OAG_VERSION" go with-fix "$g" "$b" "$s" "--name-mappings has_analysis=HasAnalysisFlag,has_market=HasMarketFlag"

# --- openapi-generator: java (okhttp-gson, built with Maven in Docker) -----
g=$(ok oag java out-java)
mkdir -p "$W/m2"
b=$(ok docker run --rm -m 2g -e MAVEN_OPTS=-Xmx1g -u "$U" -v "$W:/w" -w /w/out-java --entrypoint "" "$MAVEN_IMAGE" \
    mvn -B -q -Dmaven.repo.local=/w/m2/repo -DskipTests -Dmaven.javadoc.skip=true package dependency:copy-dependencies)
rm -rf "$W/java-smoke" && mkdir -p "$W/java-smoke" && cp "$HERE/smoke/Smoke.java" "$W/java-smoke/"
s=$(ok docker run --rm -m 1g --network host -u "$U" -v "$W:/w" -w /w/java-smoke --entrypoint "" "$MAVEN_IMAGE" sh -c \
    "CP=\"\$(ls /w/out-java/target/openapi-java-client-*[0-9].jar):/w/out-java/target/dependency/*\"; \
     javac -cp \"\$CP\" -d . Smoke.java && java -cp \".:\$CP\" Smoke '$BASE'")
row openapi-generator "$OAG_VERSION" java as-generated "$g" "$b" "$s" ""

# --- openapi-generator: csharp (generichost, built with .NET in Docker) ----
# As generated, the model `Match` is ambiguous with
# System.Text.RegularExpressions.Match inside the generated ClientUtils.cs.
dotnet() { docker run --rm -m 3g --network host -u "$U" -e HOME=/w/nuget -e DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    -e NUGET_PACKAGES=/w/nuget/packages -e Logging__LogLevel__Default=Warning -v "$W:/w" -w /w "$DOTNET_IMAGE" dotnet "$@"; }
mkdir -p "$W/nuget"
g=$(ok oag csharp out-csharp --additional-properties=packageName=livetennisapi_gen)
b=$(ok dotnet build -nologo -v q out-csharp/src/livetennisapi_gen/livetennisapi_gen.csproj)
row openapi-generator "$OAG_VERSION" csharp as-generated "$g" "$b" "skipped" "$(why "$b" "model Match is ambiguous with System.Text.RegularExpressions.Match")"
g=$(ok oag csharp out-csharp --additional-properties=packageName=livetennisapi_gen --model-name-mappings Match=MatchModel)
b=$(ok dotnet build -nologo -v q out-csharp/src/livetennisapi_gen/livetennisapi_gen.csproj)
rm -rf "$W/cs-smoke" && mkdir -p "$W/cs-smoke" && cp "$HERE/smoke/csharp/"* "$W/cs-smoke/"
s=$(ok dotnet run -v q --project cs-smoke/Smoke.csproj "$BASE")
row openapi-generator "$OAG_VERSION" csharp with-fix "$g" "$b" "$s" "--model-name-mappings Match=MatchModel. The client needs an ApiKeyToken as well as a BearerToken and then sends both headers"

# --- openapi-typescript (types) + openapi-fetch (runtime) ------------------
rm -rf "$W/ots" && mkdir -p "$W/ots"
g=$(ok "$W/tsenv/node_modules/.bin/openapi-typescript" "$W/openapi.json" -o "$W/ots/schema.ts")
cp "$HERE/smoke/smoke_openapi_typescript.ts" "$W/ots/smoke.ts"
ln -sfn "$W/tsenv/node_modules" "$W/ots/node_modules"
echo '{"type":"module"}' > "$W/ots/package.json"
cat > "$W/ots/tsconfig.json" <<'EOF'
{ "compilerOptions": { "target": "es2022", "module": "nodenext", "moduleResolution": "nodenext",
  "lib": ["es2022", "dom"], "strict": true, "outDir": "dist", "types": ["node"] }, "files": ["smoke.ts", "schema.ts"] }
EOF
b=$(ok "$TSC" -p "$W/ots")
s=$(ok node "$W/ots/dist/smoke.js" "$BASE")
row openapi-typescript "$OPENAPI_TS" typescript as-generated "$g" "$b" "$s" "types only. The smoke call uses openapi-fetch $OPENAPI_FETCH"

# --- oapi-codegen ----------------------------------------------------------
# It reads OpenAPI 3.0 through kin-openapi. As given, generation stops on a
# duplicate Go type name (the `player` parameter and the Player schema).
GOBIN="$W/bin" go install "github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@$OAPI_CODEGEN" >> "$W/run.log" 2>&1
OC="$W/bin/oapi-codegen"
oc() { # oc SPEC OUTDIR
    rm -rf "$W/$2" && mkdir -p "$W/$2"
    ( cd "$W/$2" && "$OC" -generate types,client -package ltapi -o ltapi.gen.go "$1" )
}
g=$(ok oc "$W/openapi.json" out-oapi)
row oapi-codegen "$OAPI_CODEGEN" go as-generated "$g" "skipped" "skipped" "$(why "$g" "duplicate Go type Player (the player parameter and the Player schema)")"
python3 -I "$HERE/oapi_codegen_prep.py" --rename-only "$W/openapi.json" "$W/openapi.oapi.json" >> "$W/run.log" 2>&1
g=$(ok oc "$W/openapi.oapi.json" out-oapi)
row oapi-codegen "$OAPI_CODEGEN" go rename-only "$g" "skipped" "skipped" "$(why "$g" "null listed in a nullable enum cannot become a Go constant")"
python3 -I "$HERE/oapi_codegen_prep.py" "$W/openapi.json" "$W/openapi.oapi.json" >> "$W/run.log" 2>&1
g=$(ok oc "$W/openapi.oapi.json" out-oapi)
b=$(ok sh -c "cd '$W/out-oapi' && go mod init github.com/livetennisapi/gen-oapi && go mod tidy && go build ./... && go vet ./...")
rm -rf "$W/oapi-smoke" && mkdir -p "$W/oapi-smoke" && cp "$HERE/smoke/go-oapi-codegen/main.go" "$W/oapi-smoke/"
s=$(ok sh -c "cd '$W/oapi-smoke' && go mod init smoke && go mod edit -require github.com/livetennisapi/gen-oapi@v0.0.0 \
    -replace github.com/livetennisapi/gen-oapi=../out-oapi && go mod tidy && go run . '$BASE'")
row oapi-codegen "$OAPI_CODEGEN" go with-fix "$g" "$b" "$s" "oapi_codegen_prep.py: x-go-name on the player parameter and null dropped from the nullable enums"

echo
echo "toolchain: $(python3 --version), node $(node --version), tsc $("$TSC" --version | awk '{print $2}'), $(go version | awk '{print $3}')"
echo "images: $OAG_IMAGE, $MAVEN_IMAGE, $DOTNET_IMAGE ($(dotnet --version 2>/dev/null))"
echo "spec: docs/openapi.json, info.version $SPEC_VERSION"
echo "results: $CSV (log: $W/run.log)"
