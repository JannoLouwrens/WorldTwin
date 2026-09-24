#!/bin/bash
# quarantine.sh — runnable implementation of REVIVAL_V1 §6.1 (finding #15).
#
# Moves the legal-breach cache files (spacetrack_gp, webcams, trade,
# country_exports) out of BOTH served trees into /data/quarantine/legal/,
# asserts nothing is left behind, then probes every served variant URL and
# requires 404 on all of them.
#
# Sequencing (§6.2): run AFTER the aggregator restart — the old in-memory
# scheduler otherwise re-creates the files — and BEFORE tombstones.
# Separate step from the Caddy apply in CADDY_APPLY.md.
#
# Idempotent: nullglob turns every mv into a no-op when files are already
# gone (spacetrack_gp's legacy-tree files were already quarantined
# 2026-09-24 11:02).
#
# sudo: /data/cache/v1 is root-owned drwxr-xr-x (opc cannot rename out of
# it); the legacy /data/cache tree is opc-owned but sudo is used uniformly.
# Passwordless sudo is available on this box. /data/quarantine exists
# opc-owned, so mkdir needs no sudo.
#
# Scope guard: dot-anchored globs (<id>.*) so trade.* matches trade.json /
# trade.data.json but NOT trade_annual* / trade_monthly* — those are
# retired-layer caches handled by the separate §1.B tombstone step, not here.

set -u
shopt -s nullglob

QDIR=/data/quarantine/legal
mkdir -p "$QDIR"

IDS=(spacetrack_gp webcams trade country_exports)

move() {
    # nullglob: caller's unmatched globs vanish, so zero args = nothing to do.
    if [ "$#" -gt 0 ]; then
        echo "[quarantine] moving: $*"
        sudo mv "$@" "$QDIR"/ || { echo "[quarantine] mv FAILED for: $*"; exit 1; }
    fi
}

# Legacy tree (/data/cache, opc-owned).
move /data/cache/{spacetrack_gp,webcams}.*
# trade/country_exports verified absent in the legacy tree today —
# checked anyway for completeness; nullglob makes this a safe no-op.
move /data/cache/{trade,country_exports}.*

# v1 tree (/data/cache/v1, root-owned — sudo required).
move /data/cache/v1/{spacetrack_gp,webcams,trade,country_exports}.*

# Post-move assert: zero matches for every id in BOTH trees.
leftover=0
for id in "${IDS[@]}"; do
    remaining=(/data/cache/"$id".* /data/cache/v1/"$id".*)
    if [ "${#remaining[@]}" -gt 0 ]; then
        echo "[quarantine] ASSERT FAILED — still present: ${remaining[*]}"
        leftover=1
    fi
done
if [ "$leftover" -ne 0 ]; then
    echo "[quarantine] FAIL: quarantine incomplete, see above"
    exit 1
fi
echo "[quarantine] move assert OK: no ${IDS[*]} files left in /data/cache or /data/cache/v1"

# 404 probe sweep: every served variant URL for every id must return 404.
# Accept-Encoding: gzip defends the precompressed /api/cache/* block; the
# literal .gz / .data.json URLs defend the plain file_server blocks.
fail=0
total=0
for id in "${IDS[@]}"; do
    for url in \
        "http://localhost/api/cache/${id}.json" \
        "http://localhost/api/cache/${id}.json.gz" \
        "http://localhost/api/cache/v1/${id}.json" \
        "http://localhost/api/cache/v1/${id}.data.json" \
        "http://localhost/v1/cache/${id}.json" \
        "http://localhost/v1/cache/${id}.json.gz" \
        "http://localhost/v1/cache/${id}.data.json" \
        "http://localhost/v1/cache/${id}.data.json.gz" \
    ; do
        total=$((total + 1))
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H 'Accept-Encoding: gzip' "$url")
        if [ "$code" = "404" ]; then
            echo "OK  404 $url"
        else
            echo "BAD $code $url (expected 404)"
            fail=$((fail + 1))
        fi
    done
done

if [ "$fail" -gt 0 ]; then
    echo "[quarantine] FAIL: $fail of $total variant probes did not return 404"
    exit 1
fi
echo "[quarantine] PASS: all $total variant probes returned 404; files quarantined in $QDIR"
