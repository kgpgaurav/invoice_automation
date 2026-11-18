"""Explicitly public assignment credentials, separate from private provider secrets."""

from typing import Literal

from fastapi import Response
from pydantic import BaseModel

from app.contracts import API_PREFIX


class DemoCredential(BaseModel):
    role: Literal["submitter", "reviewer"]
    token: str


class DemoAccess(BaseModel):
    roles: list[DemoCredential]


def add_demo_access_route(app, settings):
    @app.get(f"{API_PREFIX}/demo-access", response_model=DemoAccess)
    def demo_access(response: Response):
        response.headers["Cache-Control"] = "no-store"
        if not settings.public_demo_access:
            return DemoAccess(roles=[])
        return DemoAccess(
            roles=[
                DemoCredential(role="submitter", token=settings.app_api_token.get_secret_value()),
                DemoCredential(
                    role="reviewer", token=settings.reviewer_api_token.get_secret_value()
                ),
            ]
        )
