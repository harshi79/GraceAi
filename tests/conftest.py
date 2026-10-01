"""Shared fixtures: a live mock Aero server and a client pointed at it."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mock_aero import MockAero, start_server, stop_server  # noqa: E402

from grace.client import AeroClient  # noqa: E402


@pytest.fixture()
def state():
    scenario = MockAero()
    return scenario


@pytest.fixture()
def server(state):
    srv, _thread, _ = start_server(state)
    yield srv
    stop_server(srv)


@pytest.fixture()
def base_url(server):
    host, port = server.server_address
    return f"http://{host}:{port}"


@pytest.fixture()
def client(base_url):
    return AeroClient(base_url=base_url)


@pytest.fixture()
def authed(client):
    outcome = client.login("ada@example.com", "correct-horse")
    assert outcome.ok, "fixture login failed"
    return client
