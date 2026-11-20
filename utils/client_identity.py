"""Resolve a request's client address using only explicitly trusted proxies."""

import ipaddress
import logging

from starlette.requests import Request

logger = logging.getLogger(__name__)


def get_client_ip(request: Request, trusted_proxy_cidrs: str = "") -> str:
    """Return the socket peer or the nearest untrusted address in its proxy chain.

    Forwarded addresses are considered only when the direct peer belongs to a
    configured trusted network. Invalid forwarding data falls back to that
    peer, so malformed headers cannot select a caller-chosen identity.
    """
    peer = request.client.host if request.client else "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    trusted_networks = []
    for item in trusted_proxy_cidrs.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            trusted_networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.error("Ignoring invalid trusted proxy network setting.")

    if not any(peer_ip in network for network in trusted_networks):
        return str(peer_ip)

    forwarded = request.headers.get("x-forwarded-for", "")
    chain = []
    for item in forwarded.split(","):
        try:
            chain.append(ipaddress.ip_address(item.strip()))
        except ValueError:
            return str(peer_ip)

    chain.append(peer_ip)
    while len(chain) > 1 and any(
        chain[-1] in network for network in trusted_networks
    ):
        chain.pop()
    return str(chain[-1])
