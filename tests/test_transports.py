import ssl
import sys
import types
import typing

import httpcore
import pytest

import httpx


class RecordingPool:
    calls: typing.ClassVar[typing.List[typing.Dict[str, typing.Any]]] = []

    def __init__(self, **kwargs: typing.Any) -> None:
        self.kwargs = kwargs
        type(self).calls.append(kwargs)


@pytest.mark.parametrize(
    ("transport_class", "proxy_url", "pool_name"),
    [
        (httpx.HTTPTransport, None, "ConnectionPool"),
        (httpx.HTTPTransport, "http://proxy:8080", "HTTPProxy"),
        (httpx.HTTPTransport, "socks5://proxy:1080", "SOCKSProxy"),
        (httpx.AsyncHTTPTransport, None, "AsyncConnectionPool"),
        (httpx.AsyncHTTPTransport, "http://proxy:8080", "AsyncHTTPProxy"),
        (httpx.AsyncHTTPTransport, "socks5://proxy:1080", "AsyncSOCKSProxy"),
    ],
)
def test_socket_options(
    monkeypatch: pytest.MonkeyPatch,
    transport_class: type,
    proxy_url: typing.Optional[str],
    pool_name: str,
) -> None:
    RecordingPool.calls = []
    monkeypatch.setattr(httpcore, pool_name, RecordingPool)
    if proxy_url is not None and proxy_url.startswith("socks5://"):
        monkeypatch.setitem(sys.modules, "socksio", types.ModuleType("socksio"))

    proxy = None if proxy_url is None else httpx.Proxy(proxy_url)
    transport_class(proxy=proxy)
    assert RecordingPool.calls[0]["socket_options"] is None

    limits = httpx.Limits(
        max_connections=11,
        max_keepalive_connections=7,
        keepalive_expiry=13.5,
    )
    socket_options = iter(
        (
            (1, 2, 3),
            (4, 5, b"six"),
            (7, 8, bytearray(b"nine")),
            (1, 2, 3),
        )
    )

    if proxy_url is None:
        transport_class(
            verify=False,
            http1=False,
            http2=True,
            limits=limits,
            trust_env=False,
            uds="/tmp/test.sock",
            local_address="127.0.0.1",
            retries=4,
            socket_options=socket_options,
        )
        expected = {
            "max_connections": 11,
            "max_keepalive_connections": 7,
            "keepalive_expiry": 13.5,
            "http1": False,
            "http2": True,
            "uds": "/tmp/test.sock",
            "local_address": "127.0.0.1",
            "retries": 4,
            "socket_options": socket_options,
        }
    else:
        proxy = httpx.Proxy(
            proxy_url,
            auth=("user", "password"),
            headers={"X-Test": "value"},
        )
        transport_class(
            proxy=proxy,
            verify=False,
            http1=False,
            http2=True,
            limits=limits,
            trust_env=False,
            socket_options=socket_options,
        )

        raw_scheme = proxy.url.raw_scheme
        expected = {
            "proxy_url": httpcore.URL(
                scheme=raw_scheme,
                host=b"proxy",
                port=proxy.url.port,
                target=b"/",
            ),
            "proxy_auth": (b"user", b"password"),
            "max_connections": 11,
            "max_keepalive_connections": 7,
            "keepalive_expiry": 13.5,
            "http1": False,
            "http2": True,
            "socket_options": socket_options,
        }
        if pool_name in ("HTTPProxy", "AsyncHTTPProxy"):
            expected["proxy_headers"] = [(b"X-Test", b"value")]

    kwargs = RecordingPool.calls[1]
    assert isinstance(kwargs.pop("ssl_context"), ssl.SSLContext)
    assert kwargs == expected

    # The iterable is passed through without being consumed, reordered,
    # deduplicated, or converted by HTTPX.
    assert list(socket_options) == [
        (1, 2, 3),
        (4, 5, b"six"),
        (7, 8, bytearray(b"nine")),
        (1, 2, 3),
    ]
