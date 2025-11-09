# Multi-Tenant Langflow Implementation Summary

This document describes the multi-tenant implementation for Langflow using PostgreSQL schema-based isolation.

## Overview

The implementation provides complete tenant isolation using PostgreSQL schemas, with URL-based routing and a CLI helper for management. Each tenant's data is stored in a separate database schema, ensuring data isolation at the database level.

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx (Reverse Proxy)                │
│                    URL-based tenant routing                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Langflow Application                       │
│  ┌────────────────────────────────────────────────────┐    │
│  │  TenantSchemaMiddleware                             │    │
│  │  - Extracts tenant prefix from URL                  │    │
│  │  - Stores in request.state                          │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Tenant-aware Database Service                      │    │
│  │  - Looks up schema by prefix                        │    │
│  │  - Sets PostgreSQL search_path                      │    │
│  │  - Manages schema lifecycle                         │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL 17 (Aurora Serverless)               │
│  ┌────────────────────────────────────────────────────┐    │
│  │  public schema                                      │    │
│  │  └── tenant_schemas (registry table)               │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  acme-a1b2c3 schema                                │    │
│  │  ├── user                                           │    │
│  │  ├── flow                                           │    │
│  │  ├── folder                                         │    │
│  │  └── ... (all other tables)                        │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  globex-d4e5f6 schema                              │    │
│  │  ├── user                                           │    │
│  │  └── ...                                            │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow

1. **Client Request**: `GET /tenant/acme/api/v1/flows`
2. **Nginx**: Routes to Langflow, adds `X-Tenant-Prefix: acme` header
3. **TenantSchemaMiddleware**:
   - Extracts prefix from URL: `acme`
   - Stores in `request.state.tenant_prefix`
4. **Database Session Creation**:
   - Queries `public.tenant_schemas` for prefix `acme`
   - Finds schema: `acme-a1b2c3`
   - Executes: `SET search_path TO "acme-a1b2c3", public`
5. **Route Handler**: Processes request with tenant-scoped session
6. **Response**: Returns data from `acme-a1b2c3` schema only

## File Structure

### New Files Created

```
langflow/
├── lfhelper.py                                    # CLI management tool
├── deploy/multi-tenant/                           # Deployment configuration
│   ├── Dockerfile                                 # Production Docker image
│   ├── docker-compose.yml                         # Multi-service orchestration
│   ├── nginx.conf                                 # Reverse proxy config
│   ├── .env.example                               # Environment template
│   ├── README.md                                  # Deployment guide
│   ├── start.sh                                   # Startup script
│   ├── test-setup.sh                              # Automated tests
│   └── postgres-init/
│       └── 01-init.sql                            # Database initialization
└── src/backend/base/langflow/
    ├── middleware/
    │   ├── __init__.py                            # Middleware exports
    │   └── tenant.py                              # Tenant schema middleware
    ├── services/
    │   ├── database/
    │   │   ├── models/
    │   │   │   ├── __init__.py                    # Updated with TenantSchema
    │   │   │   └── tenant/
    │   │   │       ├── __init__.py                # Tenant model exports
    │   │   │       ├── model.py                   # TenantSchema model
    │   │   │       └── crud.py                    # Tenant CRUD operations
    │   │   └── tenant_service.py                  # Tenant schema management
    │   └── deps_tenant.py                         # Tenant-aware dependencies
    └── main.py                                    # Updated with middleware
```

### Modified Files

1. **`src/backend/base/langflow/main.py`**:
   - Added `TenantSchemaMiddleware` import
   - Registered middleware in `create_app()`

2. **`src/backend/base/langflow/services/database/models/__init__.py`**:
   - Added `TenantSchema` to imports and `__all__`

