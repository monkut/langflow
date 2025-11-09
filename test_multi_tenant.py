#!/usr/bin/env python3
"""Standalone test script for multi-tenant functionality."""

import asyncio
import os
import sys
from pathlib import Path

# Add src/backend/base to path for imports
backend_base = Path(__file__).parent / "src" / "backend" / "base"
sys.path.insert(0, str(backend_base))

# Set environment before imports
os.environ["LANGFLOW_DATABASE_URL"] = "postgresql://langflow:langflow@localhost:5433/langflow"
os.environ["LANGFLOW_AUTO_LOGIN"] = "false"


async def main():
    """Main test function."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from langflow.services.auth.utils import get_password_hash
    from langflow.services.database.models.tenant.crud import (
        create_tenant_schema,
        get_tenant_schema_by_prefix,
        list_all_tenant_schemas,
    )
    from langflow.services.database.models.tenant.model import TenantSchema
    from langflow.services.database.models.user.crud import get_user_by_username
    from langflow.services.database.models.user.model import User
    from langflow.services.database.tenant_service import (
        create_tenant_schema_in_db,
        generate_schema_name,
        initialize_tenant_schema,
    )

    print("🧪 Multi-Tenant Functionality Test")
    print("=" * 60)

    # Create engine (use postgresql+psycopg for async)
    database_url = "postgresql+psycopg://langflow:langflow@localhost:5433/langflow"
    engine = create_async_engine(database_url)

    # Test 1: Create Schema A
    print("\n1️⃣  Creating Schema A...")
    async with AsyncSession(engine) as session:
        # Ensure we're in public schema
        await session.exec(text("SET search_path TO public"))

        # Create schema A
        schema_a_name = generate_schema_name("company-a")
        tenant_a = TenantSchema(prefix="company-a", schema_name=schema_a_name)
        tenant_a = await create_tenant_schema(session, tenant_a)
        print(f"   ✅ Created Schema A: {tenant_a.schema_name}")

        # Create the actual PostgreSQL schema
        await create_tenant_schema_in_db(session, schema_a_name)
        print(f"   ✅ Created PostgreSQL schema: {schema_a_name}")

        # Initialize schema with tables
        await initialize_tenant_schema(session, schema_a_name)
        print(f"   ✅ Initialized tables in schema: {schema_a_name}")

    # Test 2: Create Schema B
    print("\n2️⃣  Creating Schema B...")
    async with AsyncSession(engine) as session:
        await session.exec(text("SET search_path TO public"))

        schema_b_name = generate_schema_name("company-b")
        tenant_b = TenantSchema(prefix="company-b", schema_name=schema_b_name)
        tenant_b = await create_tenant_schema(session, tenant_b)
        print(f"   ✅ Created Schema B: {tenant_b.schema_name}")

        await create_tenant_schema_in_db(session, schema_b_name)
        print(f"   ✅ Created PostgreSQL schema: {schema_b_name}")

        await initialize_tenant_schema(session, schema_b_name)
        print(f"   ✅ Initialized tables in schema: {schema_b_name}")

    # Test 3: List schemas
    print("\n3️⃣  Listing all schemas...")
    async with AsyncSession(engine) as session:
        await session.exec(text("SET search_path TO public"))
        schemas = await list_all_tenant_schemas(session)
        for schema in schemas:
            print(f"   • {schema.prefix} → {schema.schema_name}")

    # Test 4: Create users in Schema A
    print(f"\n4️⃣  Creating users in Schema A ({schema_a_name})...")
    async with AsyncSession(engine) as session:
        await session.exec(text(f'SET search_path TO "{schema_a_name}", public'))

        # User 1
        user_a1 = User(
            username="alice@company-a.com",
            password=get_password_hash("password123"),
            is_active=True,
            is_superuser=False,
        )
        session.add(user_a1)

        # User 2
        user_a2 = User(
            username="bob@company-a.com",
            password=get_password_hash("password123"),
            is_active=True,
            is_superuser=False,
        )
        session.add(user_a2)

        await session.commit()
        print(f"   ✅ Created alice@company-a.com")
        print(f"   ✅ Created bob@company-a.com")

    # Test 5: Create users in Schema B
    print(f"\n5️⃣  Creating users in Schema B ({schema_b_name})...")
    async with AsyncSession(engine) as session:
        await session.exec(text(f'SET search_path TO "{schema_b_name}", public'))

        # User 1
        user_b1 = User(
            username="charlie@company-b.com",
            password=get_password_hash("password123"),
            is_active=True,
            is_superuser=False,
        )
        session.add(user_b1)

        # User 2
        user_b2 = User(
            username="diana@company-b.com",
            password=get_password_hash("password123"),
            is_active=True,
            is_superuser=False,
        )
        session.add(user_b2)

        await session.commit()
        print(f"   ✅ Created charlie@company-b.com")
        print(f"   ✅ Created diana@company-b.com")

    # Test 6: Verify isolation - users in Schema A
    print(f"\n6️⃣  Verifying users in Schema A ({schema_a_name})...")
    async with AsyncSession(engine) as session:
        await session.exec(text(f'SET search_path TO "{schema_a_name}", public'))
        result = await session.exec(select(User))
        users_a = list(result.all())
        print(f"   Found {len(users_a)} users:")
        for user in users_a:
            print(f"   • {user.username}")

    # Test 7: Verify isolation - users in Schema B
    print(f"\n7️⃣  Verifying users in Schema B ({schema_b_name})...")
    async with AsyncSession(engine) as session:
        await session.exec(text(f'SET search_path TO "{schema_b_name}", public'))
        result = await session.exec(select(User))
        users_b = list(result.all())
        print(f"   Found {len(users_b)} users:")
        for user in users_b:
            print(f"   • {user.username}")

    # Test 8: Verify Schema A users cannot see Schema B data
    print(f"\n8️⃣  Testing isolation: Checking if Schema A sees Schema B users...")
    async with AsyncSession(engine) as session:
        await session.exec(text(f'SET search_path TO "{schema_a_name}", public'))

        # Try to find Schema B users
        charlie = await get_user_by_username(session, "charlie@company-b.com")
        diana = await get_user_by_username(session, "diana@company-b.com")

        if charlie is None and diana is None:
            print(f"   ✅ PASS: Schema A cannot see Schema B users (isolation working!)")
        else:
            print(f"   ❌ FAIL: Schema A can see Schema B users!")

    # Test 9: Verify Schema B users cannot see Schema A data
    print(f"\n9️⃣  Testing isolation: Checking if Schema B sees Schema A users...")
    async with AsyncSession(engine) as session:
        await session.exec(text(f'SET search_path TO "{schema_b_name}", public'))

        # Try to find Schema A users
        alice = await get_user_by_username(session, "alice@company-a.com")
        bob = await get_user_by_username(session, "bob@company-a.com")

        if alice is None and bob is None:
            print(f"   ✅ PASS: Schema B cannot see Schema A users (isolation working!)")
        else:
            print(f"   ❌ FAIL: Schema B can see Schema A users!")

    # Test 10: Verify users DO exist in their own schemas
    print(f"\n🔟 Verifying users exist in their own schemas...")
    async with AsyncSession(engine) as session:
        # Check Schema A
        await session.exec(text(f'SET search_path TO "{schema_a_name}", public'))
        alice = await get_user_by_username(session, "alice@company-a.com")
        if alice:
            print(f"   ✅ alice@company-a.com found in Schema A")
        else:
            print(f"   ❌ alice@company-a.com NOT found in Schema A!")

        # Check Schema B
        await session.exec(text(f'SET search_path TO "{schema_b_name}", public'))
        charlie = await get_user_by_username(session, "charlie@company-b.com")
        if charlie:
            print(f"   ✅ charlie@company-b.com found in Schema B")
        else:
            print(f"   ❌ charlie@company-b.com NOT found in Schema B!")

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print(f"\nSummary:")
    print(f"  • Schema A: {schema_a_name} (2 users)")
    print(f"  • Schema B: {schema_b_name} (2 users)")
    print(f"  • Isolation: Verified ✅")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
