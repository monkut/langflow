#!/usr/bin/env python3
"""Langflow Multi-Tenant Helper Script.

This script provides CLI commands for managing tenant schemas and users
in a multi-tenant Langflow deployment.

Usage:
    python lfhelper.py schema-add --prefix {SCHEMA_PREFIX}
    python lfhelper.py schema-list
    python lfhelper.py user-add --schema {SCHEMA_ID} --username {USERNAME} [--password {PASSWORD}]
    python lfhelper.py user-reset --schema {SCHEMA_ID} --username {USERNAME} [--password {PASSWORD}]
    python lfhelper.py user-list --schema {SCHEMA_ID}
"""

import argparse
import asyncio
import os
import secrets
import string
import sys
from pathlib import Path

# Add src/backend/base to path for imports
backend_base = Path(__file__).parent / "src" / "backend" / "base"
sys.path.insert(0, str(backend_base))


async def setup_environment():
    """Initialize the Langflow environment and services."""
    from langflow.services.utils import initialize_settings_service

    # Initialize settings service
    initialize_settings_service()


def generate_password(length: int = 16) -> str:
    """Generate a secure random password.

    Args:
        length: Length of password to generate

    Returns:
        Random password string
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def schema_add(prefix: str) -> None:
    """Create a new tenant schema.

    Args:
        prefix: URL prefix for the tenant

    Raises:
        ValueError: If prefix already exists
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from langflow.services.database.tenant_service import get_or_create_tenant_schema, get_schema_by_prefix
    from langflow.services.deps import get_db_service

    db_service = get_db_service()

    async with db_service.with_session() as session:
        # Ensure we're in public schema
        await session.exec(text("SET search_path TO public"))

        # Check if prefix already exists
        existing = await get_schema_by_prefix(session, prefix)
        if existing:
            print(f"❌ Error: Schema with prefix '{prefix}' already exists: {existing}")
            sys.exit(1)

        # Create new schema
        try:
            schema_name = await get_or_create_tenant_schema(session, prefix)
            print(f"✅ Successfully created tenant schema:")
            print(f"   Prefix: {prefix}")
            print(f"   Schema ID: {schema_name}")
            print(f"   Created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        except Exception as e:
            print(f"❌ Error creating schema: {e}")
            sys.exit(1)


async def schema_list() -> None:
    """List all tenant schemas from PostgreSQL."""
    from sqlalchemy import text

    from langflow.services.database.tenant_service import list_all_schemas
    from langflow.services.deps import get_db_service

    db_service = get_db_service()

    async with db_service.with_session() as session:
        # Ensure we're in public schema
        await session.exec(text("SET search_path TO public"))

        schemas = await list_all_schemas(session, prefix_pattern="%-%")

        if not schemas:
            print("No tenant schemas found.")
            return

        print(f"\n{'Schema Name':<40} {'Prefix':<20}")
        print("-" * 60)

        for schema_row in schemas:
            # Extract schema name from Row object (always access first element)
            schema_name = str(schema_row[0])
            # Extract prefix (everything before first dash)
            prefix = schema_name.split("-")[0] if "-" in schema_name else schema_name
            print(f"{schema_name:<40} {prefix:<20}")

        print(f"\nTotal: {len(schemas)} schema(s)")


async def user_add(schema_id: str, username: str, password: str | None = None) -> None:
    """Add a user to a tenant schema.

    Args:
        schema_id: Schema identifier (format: prefix-hash)
        username: Username for the new user
        password: Optional password (auto-generated if not provided)
    """
    from sqlalchemy import text

    from langflow.services.database.models.user.crud import get_user_by_username
    from langflow.services.database.models.user.model import User
    from langflow.services.deps import get_db_service
    from langflow.services.deps_tenant import get_tenant_session

    # Generate password if not provided
    if not password:
        password = generate_password()
        auto_generated = True
    else:
        auto_generated = False

    db_service = get_db_service()

    # First, verify the schema exists in PostgreSQL
    async with db_service.with_session() as session:
        await session.exec(text("SET search_path TO public"))

        check_query = text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_namespace WHERE nspname = :schema_name
            )
        """).bindparams(schema_name=schema_id)
        result = await session.exec(check_query)
        exists = result.scalar()

        if not exists:
            print(f"❌ Error: Schema '{schema_id}' not found")
            sys.exit(1)

    # Now create the user in the tenant schema
    async with get_tenant_session(schema_id) as session:
        # Check if user already exists
        existing_user = await get_user_by_username(session, username)
        if existing_user:
            print(f"❌ Error: User '{username}' already exists in schema '{schema_id}'")
            sys.exit(1)

        # Hash the password
        from langflow.services.auth.utils import get_password_hash

        hashed_password = get_password_hash(password)

        # Create user
        user = User(username=username, password=hashed_password, is_active=True, is_superuser=False)

        session.add(user)
        await session.commit()
        await session.refresh(user)

        print(f"✅ Successfully created user:")
        print(f"   Schema: {schema_id}")
        print(f"   Username: {username}")
        if auto_generated:
            print(f"   Password: {password} (auto-generated)")
        else:
            print(f"   Password: ******** (provided)")
        print(f"   User ID: {user.id}")


async def user_reset(schema_id: str, username: str, password: str | None = None) -> None:
    """Reset a user's password in a tenant schema.

    Args:
        schema_id: Schema identifier (format: prefix-hash)
        username: Username to reset
        password: Optional new password (auto-generated if not provided)
    """
    from sqlalchemy import text

    from langflow.services.database.models.user.crud import get_user_by_username
    from langflow.services.deps import get_db_service
    from langflow.services.deps_tenant import get_tenant_session

    # Generate password if not provided
    if not password:
        password = generate_password()
        auto_generated = True
    else:
        auto_generated = False

    db_service = get_db_service()

    # First, verify the schema exists in PostgreSQL
    async with db_service.with_session() as session:
        await session.exec(text("SET search_path TO public"))

        check_query = text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_namespace WHERE nspname = :schema_name
            )
        """).bindparams(schema_name=schema_id)
        result = await session.exec(check_query)
        exists = result.scalar()

        if not exists:
            print(f"❌ Error: Schema '{schema_id}' not found")
            sys.exit(1)

    # Now reset the user's password in the tenant schema
    async with get_tenant_session(schema_id) as session:
        # Get user
        user = await get_user_by_username(session, username)
        if not user:
            print(f"❌ Error: User '{username}' not found in schema '{schema_id}'")
            sys.exit(1)

        # Hash the new password
        from langflow.services.auth.utils import get_password_hash

        user.password = get_password_hash(password)

        session.add(user)
        await session.commit()

        print(f"✅ Successfully reset password:")
        print(f"   Schema: {schema_id}")
        print(f"   Username: {username}")
        if auto_generated:
            print(f"   New Password: {password} (auto-generated)")
        else:
            print(f"   New Password: ******** (provided)")


