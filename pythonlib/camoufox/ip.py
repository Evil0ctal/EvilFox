import re
import warnings
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

import requests
from urllib3.exceptions import InsecureRequestWarning

from .exceptions import InvalidIP, InvalidProxy

"""
Helpers to find the user's public IP address for geolocation.
"""


@dataclass
class Proxy:
    """
    Stores proxy information.
    """

    server: str
    username: Optional[str] = None
    password: Optional[str] = None
    bypass: Optional[str] = None

    @staticmethod
    def parse_server(server: str) -> Tuple[str, str, Optional[str]]:
        """
        Parses the proxy server string.
        """
        proxy_match = re.match(r'^(?:(?P<schema>\w+)://)?(?P<url>.*?)(?:\:(?P<port>\d+))?$', server)
        if not proxy_match:
            raise InvalidProxy(f"Invalid proxy server: {server}")
        return proxy_match['schema'], proxy_match['url'], proxy_match['port']

    def as_string(self) -> str:
        schema, url, port = self.parse_server(self.server)
        if not schema:
            schema = 'http'
        result = f"{schema}://"
        if self.username:
            result += f"{self.username}"
            if self.password:
                result += f":{self.password}"
            result += "@"

        result += url
        if port:
            result += f":{port}"
        return result

    @staticmethod
    def as_requests_proxy(proxy_string: str) -> Dict[str, str]:
        """
        Converts the proxy to a requests proxy dictionary.
        """
        return {
            'http': proxy_string,
            'https': proxy_string,
        }


@lru_cache(128, typed=True)
def valid_ipv4(ip: str) -> bool:
    return bool(re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', ip))


@lru_cache(128, typed=True)
def valid_ipv6(ip: str) -> bool:
    return bool(re.match(r'^(([0-9a-fA-F]{0,4}:){1,7}[0-9a-fA-F]{0,4})$', ip))


def validate_ip(ip: str) -> None:
    if not valid_ipv4(ip) and not valid_ipv6(ip):
        raise InvalidIP(f"Invalid IP address: {ip}")


@contextmanager
def _suppress_insecure_warning():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=InsecureRequestWarning)
        yield


@lru_cache(maxsize=None)
def public_ip(proxy: Optional[str] = None, verify_ssl: bool = False) -> str:
    """
    Sends a request to a public IP api
    
    Args:
        proxy: Optional proxy string to use for the request
        verify_ssl: Whether to verify SSL certificates (default: False for compatibility
                   with various IP lookup services that may have certificate issues)
    """
    URLS = [
        # Prefers IPv4
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://ipinfo.io/ip",
        # IPv4 & IPv6
        "https://icanhazip.com",
        "https://ifconfig.co/ip",
        "https://ipecho.net/plain",
    ]

    exception = None
    for url in URLS:
        try:
            context = _suppress_insecure_warning() if not verify_ssl else nullcontext()
            with context:
                resp = requests.get(
                    url,
                    proxies=Proxy.as_requests_proxy(proxy) if proxy else None,
                    timeout=5,
                    verify=verify_ssl,
                )
            resp.raise_for_status()
            ip = resp.text.strip()
            validate_ip(ip)
            return ip
        except (requests.exceptions.ProxyError, requests.RequestException, InvalidIP) as exception:
            pass
    raise InvalidIP(f"Failed to get IP address: {exception}")
