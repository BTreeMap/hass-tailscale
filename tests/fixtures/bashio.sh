#!/usr/bin/env bash
# Minimal bashio stub for tests.

bashio::config() {
  local filter="${1:-}"
  local default="${2-}"
  local query="${filter}"
  if [[ -n "${BASHIO_CONFIG_JSON:-}" ]]; then
    if [[ ! "${query}" =~ ^[[:space:]]*\..* ]]; then
      query=".${query}"
    fi
    if [[ -n "${default}" ]]; then
      jq -r "${query} // \"${default}\"" "${BASHIO_CONFIG_JSON}"
      return
    fi
    jq -r "${query}" "${BASHIO_CONFIG_JSON}"
    return
  fi
  if [[ -n "${default}" ]]; then
    echo "${default}"
  else
    echo ""
  fi
}

bashio::var.true() {
  local value="${1:-}"
  [[ "${value}" == "true" || "${value}" == "True" || "${value}" == "1" ]]
}

bashio::core.ssl() {
  echo "${BASHIO_CORE_SSL:-false}"
}

bashio::core.port() {
  echo "${BASHIO_CORE_PORT:-8123}"
}

bashio::log.info() { :; }
bashio::log.warning() { :; }

bashio::exit.nok() {
  echo "$*" >&2
  exit 1
}