async def user_list(schema_id: str) -> None:
    """List all users in a tenant schema.

    Args:
        schema_id: Schema identifier (format: prefix-hash)
    """
    from sqlalchemy import text
    from sqlmodel import select

    from langflow.services.database.models.user.model import User
    from langflow.services.deps import get_db_service
    from langflow.services.deps_tenant import get_tenant_session

    db_service = get_db_service()

    # First, verify the schema exists in PostgreSQL
    async with db_service.with_session() as session:
        await session.exec(text("SET search_path TO public"))

        check_query = text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_namespace WHERE nspname = :schema_name
            )
        """).bindparams(schema_name=schema_id)
        result = await session.exec(check_query)
        exists = result.scalar()

        if not exists:
            print(f"❌ Error: Schema '{schema_id}' not found")
            sys.exit(1)

    # Now list users in the tenant schema
    async with get_tenant_session(schema_id) as session:
        result = await session.exec(select(User).order_by(User.username))
        users = list(result.all())

        if not users:
            print(f"No users found in schema '{schema_id}'.")
            return

        print(f"\nUsers in schema '{schema_id}':")
        print(f"{'Username':<30} {'Active':<10} {'Superuser':<12} {'Last Login'}")
        print("-" * 90)

        for user in users:
            active = "Yes" if user.is_active else "No"
            superuser = "Yes" if user.is_superuser else "No"
            last_login = user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else "Never"
            print(f"{user.username:<30} {active:<10} {superuser:<12} {last_login}")

        print(f"\nTotal: {len(users)} user(s)")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Langflow Multi-Tenant Helper", formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # schema-add command
    schema_add_parser = subparsers.add_parser("schema-add", help="Create a new tenant schema")
    schema_add_parser.add_argument("--prefix", required=True, help="URL prefix for the tenant")

    # schema-list command
    subparsers.add_parser("schema-list", help="List all tenant schemas")

    # user-add command
    user_add_parser = subparsers.add_parser("user-add", help="Add a user to a tenant schema")
    user_add_parser.add_argument("--schema", required=True, help="Schema ID (format: prefix-hash)")
    user_add_parser.add_argument("--username", required=True, help="Username for the new user")
    user_add_parser.add_argument("--password", help="Password (auto-generated if not provided)")

    # user-reset command
    user_reset_parser = subparsers.add_parser("user-reset", help="Reset a user's password")
    user_reset_parser.add_argument("--schema", required=True, help="Schema ID (format: prefix-hash)")
    user_reset_parser.add_argument("--username", required=True, help="Username to reset")
    user_reset_parser.add_argument("--password", help="New password (auto-generated if not provided)")

    # user-list command
    user_list_parser = subparsers.add_parser("user-list", help="List users in a tenant schema")
    user_list_parser.add_argument("--schema", required=True, help="Schema ID (format: prefix-hash)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the async function
    asyncio.run(setup_environment())

    if args.command == "schema-add":
        asyncio.run(schema_add(args.prefix))
    elif args.command == "schema-list":
        asyncio.run(schema_list())
    elif args.command == "user-add":
        asyncio.run(user_add(args.schema, args.username, args.password))
    elif args.command == "user-reset":
        asyncio.run(user_reset(args.schema, args.username, args.password))
    elif args.command == "user-list":
        asyncio.run(user_list(args.schema))


if __name__ == "__main__":
    main()
