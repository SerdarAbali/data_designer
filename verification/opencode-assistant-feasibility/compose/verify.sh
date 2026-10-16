#!/usr/bin/env bash
# Disposable Compose proof for the Architecture Assistant network posture.
#
# Usage:  bash compose/verify.sh
#
# Builds a minimal OpenCode image from the local binary, starts it with no
# published host port, and checks:
#   * a sibling container can reach it by service name and that an
#     unauthenticated request is rejected;
#   * the host cannot reach the container on the container port at all.
#
# Nothing outside this directory is modified; the temporary build context lives
# under /tmp and is removed on exit. Run from the harness directory.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS="$(dirname "$HERE")"
COMPOSE_FILE="$HERE/compose.verify.yml"
CONTEXT="${ARCHVERIFY_BUILD_CONTEXT:-/tmp/opencode/archverify-compose}"
OPENCODE_BIN="${ARCHVERIFY_OPENCODE_BIN:-/home/sedu/.opencode/bin/opencode}"
CONTAINER_PORT=4096

cleanup() {
  sudo env ARCHVERIFY_BUILD_CONTEXT="$CONTEXT" docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$CONTEXT"
}
trap cleanup EXIT

rm -rf "$CONTEXT"
mkdir -p "$CONTEXT/plugins/verify"
cp "$OPENCODE_BIN" "$CONTEXT/opencode"
cp "$HERE/Dockerfile" "$CONTEXT/Dockerfile"
cp "$HARNESS/runtime/profile/opencode.json" "$CONTEXT/opencode.json"
cp "$HARNESS/runtime/profile/.opencode/plugins/verify/index.ts" "$CONTEXT/plugins/verify/index.ts"

echo "== building and starting the verification stack (no published ports) =="
sudo env ARCHVERIFY_BUILD_CONTEXT="$CONTEXT" docker compose -f "$COMPOSE_FILE" up --build -d

echo
echo "== published port check (host must see nothing) =="
PUBLISHED="$(sudo env ARCHVERIFY_BUILD_CONTEXT="$CONTEXT" docker compose -f "$COMPOSE_FILE" ps --format json \
  | python3 -c 'import json,sys
ports=0
for line in sys.stdin:
    line=line.strip()
    if not line:
        continue
    row=json.loads(line)
    # Compose reports exposed-but-unpublished ports with PublishedPort == 0.
    ports += sum(
        1
        for publisher in (row.get("Publishers") or [])
        if int(publisher.get("PublishedPort") or 0) > 0
    )
print(ports)')"
echo "published_host_ports=$PUBLISHED"
HOST_REACHABLE=no
if timeout 3 bash -c "</dev/tcp/127.0.0.1/$CONTAINER_PORT" 2>/dev/null; then
  HOST_REACHABLE=yes
fi
echo "host_can_connect_to_127.0.0.1:$CONTAINER_PORT=$HOST_REACHABLE"

echo
echo "== waiting for the in-network probe to finish =="
PROBE_ID="$(sudo env ARCHVERIFY_BUILD_CONTEXT="$CONTEXT" docker compose -f "$COMPOSE_FILE" ps -q probe)"
for _ in $(seq 1 90); do
  STATE="$(sudo docker inspect -f '{{.State.Status}}' "$PROBE_ID" 2>/dev/null || echo missing)"
  [ "$STATE" = "exited" ] && break
  sleep 1
done
echo "probe_container_state=$STATE"

echo
echo "== in-network probe output (service-name reachability + auth) =="
PROBE_LOG="$(sudo docker logs "$PROBE_ID" 2>&1 || true)"
echo "$PROBE_LOG"

echo
FAIL=0
[ "$PUBLISHED" = "0" ] || { echo "FAIL: published host ports = $PUBLISHED"; FAIL=1; }
[ "$HOST_REACHABLE" = "no" ] || { echo "FAIL: host reached the container port"; FAIL=1; }
echo "$PROBE_LOG" | grep -q "2.0.30" || { echo "FAIL: sibling container did not reach OpenCode by service name"; FAIL=1; }
echo "$PROBE_LOG" | grep -q "status=401" || { echo "FAIL: unauthenticated request was not rejected"; FAIL=1; }
[ "$FAIL" = "0" ] || { echo "RESULT: FAIL"; exit 1; }
echo "RESULT: PASS - OpenCode is private to the Compose network; sibling container reached it by service name; unauthenticated access is rejected; host cannot reach it"
