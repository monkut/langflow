"""Tenant-aware dependency injection for database sessions."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from lfx.log.logger import logger
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.tenant_service import get_schema_by_prefix
from langflow.services.deps import get_db_service


async def get_tenant_prefix(request: Request) -> str | None:
    """Extract tenant prefix from request state.

    Args:
        request: FastAPI request object

    Returns:
        Tenant prefix if present, None otherwise
    """
    return getattr(request.state, "tenant_prefix", None)


async def get_tenant_schema_name(
    request: Request, tenant_prefix: Annotated[str | None, Depends(get_tenant_prefix)]
) -> str | None:
    """Get the database schema name for the current tenant.

    Args:
        request: FastAPI request object
        tenant_prefix: Tenant prefix from URL

    Returns:
        Schema name if tenant context exists, None for public schema

    Raises:
        HTTPException: If tenant prefix is provided but not found
    """
    if not tenant_prefix:
        return None

    # Check if schema name is already cached in request state
    if hasattr(request.state, "tenant_schema") and request.state.tenant_schema:
        return request.state.tenant_schema

    # Look up schema in PostgreSQL using public schema connection
    db_service = get_db_service()
    async with db_service.with_session() as session:
        # Ensure we're using public schema for the lookup
        await session.exec(text("SET search_path TO public"))

        schema_name = await get_schema_by_prefix(session, tenant_prefix)

        if not schema_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant schema not found for prefix: {tenant_prefix}",
            )

        # Cache in request state
        request.state.tenant_schema = schema_name
        return schema_name


@asynccontextmanager
async def get_tenant_session(schema_name: str | None = None):
    """Get a database session with the appropriate schema search path.

    Args:
        schema_name: Optional schema name to set. If None, uses public schema.

    Yields:
        AsyncSession configured for the tenant schema
    """
    db_service = get_db_service()

    async with db_service.with_session() as session:
        try:
            if schema_name:
                # Set search path to tenant schema with public fallback
                await session.exec(text(f'SET search_path TO "{schema_name}", public'))
                await logger.adebug(f"Session configured for schema: {schema_name}")
            else:
                # Use public schema
                await session.exec(text("SET search_path TO public"))
                await logger.adebug("Session configured for public schema")

            yield session

        except Exception as e:
            await logger.aerror(f"Error in tenant session: {e}")
            await session.rollback()
            raise
        finally:
            # Reset to public schema
            await session.exec(text("SET search_path TO public"))


async def get_tenant_aware_session(
    tenant_schema_name: Annotated[str | None, Depends(get_tenant_schema_name)]
) -> AsyncSession:
    """FastAPI dependency for getting a tenant-aware database session.

    This dependency should be used in route handlers that need database access
    with automatic tenant schema isolation.

    Args:
        tenant_schema_name: Schema name from tenant resolution

    Yields:
        AsyncSession configured for the tenant

    Example:
        @router.get("/flows")
        async def get_flows(
            session: Annotated[AsyncSession, Depends(get_tenant_aware_session)]
        ):
            # This session is automatically scoped to the tenant schema
            flows = await session.exec(select(Flow))
            return flows
    """
    async with get_tenant_session(tenant_schema_name) as session:
        yield session
