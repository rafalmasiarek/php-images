#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:?namespace required}"
NAME="${2:?name required}"
PREFIX="${3:?tag prefix required}"

DATE_UTC="$(date -u +%F)"
SHA_SHORT="${GITHUB_SHA:-local}"
SHA_SHORT="${SHA_SHORT:0:7}"

echo "TAG_MOVING=${NAMESPACE}/${NAME}:${PREFIX}"
echo "TAG_DATE=${NAMESPACE}/${NAME}:${PREFIX}-${DATE_UTC}"
echo "TAG_SHA=${NAMESPACE}/${NAME}:${PREFIX}-sha-${SHA_SHORT}"
