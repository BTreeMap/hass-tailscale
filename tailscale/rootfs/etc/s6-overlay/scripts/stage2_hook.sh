#!/command/with-contenv bashio
# shellcheck shell=bash
export LOG_FD
# ==============================================================================
# Home Assistant Community App: Tailscale
# S6 Overlay stage2 hook to customize services
# ==============================================================================

# MagicDNS related service dependencies:
#
#                                    +-------- magicdns-ingress-proxy
#                                    |          |                 |
#                                    |          |                 |
#                                    ˅    !!    ˅                 |
#   init-magicdns-proxies-upstream-list -----> post-tailscaled    |
#                                    ˄          |                 |
#                                    |          |                 |
#                                    |    !!    ˅                 |
#                 magicdns-egress-proxy <----- tailscaled         |
#                                               |                 |
#                                               |                 |
#                                               ˅                 ˅
#                                              init-magicdns-ingress-proxy
#
# Disable MagicDNS egress proxy service when userspace-networking is enabled or accepting dns is disabled
if bashio::config.true "userspace_networking" || \
    bashio::config.false "accept_dns";
then
    # Either this or init-magicdns-proxies-upstream-list/dependencies.d/post-tailscaled below has to be removed
    # When accepting dns is disabled init-magicdns-proxies-upstream-list depends on post-tailscaled
    rm /etc/s6-overlay/s6-rc.d/tailscaled/dependencies.d/magicdns-egress-proxy
else
    # Either this or tailscaled/dependencies.d/magicdns-egress-proxy above has to be removed
    # When accepting dns is enabled init-magicdns-proxies-upstream-list doesn't depend on post-tailscaled
    rm /etc/s6-overlay/s6-rc.d/init-magicdns-proxies-upstream-list/dependencies.d/post-tailscaled
fi
# Disable MagicDNS ingress proxy service when userspace-networking is enabled
if bashio::config.true "userspace_networking"; then
    rm /etc/s6-overlay/s6-rc.d/forwarding/dependencies.d/magicdns-ingress-proxy
    rm /etc/s6-overlay/s6-rc.d/user/contents.d/magicdns-ingress-proxy
    rm /etc/s6-overlay/s6-rc.d/tailscaled/dependencies.d/init-magicdns-ingress-proxy
fi
# Disable protect-subnets service when userspace-networking is enabled or accepting routes is disabled
if bashio::config.true "userspace_networking" || \
    bashio::config.false "accept_routes";
then
    rm /etc/s6-overlay/s6-rc.d/post-tailscaled/dependencies.d/protect-subnets
fi

# If local subnets are not configured in advertise_routes, do not wait for the local network to be ready to collect subnet information
if ! bashio::config "advertise_routes" | grep -Fxq "local_subnets"; then
    rm /etc/s6-overlay/s6-rc.d/post-tailscaled/dependencies.d/local-network
fi

# Disable forwarding service when userspace-networking is enabled
if bashio::config.true "userspace_networking"; then
    rm /etc/s6-overlay/s6-rc.d/user/contents.d/forwarding
fi

# Disable mss-clamping service when userspace-networking is enabled
if bashio::config.true "userspace_networking"; then
    rm /etc/s6-overlay/s6-rc.d/user/contents.d/mss-clamping
fi

# Disable taildrop service when it has been explicitly disabled
if bashio::config.false 'taildrop'; then
    rm /etc/s6-overlay/s6-rc.d/user/contents.d/taildrop
fi

# Disable share-homeassistant service when it has been explicitly disabled
if bashio::config.equals 'share_homeassistant' 'disabled'; then
    rm /etc/s6-overlay/s6-rc.d/user/contents.d/share-homeassistant
fi
