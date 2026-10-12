import os

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration


def scrub_sentry_event(event: dict) -> dict:
    """Keep account details, headers, cookies, and submitted study data out of events."""
    event.pop("user", None)
    event.pop("request", None)
    event.pop("breadcrumbs", None)
    return event


def initialize_sentry() -> None:
    """A DSN explicitly opts this process into reporting, including development."""
    if not (sentry_dsn := os.getenv("SENTRY_DSN")):
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[DjangoIntegration()],
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        release=os.getenv("SENTRY_RELEASE"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1")),
        trace_lifecycle="static",
        data_collection={
            "user_info": False,
            "cookies": False,
            "http_headers": False,
            "http_bodies": [],
            "url_query_params": False,
            "database_query_data": False,
            "stack_frame_variables": False,
        },
        include_local_variables=False,
        max_request_body_size="never",
        before_send=lambda event, hint: scrub_sentry_event(event),
        before_send_transaction=lambda event, hint: scrub_sentry_event(event),
    )
