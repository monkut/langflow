"""CRUD operations for tenant schemas."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.tenant.model import TenantSchema


async def get_tenant_schema_by_prefix(session: AsyncSession, prefix: str) -> TenantSchema | None:
    """Get a tenant schema by its URL prefix.

    Args:
        session: Database session
        prefix: URL prefix (e.g., 'acme')

    Returns:
        TenantSchema if found, None otherwise
    """
    statement = select(TenantSchema).where(TenantSchema.prefix == prefix, TenantSchema.is_active == True)  # noqa: E712
    result = await session.exec(statement)
    return result.first()


async def get_tenant_schema_by_name(session: AsyncSession, schema_name: str) -> TenantSchema | None:
    """Get a tenant schema by its database schema name.

    Args:
        session: Database session
        schema_name: PostgreSQL schema name (e.g., 'acme-a1b2c3')

    Returns:
        TenantSchema if found, None otherwise
    """
    statement = select(TenantSchema).where(
        TenantSchema.schema_name == schema_name, TenantSchema.is_active == True  # noqa: E712
    )
    result = await session.exec(statement)
    return result.first()


async def list_all_tenant_schemas(session: AsyncSession, include_inactive: bool = False) -> list[TenantSchema]:
    """List all tenant schemas.

    Args:
        session: Database session
        include_inactive: Whether to include inactive schemas

    Returns:
        List of TenantSchema objects
    """
    if include_inactive:
        statement = select(TenantSchema).order_by(TenantSchema.created_at)
    else:
        statement = select(TenantSchema).where(TenantSchema.is_active == True).order_by(  # noqa: E712
            TenantSchema.created_at
        )

    result = await session.exec(statement)
    return list(result.all())


async def create_tenant_schema(session: AsyncSession, tenant: TenantSchema) -> TenantSchema:
    """Create a new tenant schema record.

    Args:
        session: Database session
        tenant: TenantSchema object to create

    Returns:
        Created TenantSchema object
    """
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def deactivate_tenant_schema(session: AsyncSession, prefix: str) -> TenantSchema | None:
    """Deactivate a tenant schema.

    Args:
        session: Database session
        prefix: URL prefix of the schema to deactivate

    Returns:
        Updated TenantSchema if found, None otherwise
    """
    tenant = await get_tenant_schema_by_prefix(session, prefix)
    if tenant:
        tenant.is_active = False
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant
