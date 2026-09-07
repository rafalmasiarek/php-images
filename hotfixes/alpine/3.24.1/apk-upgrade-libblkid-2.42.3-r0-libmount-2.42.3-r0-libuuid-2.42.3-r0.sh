#!/usr/bin/env sh
# generated-by: create-hotfix-pr-from-issue.py
# hotfix-id: apk-upgrade-libblkid-2.42.3-r0-libmount-2.42.3-r0-libuuid-2.42.3-r0
# hotfix-cves: CVE-2026-27456,CVE-2026-53612,CVE-2026-53613,CVE-2026-53614,CVE-2026-76642,CVE-2026-78408,CVE-2026-78409,CVE-2026-78410
# hotfix-packages: libblkid<2.42.3-r0,libmount<2.42.3-r0,libuuid<2.42.3-r0
set -eu

apk add --no-cache --upgrade 'libblkid>=2.42.3-r0' 'libmount>=2.42.3-r0' 'libuuid>=2.42.3-r0'
