"""
Tests for the `HTTPTransport` and `AsyncHTTPTransport` classes.

These tests use stand-ins to replace the `httpcore` connection pool
classes, so that we can assert on the exact set of arguments that each
style of connection pool is constructed with.
"""
import socket
import ssl
import typing

import httpcore
import pytest

import httpx


class PoolStandIn:
    """
    A stand-in for an `httpcore` connection pool class, recording the
    keyword arguments it is instantiated with.
    """

    def __init__(self, **kwargs: typing.Any) -> None:
        self.kwargs = kwargs


def connection_pool_stand_in(
    monkeypatch: pytest.MonkeyPatch, pool_class: type
) -> typing.List[PoolStandIn]:
    """
    Replace an `httpcore` connection pool class with a stand-in,
    returning the list of instances it is constructed into.
    """
    instances: typing.List[PoolStandIn] = []

    class RecordingPoolStandIn(PoolStandIn):
        def __init__(self, **kwargs: typing.Any) -> None:
            super().__init__(**kwargs)
            instances.append(self)

    monkeypatch.setattr(httpcore, pool_class.__name__, RecordingPoolStandIn)
    return instances


def example_socket_options() -> typing.List[typing.Tuple[int, int, int]]:
    # Socket options are 3-tuples of (socket level, option name, value).
    # The ordering and any duplicate options are significant,
    # and must be preserved as-is.
    return [
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    ]


def test_http_transport_connection_pool_arguments(monkeypatch):
    pools = connection_pool_stand_in(monkeypatch, httpcore.ConnectionPool)

    limits = httpx.Limits(
        max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
    )
    httpx.HTTPTransport(
        http1=False,
        http2=True,
        limits=limits,
        uds="/var/run/docker.sock",
        local_address="0.0.0.0",
        retries=2,
        socket_options=iter(example_socket_options()),
    )

    assert len(pools) == 1
    kwargs = pools[0].kwargs
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["max_connections"] == 20
    assert kwargs["max_keepalive_connections"] == 10
    assert kwargs["keepalive_expiry"] == 30.0
    assert kwargs["http1"] is False
    assert kwargs["http2"] is True
    assert kwargs["uds"] == "/var/run/docker.sock"
    assert kwargs["local_address"] == "0.0.0.0"
    assert kwargs["retries"] == 2
    # Socket options are passed through to the connection pool as-is.
    # A one-shot iterable is only ever consumed by the pool itself,
    # and must not have been exhausted by the transport.
    assert list(kwargs["socket_options"]) == example_socket_options()


def test_http_transport_http_proxy_arguments(monkeypatch):
    pools = connection_pool_stand_in(monkeypatch, httpcore.HTTPProxy)

    proxy = httpx.Proxy(
        "http://user:pass@127.0.0.1:8080/", headers={"X-Custom": "example"}
    )
    limits = httpx.Limits(
        max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
    )
    httpx.HTTPTransport(
        proxy=proxy,
        http1=False,
        http2=True,
        limits=limits,
        socket_options=iter(example_socket_options()),
    )

    assert len(pools) == 1
    kwargs = pools[0].kwargs
    assert kwargs["proxy_url"] == httpcore.URL("http://127.0.0.1:8080/")
    assert kwargs["proxy_auth"] == (b"user", b"pass")
    assert kwargs["proxy_headers"] == [(b"X-Custom", b"example")]
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["max_connections"] == 20
    assert kwargs["max_keepalive_connections"] == 10
    assert kwargs["keepalive_expiry"] == 30.0
    assert kwargs["http1"] is False
    assert kwargs["http2"] is True
    assert list(kwargs["socket_options"]) == example_socket_options()


def test_http_transport_socks_proxy_arguments(monkeypatch):
    pools = connection_pool_stand_in(monkeypatch, httpcore.SOCKSProxy)

    proxy = httpx.Proxy("socks5://user:pass@127.0.0.1:1080/")
    limits = httpx.Limits(
        max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
    )
    httpx.HTTPTransport(
        proxy=proxy,
        http1=False,
        http2=True,
        limits=limits,
        socket_options=iter(example_socket_options()),
    )

    assert len(pools) == 1
    kwargs = pools[0].kwargs
    assert kwargs["proxy_url"] == httpcore.URL("socks5://127.0.0.1:1080/")
    assert kwargs["proxy_auth"] == (b"user", b"pass")
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["max_connections"] == 20
    assert kwargs["max_keepalive_connections"] == 10
    assert kwargs["keepalive_expiry"] == 30.0
    assert kwargs["http1"] is False
    assert kwargs["http2"] is True
    assert list(kwargs["socket_options"]) == example_socket_options()


def test_http_transport_default_socket_options(monkeypatch):
    # Using `socket_options=None` preserves the existing default behaviour.
    connection_pools = connection_pool_stand_in(monkeypatch, httpcore.ConnectionPool)
    http_proxies = connection_pool_stand_in(monkeypatch, httpcore.HTTPProxy)
    socks_proxies = connection_pool_stand_in(monkeypatch, httpcore.SOCKSProxy)

    httpx.HTTPTransport()
    httpx.HTTPTransport(proxy=httpx.Proxy("http://127.0.0.1:8080/"))
    httpx.HTTPTransport(proxy=httpx.Proxy("socks5://127.0.0.1:1080/"))

    assert connection_pools[0].kwargs["socket_options"] is None
    assert http_proxies[0].kwargs["socket_options"] is None
    # `httpcore.SOCKSProxy` does not support `socket_options` yet,
    # so the argument is only included when explicitly configured.
    assert "socket_options" not in socks_proxies[0].kwargs


