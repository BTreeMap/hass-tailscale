#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${TAILSCALE_LOG:-}" ]]; then
  printf '%q ' "$0" "$@" >> "${TAILSCALE_LOG}"
  printf '\n' >> "${TAILSCALE_LOG}"
fi

if [[ "${1:-}" == "status" ]]; then
  if [[ -n "${TAILSCALE_STATUS_JSON:-}" ]]; then
    printf '%s' "${TAILSCALE_STATUS_JSON}"
  else
    printf '%s' '{"Self":{"CapMap":{"https":true,"funnel":true}}}'
  fi
  exit 0
fi

exit 0
