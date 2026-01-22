#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BASHIO_DIR:-}" ]]; then
  echo "BASHIO_DIR must be set" >&2
  exit 1
fi

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

source "${BASHIO_DIR}/lib/bashio.sh"
