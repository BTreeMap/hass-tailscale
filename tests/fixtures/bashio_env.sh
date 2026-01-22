#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BASHIO_DIR:-}" ]]; then
  echo "BASHIO_DIR must be set" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${BASHIO_DIR}/lib/bashio.sh"

function bashio::addon.config() {
  cat "${BASHIO_CONFIG_JSON}"
}

function bashio::core.port() {
  echo "${BASHIO_CORE_PORT:-8123}"
}

function bashio::core.ssl() {
  echo "${BASHIO_CORE_SSL:-false}"
}

function bashio::log.info() { :; }
function bashio::log.warning() { :; }
function bashio::log.fatal() { :; }

function bashio::config() {
  local key=${1}
  local default_value=${2:-null}
  local query

  query=$(
    cat << QUERY
        if (.${key} == null) then
            null
        elif (.${key} | type == "string") then
            .${key} // empty
        elif (.${key} | type == "boolean") then
            .${key} // false
        elif (.${key} | type == "array") then
            if (.${key} == []) then
                empty
            else
                .${key}[]
            end
        elif (.${key} | type == "object") then
            if (.${key} == {}) then
                empty
            else
                .${key}
            end
        else
            .${key}
        end
QUERY
  )

  bashio::jq "${BASHIO_CONFIG_JSON}" "${query}" | while IFS= read -r line; do
    if [[ "${line}" == "null" ]]; then
      echo "${default_value}"
    else
      printf "%s\n" "${line}"
    fi
  done
}
