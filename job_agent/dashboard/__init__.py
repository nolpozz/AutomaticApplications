"""Local web dashboard (FastAPI). Import ``create_app`` lazily."""

__all__ = ["create_app"]


def create_app():  # type: ignore[no-untyped-def]
    from job_agent.dashboard.app import create_app as _factory

    return _factory()
