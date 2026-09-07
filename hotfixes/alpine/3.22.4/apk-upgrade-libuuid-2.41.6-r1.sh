#!/usr/bin/env sh
# generated-by: create-hotfix-pr-from-issue.py
# hotfix-id: apk-upgrade-libuuid-2.41.6-r1
# hotfix-cves: CVE-2026-78408
# hotfix-packages: libuuid<2.41.6-r1
set -eu

apk add --no-cache --upgrade 'libuuid>=2.41.6-r1'