3. **`src/backend/base/langflow/alembic/versions/fd66d4ee29f0_add_tenant_schemas_table.py`** (REQUIRED):
   - Alembic migration file for creating the `tenant_schemas` table
   - Revision ID: `fd66d4ee29f0`
   - Revises: `d9a6ea21edcd` (must be after latest Langflow migration)
   - **CRITICAL**: This migration file MUST be included in the Docker image
   - Without this file, Langflow will fail to start with a migration mismatch error
   - The migration creates:
     - `tenant_schemas` table with all required columns
     - Unique indexes on `prefix` and `schema_name`
     - Proper UUID, timestamp, and boolean fields

## Database Schema

### Registry Table (public.tenant_schemas)

```sql
CREATE TABLE public.tenant_schemas (
    id UUID PRIMARY KEY,
    prefix VARCHAR(50) UNIQUE NOT NULL,      -- URL prefix (e.g., 'acme')
    schema_name VARCHAR(63) UNIQUE NOT NULL, -- PG schema (e.g., 'acme-a1b2c3')
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_tenant_schemas_prefix ON public.tenant_schemas(prefix);
CREATE INDEX idx_tenant_schemas_schema_name ON public.tenant_schemas(schema_name);
```

### Tenant Schema Structure

Each tenant schema contains all Langflow tables:

```sql
CREATE SCHEMA "acme-a1b2c3";

SET search_path TO "acme-a1b2c3";

-- All Langflow tables are created in this schema
CREATE TABLE "user" (...);
CREATE TABLE "flow" (...);
CREATE TABLE "folder" (...);
CREATE TABLE "api_key" (...);
CREATE TABLE "variable" (...);
-- etc.
```

## API Changes

### URL Format

- **Public/Admin**: `http://domain.com/api/v1/...`
- **Tenant**: `http://domain.com/tenant/{prefix}/api/v1/...`

### Examples

```bash
# Public health check (no tenant)
GET /health

# Admin login (public schema)
POST /api/v1/login

# Tenant-specific flows (acme schema)
GET /tenant/acme/api/v1/flows

# Tenant-specific user management (globex schema)
POST /tenant/globex/api/v1/users
```

## Helper Script (lfhelper.py)

### Commands

#### Schema Management

```bash
# Create a new tenant schema
python lfhelper.py schema-add --prefix acme

# List all schemas
python lfhelper.py schema-list
```

#### User Management

```bash
# Add user with auto-generated password
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com

# Add user with custom password
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com --password SecurePass123!

# Reset user password
python lfhelper.py user-reset --schema acme-a1b2c3 --username admin@acme.com

# List users in schema
python lfhelper.py user-list --schema acme-a1b2c3
```

## Deployment

### Local Development

```bash
cd deploy/multi-tenant
./start.sh
```

### Production (AWS Fargate + Aurora)

1. **Build and push image**:
   ```bash
   docker build -t your-registry/langflow:multi-tenant -f deploy/multi-tenant/Dockerfile .
   docker push your-registry/langflow:multi-tenant
   ```

2. **Create Aurora Serverless PostgreSQL cluster** (PostgreSQL 15+)

3. **Create ECS Task Definition** with environment variables:
   ```bash
   LANGFLOW_DATABASE_URL=postgresql://user:pass@aurora-cluster:5432/langflow
   LANGFLOW_WORKERS=4
   LANGFLOW_POOL_SIZE=20
   LANGFLOW_MAX_OVERFLOW=30
   ```

4. **Configure ALB**:
   - Health check: `/health`
   - Path pattern: `/tenant/*`
   - Sticky sessions: Enabled

5. **Auto-scaling**: Target tracking on CPU 70%

## Security Features

1. **Schema Isolation**: Complete data separation at database level
2. **URL-based Routing**: Tenant identification via URL prefix
3. **Collision Prevention**: 6-character random hash prevents conflicts
4. **Password Security**: Auto-generated secure passwords
5. **Rate Limiting**: Nginx-based request throttling
6. **Connection Pooling**: Prevents resource exhaustion

## Performance Optimization

### Database Settings

