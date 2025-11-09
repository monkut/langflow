"""Tenant schema switching middleware for multi-tenancy support."""

import re
from typing import Any

from fastapi import Request, Response
from lfx.log.logger import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Regex to extract tenant prefix from URL path
# Matches: /tenant/{prefix}/... or /tenant/{prefix} or /{prefix}/api/v1/...
TENANT_PATH_REGEX = re.compile(r"^/tenant/([a-zA-Z0-9_-]+)")


class TenantSchemaMiddleware(BaseHTTPMiddleware):
    """Middleware to set PostgreSQL search_path based on request URL prefix.

    This middleware extracts the tenant identifier from the URL path and stores it
    in request.state for use by the database service.

    URL Format: /tenant/{prefix}/api/v1/...
    Example: /tenant/acme/api/v1/flows -> sets search_path to 'acme-a1b2c3'
    """

    def __init__(self, app: Any):  # noqa: ANN401
        super().__init__(app)
        self._logged_init = False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Extract tenant prefix from URL and store in request state.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            Response from the application
        """
        # Skip tenant extraction for health check and static files
        if request.url.path in ["/health", "/api/v1/health", "/healthz"]:
            request.state.tenant_prefix = None
            request.state.tenant_schema = None
            return await call_next(request)

        # Extract tenant prefix from URL
        match = TENANT_PATH_REGEX.match(request.url.path)
        if match:
            tenant_prefix = match.group(1)
            request.state.tenant_prefix = tenant_prefix

            if not self._logged_init:
                await logger.adebug(f"Tenant middleware initialized, extracted prefix: {tenant_prefix}")
                self._logged_init = True
        else:
            # No tenant prefix in URL, use public schema
            request.state.tenant_prefix = None
            request.state.tenant_schema = None

        # The actual schema lookup and search_path setting will be done
        # in the database service's with_session method
        return await call_next(request)
