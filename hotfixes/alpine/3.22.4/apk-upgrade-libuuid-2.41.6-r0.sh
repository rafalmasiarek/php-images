#!/usr/bin/env sh
# generated-by: create-hotfix-pr-from-issue.py
# hotfix-id: apk-upgrade-libuuid-2.41.6-r0
# hotfix-cves: CVE-2025-14104,CVE-2026-27456,CVE-2026-53612,CVE-2026-53613,CVE-2026-53614,CVE-2026-76642,CVE-2026-78410
# hotfix-packages: libuuid<2.41.6-r0
set -eu

apk add --no-cache --upgrade 'libuuid>=2.41.6-r0'
