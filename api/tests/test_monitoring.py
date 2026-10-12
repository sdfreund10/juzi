import json

import pytest
import sentry_sdk
from django.core.handlers.wsgi import WSGIHandler
from django.http import HttpRequest
from django.test import RequestFactory, override_settings
from django.urls import path
from sentry_sdk.transport import Transport

from config.monitoring import initialize_sentry


class MemoryTransport(Transport):
    def __init__(self, options):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


def crash(request: HttpRequest):
    raise RuntimeError("Controlled backend failure")


urlpatterns = [path("monitoring-test/", crash)]


@pytest.fixture
def monitoring(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.com/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
    monkeypatch.setenv("SENTRY_RELEASE", "commit-sha")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "1")
    previous_client = sentry_sdk.get_client()
    original_init = sentry_sdk.init

    def init(**options):
        return original_init(**options, transport=MemoryTransport)

    monkeypatch.setattr(sentry_sdk, "init", init)
    with sentry_sdk.isolation_scope():
        initialize_sentry()
        client = sentry_sdk.get_client()
        yield client
        client.close()
        sentry_sdk.get_global_scope().set_client(previous_client)


def test_missing_dsn_leaves_monitoring_disabled(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    initialize_sentry()
    assert not sentry_sdk.get_client().is_active()


@pytest.mark.django_db(transaction=True)
@override_settings(ROOT_URLCONF=__name__)
def test_django_exception_and_trace_are_captured_without_private_data(monitoring):
    request = RequestFactory().post(
        "/monitoring-test/",
        data={"password": "private-password", "study": "private-study"},
        HTTP_COOKIE="sessionid=private-cookie; csrftoken=" + "a" * 32,
        HTTP_X_CSRFTOKEN="a" * 32,
        HTTP_SENTRY_TRACE="0123456789abcdef0123456789abcdef-0123456789abcdef-1",
    )
    statuses = []
    response = WSGIHandler()(request.environ, lambda status, headers: statuses.append(status))
    list(response)
    response.close()
    assert statuses[0].startswith("500")
    monitoring.flush()
    events = [
        item.get_event()
        for envelope in monitoring.transport.envelopes
        for item in envelope.items
        if item.type == "event"
    ]
    assert len(events) == 1
    assert events[0]["exception"]["values"][0]["value"] == "Controlled backend failure"
    assert events[0]["release"] == "commit-sha"
    assert events[0]["environment"] == "test"
    assert "request" not in events[0]
    assert "user" not in events[0]
    assert "private-" not in json.dumps(events)
    assert all(
        "vars" not in frame
        for value in events[0]["exception"]["values"]
        for frame in value["stacktrace"]["frames"]
    )
    transactions = [
        item.payload.json
        for envelope in monitoring.transport.envelopes
        for item in envelope.items
        if item.type == "transaction"
    ]
    assert len(transactions) == 1
    assert transactions[0]["contexts"]["trace"]["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert (
        transactions[0]["contexts"]["trace"]["trace_id"]
        == events[0]["contexts"]["trace"]["trace_id"]
    )
    assert monitoring.options["traces_sample_rate"] == 1
