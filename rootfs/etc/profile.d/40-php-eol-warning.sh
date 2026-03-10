#!/bin/sh

case "$-" in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac

[ -t 1 ] || return 0 2>/dev/null || exit 0
[ -f /usr/local/share/php-image-lifecycle.env ] || return 0 2>/dev/null || exit 0

. /usr/local/share/php-image-lifecycle.env

[ -n "${PHP_EOL:-}" ] || return 0 2>/dev/null || exit 0

TODAY="$(date -u +%F 2>/dev/null || true)"
[ -n "$TODAY" ] || return 0 2>/dev/null || exit 0

if [ "$TODAY" \> "$PHP_EOL" ] || [ "$TODAY" = "$PHP_EOL" ]; then
  printf '********************************************\n'
  printf 'WARNING: PHP %s (%s) is end-of-life since %s.\n' "${PHP_BRANCH:-unknown}" "${PHP_VERSION:-unknown}" "$PHP_EOL"
  printf 'This image no longer receives upstream support.\n'
  printf '********************************************\n'
fi