def test_http_transport_socket_options_are_not_interpreted(monkeypatch):
    # Socket options are passed through to the connection pool unmodified,
    # without being copied, interpreted, or validated by HTTPX.
    pools = connection_pool_stand_in(monkeypatch, httpcore.ConnectionPool)

    socket_options = example_socket_options()
    httpx.HTTPTransport(socket_options=socket_options)

    assert pools[0].kwargs["socket_options"] is socket_options


def test_async_http_transport_connection_pool_arguments(monkeypatch):
    pools = connection_pool_stand_in(monkeypatch, httpcore.AsyncConnectionPool)

    limits = httpx.Limits(
        max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
    )
    httpx.AsyncHTTPTransport(
        http1=False,
        http2=True,
        limits=limits,
        uds="/var/run/docker.sock",
        local_address="0.0.0.0",
        retries=2,
        socket_options=iter(example_socket_options()),
    )

    assert len(pools) == 1
    kwargs = pools[0].kwargs
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["max_connections"] == 20
    assert kwargs["max_keepalive_connections"] == 10
    assert kwargs["keepalive_expiry"] == 30.0
    assert kwargs["http1"] is False
    assert kwargs["http2"] is True
    assert kwargs["uds"] == "/var/run/docker.sock"
    assert kwargs["local_address"] == "0.0.0.0"
    assert kwargs["retries"] == 2
    assert list(kwargs["socket_options"]) == example_socket_options()


def test_async_http_transport_http_proxy_arguments(monkeypatch):
    pools = connection_pool_stand_in(monkeypatch, httpcore.AsyncHTTPProxy)

    proxy = httpx.Proxy(
        "http://user:pass@127.0.0.1:8080/", headers={"X-Custom": "example"}
    )
    limits = httpx.Limits(
        max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
    )
    httpx.AsyncHTTPTransport(
        proxy=proxy,
        http1=False,
        http2=True,
        limits=limits,
        socket_options=iter(example_socket_options()),
    )

    assert len(pools) == 1
    kwargs = pools[0].kwargs
    assert kwargs["proxy_url"] == httpcore.URL("http://127.0.0.1:8080/")
    assert kwargs["proxy_auth"] == (b"user", b"pass")
    assert kwargs["proxy_headers"] == [(b"X-Custom", b"example")]
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["max_connections"] == 20
    assert kwargs["max_keepalive_connections"] == 10
    assert kwargs["keepalive_expiry"] == 30.0
    assert kwargs["http1"] is False
    assert kwargs["http2"] is True
    assert list(kwargs["socket_options"]) == example_socket_options()


def test_async_http_transport_socks_proxy_arguments(monkeypatch):
    pools = connection_pool_stand_in(monkeypatch, httpcore.AsyncSOCKSProxy)

    proxy = httpx.Proxy("socks5://user:pass@127.0.0.1:1080/")
    limits = httpx.Limits(
        max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
    )
    httpx.AsyncHTTPTransport(
        proxy=proxy,
        http1=False,
        http2=True,
        limits=limits,
        socket_options=iter(example_socket_options()),
    )

    assert len(pools) == 1
    kwargs = pools[0].kwargs
    assert kwargs["proxy_url"] == httpcore.URL("socks5://127.0.0.1:1080/")
    assert kwargs["proxy_auth"] == (b"user", b"pass")
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["max_connections"] == 20
    assert kwargs["max_keepalive_connections"] == 10
    assert kwargs["keepalive_expiry"] == 30.0
    assert kwargs["http1"] is False
    assert kwargs["http2"] is True
    assert list(kwargs["socket_options"]) == example_socket_options()


def test_async_http_transport_default_socket_options(monkeypatch):
    # Using `socket_options=None` preserves the existing default behaviour.
    connection_pools = connection_pool_stand_in(
        monkeypatch, httpcore.AsyncConnectionPool
    )
    http_proxies = connection_pool_stand_in(monkeypatch, httpcore.AsyncHTTPProxy)
    socks_proxies = connection_pool_stand_in(monkeypatch, httpcore.AsyncSOCKSProxy)

    httpx.AsyncHTTPTransport()
    httpx.AsyncHTTPTransport(proxy=httpx.Proxy("http://127.0.0.1:8080/"))
    httpx.AsyncHTTPTransport(proxy=httpx.Proxy("socks5://127.0.0.1:1080/"))

    assert connection_pools[0].kwargs["socket_options"] is None
    assert http_proxies[0].kwargs["socket_options"] is None
    # `httpcore.AsyncSOCKSProxy` does not support `socket_options` yet,
    # so the argument is only included when explicitly configured.
    assert "socket_options" not in socks_proxies[0].kwargs


def test_async_http_transport_socket_options_are_not_interpreted(monkeypatch):
    # Socket options are passed through to the connection pool unmodified,
    # without being copied, interpreted, or validated by HTTPX.
    pools = connection_pool_stand_in(monkeypatch, httpcore.AsyncConnectionPool)

    socket_options = example_socket_options()
    httpx.AsyncHTTPTransport(socket_options=socket_options)

    assert pools[0].kwargs["socket_options"] is socket_options
