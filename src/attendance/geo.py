"""Geo and network helpers."""
import ipaddress
import math

EARTH_RADIUS_METERS = 6_371_000


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def network_of(ip: str) -> str:
    """The surrounding network of an address: /24 for IPv4, /64 for IPv6.
    Campus Wi-Fi usually NATs through a small pool of public addresses,
    so trusting the lecturer's /24 covers students on the same Wi-Fi."""
    addr = ipaddress.ip_address(ip)
    prefix = 24 if addr.version == 4 else 64
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def ip_in_networks(ip: str, networks: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in networks:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False
