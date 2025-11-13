"""Tenant-aware database service extensions."""

import hashlib
import secrets
from contextvars import ContextVar

from lfx.log.logger import logger
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

# Context variable to store current tenant schema name
current_tenant_schema: ContextVar[str | None] = ContextVar("current_tenant_schema", default=None)


def generate_schema_name(prefix: str, hash_length: int = 6) -> str:
    """Generate a unique schema name with prefix and hash.

    Args:
        prefix: URL prefix for the tenant
        hash_length: Length of the random hash to append

    Returns:
        Schema name in format: {prefix}-{hash}

    Example:
        generate_schema_name("acme") -> "acme-a1b2c3"
    """
    # Generate a random hash
    random_bytes = secrets.token_bytes(hash_length)
    hash_str = hashlib.sha256(random_bytes).hexdigest()[:hash_length]

    # PostgreSQL schema names are limited to 63 characters
    # Format: prefix-hash
    max_prefix_length = 63 - hash_length - 1  # -1 for the dash
    safe_prefix = prefix[:max_prefix_length].lower().replace("-", "_")

    return f"{safe_prefix}-{hash_str}"


async def create_tenant_schema_in_db(session: AsyncSession, schema_name: str) -> None:
    """Create a new PostgreSQL schema.

    Args:
        session: Database session
        schema_name: Name of the schema to create

    Raises:
        RuntimeError: If schema creation fails
    """
    try:
        # Create the schema
        await session.exec(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        await session.commit()
        await logger.adebug(f"Created PostgreSQL schema: {schema_name}")
    except Exception as e:
        await logger.aerror(f"Failed to create schema {schema_name}: {e}")
        await session.rollback()
        raise


async def initialize_tenant_schema(
    session: AsyncSession, schema_name: str, source_schema: str = "public"
) -> None:
    """Initialize a tenant schema by copying structure from source schema.

    This function creates all Langflow tables in the tenant schema by copying
    from the public schema.

    Args:
        session: Database session
        schema_name: Name of the tenant schema to initialize
        source_schema: Name of the schema to copy structure from (default: public)

    Raises:
        RuntimeError: If initialization fails
    """
    try:
        # Create schema if not exists (already done, but safe to repeat)
        await session.exec(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

        # Copy table structure from public schema to tenant schema
        # This uses PostgreSQL's CREATE TABLE ... LIKE syntax
        tables_to_copy = [
            "user",
            "apikey",
            "flow",
            "folder",
            "message",
            "variable",
            "transaction",
            "vertex_build",
            "file",
        ]

        for table_name in tables_to_copy:
            # Check if table exists in source schema
            check_stmt = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = '{source_schema}'
                AND table_name = '{table_name}'
            )
            """
            result = await session.exec(text(check_stmt))
            exists = result.scalar()

            if exists:
                # Create table in tenant schema by copying structure from public
                copy_stmt = f"""
                CREATE TABLE IF NOT EXISTS "{schema_name}".{table_name}
                (LIKE {source_schema}.{table_name} INCLUDING ALL)
                """
                try:
                    await session.exec(text(copy_stmt))
                    await logger.adebug(f"Created table {table_name} in schema {schema_name}")
                except Exception as table_error:
                    await logger.aerror(f"Could not copy table {table_name}: {table_error}")
            else:
                await logger.adebug(f"Table {table_name} does not exist in {source_schema}, skipping")

        await session.commit()
        await logger.adebug(f"Initialized schema {schema_name} with database structure")

    except Exception as e:
        await logger.aerror(f"Failed to initialize schema {schema_name}: {e}")
        await session.rollback()
        raise


async def set_search_path_for_session(session: AsyncSession, schema_name: str) -> None:
    """Set the PostgreSQL search_path for a session.

    Args:
        session: Database session
        schema_name: Schema name to set as search path
    """
    try:
        # Set search path with fallback to public
        await session.exec(text(f'SET search_path TO "{schema_name}", public'))
        current_tenant_schema.set(schema_name)
        await logger.adebug(f"Set search_path to: {schema_name}")
    except Exception as e:
        await logger.aerror(f"Failed to set search_path to {schema_name}: {e}")
        raise


async def get_schema_by_prefix(session: AsyncSession, prefix: str) -> str | None:
    """Find existing tenant schema by prefix.

    Args:
        session: Database session
        prefix: URL prefix for the tenant

    Returns:
        Schema name if found, None otherwise
    """
    # Query pg_namespace for schemas matching the prefix pattern
    query = text("""
        SELECT nspname
        FROM pg_namespace
        WHERE nspname LIKE :pattern
        ORDER BY nspname
        LIMIT 1
    """).bindparams(pattern=f"{prefix}-%")
    result = await session.exec(query)
    schema_name = result.scalar()

    if schema_name:
        await logger.adebug(f"Found existing schema for prefix '{prefix}': {schema_name}")

    return schema_name


async def list_all_schemas(session: AsyncSession, prefix_pattern: str = "%") -> list[str]:
    """List all tenant schemas matching a prefix pattern.

    Args:
        session: Database session
        prefix_pattern: SQL LIKE pattern for schema names (default: all schemas)

    Returns:
        List of schema names
    """
    query = text("""
        SELECT nspname
        FROM pg_namespace
        WHERE nspname LIKE :pattern
        AND nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
        ORDER BY nspname
    """).bindparams(pattern=prefix_pattern)
    result = await session.exec(query)
    return list(result.all())


async def get_or_create_tenant_schema(session: AsyncSession, prefix: str) -> str:
    """Get existing tenant schema or create a new one.

    Args:
        session: Database session (must use public schema)
        prefix: URL prefix for the tenant

    Returns:
        Schema name (format: {prefix}-{hash})

    Raises:
        ValueError: If prefix is invalid
        RuntimeError: If schema creation fails
    """
    # Validate prefix
    if not prefix or len(prefix) > 50:
        msg = "Prefix must be between 1 and 50 characters"
        raise ValueError(msg)

    # Check if schema already exists
    existing = await get_schema_by_prefix(session, prefix)
    if existing:
        await logger.adebug(f"Found existing tenant schema for prefix: {prefix}")
        return existing

    # Generate unique schema name
    schema_name = generate_schema_name(prefix)

    # Verify uniqueness by checking PostgreSQL directly
    check_query_template = text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_namespace WHERE nspname = :schema_name
        )
    """)
    check_query = check_query_template.bindparams(schema_name=schema_name)
    result = await session.exec(check_query)
    exists = result.scalar()

    while exists:
        # Collision detected, regenerate
        schema_name = generate_schema_name(prefix)
        check_query = check_query_template.bindparams(schema_name=schema_name)
        result = await session.exec(check_query)
        exists = result.scalar()

    await logger.adebug(f"Creating new tenant schema: {prefix} -> {schema_name}")

    # Create the actual PostgreSQL schema
    await create_tenant_schema_in_db(session, schema_name)

    # Initialize the schema with tables
    await initialize_tenant_schema(session, schema_name)

    return schema_name
