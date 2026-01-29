FROM ghcr.io/hassio-addons/base:20.0.1

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Setup base
ARG BUILD_ARCH=amd64

# renovate: datasource=repology depName=coreutils packageName=alpine_3_23/coreutils versioning=loose
ARG COREUTILS_VERSION="9.7-r1"
# renovate: datasource=repology depName=ethtool packageName=alpine_3_23/ethtool versioning=loose
ARG ETHTOOL_VERSION="6.14.1-r0"
# renovate: datasource=repology depName=ipcalc packageName=alpine_3_23/ipcalc versioning=loose
ARG IPCALC_VERSION="1.0.3-r0"
# renovate: datasource=repology depName=iproute2 packageName=alpine_3_23/iproute2 versioning=loose
ARG IPROUTE2_VERSION="6.15.0-r0"
# renovate: datasource=repology depName=iptables packageName=alpine_3_23/iptables versioning=loose
ARG IPTABLES_VERSION="1.8.11-r1"
# renovate: datasource=repology depName=networkmanager packageName=alpine_3_23/networkmanager versioning=loose
ARG NETWORKMANAGER_VERSION="1.52.1-r0"
# renovate: datasource=repology depName=nginx packageName=alpine_3_23/nginx versioning=loose
ARG NGINX_VERSION="1.28.0-r8"

# renovate: datasource=github-releases depName=tailscale packageName=tailscale/tailscale versioning=loose extractVersion=^v(?<version>.*)$
ARG TAILSCALE_VERSION="1.92.5"

RUN \
  apk add --no-cache \
    coreutils="${COREUTILS_VERSION}" \
    ethtool="${ETHTOOL_VERSION}" \
    ipcalc="${IPCALC_VERSION}" \
    iproute2="${IPROUTE2_VERSION}" \
    iptables="${IPTABLES_VERSION}" \
    networkmanager="${NETWORKMANAGER_VERSION}" \
    nginx="${NGINX_VERSION}" \
  && ln -sf /sbin/xtables-nft-multi /sbin/ip6tables \
  && ln -sf /sbin/xtables-nft-multi /sbin/iptables \
  && case "${BUILD_ARCH}" in \
       aarch64) ARCH="arm64" ;; \
       amd64)   ARCH="amd64" ;; \
       *) echo "Unsupported BUILD_ARCH=${BUILD_ARCH}" >&2; exit 1 ;; \
     esac \
  && curl -fsSL "https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_${ARCH}.tgz" \
     | tar zxvf - -C /opt/ --strip-components 1 \
  && rm -rf \
    /opt/systemd

# Copy root filesystem
COPY rootfs /

HEALTHCHECK \
    CMD healthcheck

# S6 Overlay stage 2 hook
ENV S6_STAGE2_HOOK=/etc/s6-overlay/scripts/stage2_hook.sh

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
  io.hass.name="${BUILD_NAME}" \
  io.hass.description="${BUILD_DESCRIPTION}" \
  io.hass.arch="${BUILD_ARCH}" \
  io.hass.type="addon" \
  io.hass.version=${BUILD_VERSION} \
  maintainer="Joe Fang <hass-tailscale@oss.joefang.org>" \
  org.opencontainers.image.title="${BUILD_NAME}" \
  org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
  org.opencontainers.image.vendor="BTreeMap" \
  org.opencontainers.image.authors="Joe Fang <hass-tailscale@oss.joefang.org>" \
  org.opencontainers.image.licenses="MIT" \
  org.opencontainers.image.url="https://github.com/BTreeMap/hass-tailscale" \
  org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
  org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
  org.opencontainers.image.created=${BUILD_DATE} \
  org.opencontainers.image.revision=${BUILD_REF} \
  org.opencontainers.image.version=${BUILD_VERSION}
