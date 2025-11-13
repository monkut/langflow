"""Tenant schema model for multi-tenancy support."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from langflow.schema.serialize import UUIDstr


class TenantSchema(SQLModel, table=True):  # type: ignore[call-arg]
    """Registry of tenant schemas for multi-tenancy.

    This table resides in the public schema and maps URL prefixes
    to PostgreSQL schemas for tenant isolation.
    """

    __tablename__ = "tenant_schemas"

    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    prefix: str = Field(index=True, unique=True, max_length=50)
    """URL prefix for this tenant (e.g., 'acme' for /tenant/acme/...)"""

    schema_name: str = Field(index=True, unique=True, max_length=63)
    """PostgreSQL schema name (prefix-hash, e.g., 'acme-a1b2c3')"""

    is_active: bool = Field(default=True)
    """Whether this tenant schema is currently active"""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TenantSchemaCreate(SQLModel):
    """Model for creating a new tenant schema."""

    prefix: str = Field(max_length=50)


class TenantSchemaRead(SQLModel):
    """Model for reading tenant schema information."""

    id: UUID = Field(default_factory=uuid4)
    prefix: str
    schema_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