```yaml
# PostgreSQL tuning for multi-tenant workload
max_connections: 200
shared_buffers: 256MB
effective_cache_size: 1GB
work_mem: 1MB
```

### Application Settings

```bash
# Worker configuration
LANGFLOW_WORKERS=4

# Connection pool
LANGFLOW_POOL_SIZE=20
LANGFLOW_MAX_OVERFLOW=30
```

## Monitoring

### Health Checks

```bash
# Application health
curl http://localhost:7860/health

# Database health
docker-compose exec postgres pg_isready -U langflow

# Schema sizes
docker-compose exec postgres psql -U langflow -d langflow -c "SELECT * FROM public.get_schema_sizes();"
```

### Logs

```bash
# View application logs
docker-compose logs -f langflow

# View tenant-specific activity
docker-compose logs langflow | grep "acme-a1b2c3"

# View PostgreSQL logs
docker-compose logs postgres
```

## Testing

### Automated Test Suite

```bash
cd deploy/multi-tenant
./test-setup.sh
```

Tests include:
- Service health checks
- Schema creation and listing
- User management operations
- Schema isolation verification
- Duplicate prevention
- Password reset functionality

### Manual Testing

```bash
# 1. Create schema
docker-compose exec langflow python lfhelper.py schema-add --prefix testco

# 2. Add user
docker-compose exec langflow python lfhelper.py user-add --schema testco-XXXXXX --username test@test.com

# 3. Verify in database
docker-compose exec postgres psql -U langflow -d langflow -c "SELECT * FROM public.tenant_schemas;"

# 4. Check schema contents
docker-compose exec postgres psql -U langflow -d langflow -c "SET search_path TO \"testco-XXXXXX\"; SELECT * FROM \"user\";"
```

## Migration from Single-Tenant

If you have existing Langflow data:

1. **Backup current database**:
   ```bash
   pg_dump -U langflow langflow > backup.sql
   ```

2. **Export existing data to tenant schema**:
   ```sql
   -- Create new tenant schema
   CREATE SCHEMA "existing-tenant";

   -- Copy all tables
   CREATE TABLE "existing-tenant".user AS SELECT * FROM public.user;
   CREATE TABLE "existing-tenant".flow AS SELECT * FROM public.flow;
   -- ... repeat for all tables
   ```

3. **Register in tenant_schemas**:
   ```sql
   INSERT INTO public.tenant_schemas (id, prefix, schema_name, is_active)
   VALUES (gen_random_uuid(), 'existing', 'existing-tenant', true);
   ```

## Troubleshooting

### Issue: Schema not found

**Symptom**: 404 error when accessing `/tenant/acme/`

**Solution**:
```bash
# Check if schema exists
python lfhelper.py schema-list

# Create if missing
python lfhelper.py schema-add --prefix acme
```

### Issue: User authentication fails

**Symptom**: Invalid credentials error

**Solution**:
```bash
# Verify user exists
python lfhelper.py user-list --schema acme-a1b2c3

# Reset password
python lfhelper.py user-reset --schema acme-a1b2c3 --username user@acme.com
```

### Issue: Database connection timeout

**Symptom**: Connection pool exhausted

**Solution**:
```bash
# Increase pool size in .env
LANGFLOW_POOL_SIZE=30
LANGFLOW_MAX_OVERFLOW=50

# Restart services
docker-compose restart langflow
```

## Future Enhancements

1. **Tenant Quotas**: Implement resource limits per tenant
2. **Billing Integration**: Track usage per schema
3. **Tenant Analytics**: Monitor activity per tenant
4. **Automated Backup**: Per-schema backup scheduling
5. **Tenant Suspension**: Deactivate without data deletion
6. **Cross-tenant Admin**: Super-admin dashboard for all tenants

## License

Same as Langflow main project (MIT).

## Support

For issues or questions:
- GitHub Issues: https://github.com/langflow-ai/langflow/issues
- Documentation: See `deploy/multi-tenant/README.md`
