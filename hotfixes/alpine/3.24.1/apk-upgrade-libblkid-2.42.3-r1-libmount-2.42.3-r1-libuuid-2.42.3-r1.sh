#!/usr/bin/env sh
# generated-by: create-hotfix-pr-from-issue.py
# hotfix-id: apk-upgrade-libblkid-2.42.3-r1-libmount-2.42.3-r1-libuuid-2.42.3-r1
# hotfix-cves: CVE-2026-78408
# hotfix-packages: libblkid<2.42.3-r1,libmount<2.42.3-r1,libuuid<2.42.3-r1
set -eu

apk add --no-cache --upgrade 'libblkid>=2.42.3-r1' 'libmount>=2.42.3-r1' 'libuuid>=2.42.3-r1'
