from __future__ import annotations

import asyncio
import inspect
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit

type AddressResolver = Callable[..., Iterable[Any] | Awaitable[Iterable[Any]]]


class URLPolicyError(ValueError):
    """Raised before a request when a URL is outside the configured boundary."""


@dataclass(frozen=True, slots=True)
class ValidatedURL:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


def canonicalize_host(host: str) -> str:
    """Return the comparison form for a DNS host without broadening its scope."""

    candidate = host.strip().rstrip(".")
    if not candidate:
        raise URLPolicyError("URL host is empty")
    if any(ord(character) < 33 for character in candidate):
        raise URLPolicyError("URL host contains control or whitespace characters")
    try:
        return candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise URLPolicyError("URL host is not valid IDNA") from exc


def is_public_ip(address: str) -> bool:
    """Whether an address is globally routable (IPv4-mapped IPv6 included)."""

    try:
        parsed = ipaddress.ip_address(address.split("%", maxsplit=1)[0])
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return parsed.is_global


def validate_url_syntax(
    url: str,
    allowed_hosts: Sequence[str],
    *,
    allowed_ports: Sequence[int] = (80, 443),
) -> tuple[SplitResult, str, int]:
    """Validate scheme, credentials, exact host membership, and port."""

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise URLPolicyError("URL is malformed") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise URLPolicyError("only http and https URLs are permitted")
    if not parsed.hostname:
        raise URLPolicyError("URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise URLPolicyError("URL credentials are not permitted")

    host = canonicalize_host(parsed.hostname)
    try:
        normalized_allowed = {canonicalize_host(item) for item in allowed_hosts}
    except URLPolicyError as exc:
        raise URLPolicyError("allowed_hosts contains an invalid hostname") from exc
    if not normalized_allowed:
        raise URLPolicyError("allowed_hosts must not be empty")
    if host not in normalized_allowed:
        raise URLPolicyError(f"host {host!r} is not explicitly allowed")

    effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if effective_port not in allowed_ports:
        raise URLPolicyError(f"port {effective_port} is not permitted")
    return parsed, host, effective_port


async def system_resolver(host: str, port: int) -> tuple[str, ...]:
    """Resolve a host off the event loop and return unique numeric addresses."""

    loop = asyncio.get_running_loop()
    records = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM),
    )
    return tuple(sorted({str(record[4][0]) for record in records}))


def _coerce_addresses(records: Iterable[Any]) -> tuple[str, ...]:
    addresses: set[str] = set()
    for record in records:
        if isinstance(record, (str, ipaddress.IPv4Address, ipaddress.IPv6Address)):
            addresses.add(str(record))
            continue
        # Accept socket.getaddrinfo-shaped records to keep resolver injection simple.
        if isinstance(record, tuple) and len(record) >= 5:
            socket_address = record[4]
            if isinstance(socket_address, tuple) and socket_address:
                addresses.add(str(socket_address[0]))
                continue
        raise URLPolicyError("DNS resolver returned an invalid address record")
    return tuple(sorted(addresses))


async def resolve_addresses(
    resolver: AddressResolver,
    host: str,
    port: int,
) -> tuple[str, ...]:
    """Call either a one-argument or two-argument injected resolver."""

    try:
        result = resolver(host, port)
    except TypeError:
        # A small convenience for test resolvers and existing application hooks.
        result = resolver(host)
    if inspect.isawaitable(result):
        result = await result
    return _coerce_addresses(result)


async def validate_public_url(
    url: str,
    allowed_hosts: Sequence[str],
    *,
    resolver: AddressResolver = system_resolver,
    allowed_ports: Sequence[int] = (80, 443),
) -> ValidatedURL:
    """Validate an outbound URL and require every DNS answer to be public.

    Requiring *all* answers to be public prevents a mixed public/private DNS set
    from becoming an SSRF bypass depending on which address the HTTP stack picks.
    Callers must repeat this check for every redirect hop and retry.
    """

    _, host, port = validate_url_syntax(url, allowed_hosts, allowed_ports=allowed_ports)
    try:
        addresses = await resolve_addresses(resolver, host, port)
    except (OSError, socket.gaierror) as exc:
        raise URLPolicyError(f"DNS resolution failed for {host!r}") from exc
    if not addresses:
        raise URLPolicyError(f"DNS resolution returned no addresses for {host!r}")
    blocked = tuple(address for address in addresses if not is_public_ip(address))
    if blocked:
        raise URLPolicyError(f"host {host!r} resolved to a non-public address")
    return ValidatedURL(url=url, host=host, port=port, addresses=addresses)


class URLPolicy:
    """Reusable exact-host and public-network policy."""

    def __init__(
        self,
        allowed_hosts: Sequence[str],
        *,
        resolver: AddressResolver = system_resolver,
        allowed_ports: Sequence[int] = (80, 443),
    ) -> None:
        self.allowed_hosts = tuple(allowed_hosts)
        self.resolver = resolver
        self.allowed_ports = tuple(allowed_ports)

    async def validate(self, url: str) -> ValidatedURL:
        return await validate_public_url(
            url,
            self.allowed_hosts,
            resolver=self.resolver,
            allowed_ports=self.allowed_ports,
        )
