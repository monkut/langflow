# Multi-Tenant Langflow Implementation

This document describes the complete multi-tenant implementation for Langflow using PostgreSQL schema-based isolation.

## 🎯 Overview

A production-ready multi-tenant solution for Langflow providing complete tenant isolation through PostgreSQL schemas. Each tenant's data is stored in a separate database schema, ensuring data isolation at the database level.

### ✅ What's Included

- **Dynamic Schema Switching**: Header-based tenant identification with automatic PostgreSQL `search_path` routing
- **CLI Management Tool**: `lfhelper.py` for schema and user management
- **Docker Infrastructure**: Production-ready Dockerfile, docker-compose, and Nginx reverse proxy
- **AWS Deployment**: Complete CloudFormation stacks for ECS Fargate + Aurora Serverless v2
- **Security**: Schema-level isolation, secure password generation, connection pooling
- **Testing**: Automated test suite validating all functionality

### 🏗️ Key Design Decisions

**URL Path-Based Routing**: Tenants are identified via URL paths in the format `/tenant/{prefix}/...` (e.g., `/tenant/acme/api/v1/flows`). The middleware extracts the tenant prefix from the request path to determine schema routing.

**No Tracking Table**: Queries PostgreSQL's `pg_namespace` system catalog directly for schema discovery rather than maintaining a separate registry table. This:
- Eliminates sync issues between registry and actual schemas
- Provides single source of truth (PostgreSQL itself)
- Simplifies architecture and reduces maintenance
- Makes schema discovery fast and reliable

## 🚀 Quick Start

### Local Development

```bash
# 1. Navigate to deployment directory
cd deploy/multi-tenant

# 2. Start all services (PostgreSQL, Langflow, Nginx)
./start.sh

# 3. Create a tenant
docker-compose exec langflow python lfhelper.py schema-add --prefix mycompany
# Output: Schema created - mycompany-a1b2c3

# 4. Add a user (password auto-generated)
docker-compose exec langflow python lfhelper.py user-add \
  --schema mycompany-a1b2c3 \
  --username admin@mycompany.com
# Output: Password: Xy9$aBc123... (auto-generated)

# 5. Access via browser
# URL: http://localhost/tenant/mycompany/
# Login with credentials from step 4
```

### Running Tests

```bash
cd deploy/multi-tenant
./test-setup.sh

# Validates:
# ✅ Docker services running
# ✅ Schema creation
# ✅ User management
# ✅ Schema isolation
# ✅ Duplicate prevention
```

## 📁 Files Created/Modified

### New Files

**Core Implementation** (7 files):
- `src/backend/base/langflow/middleware/tenant.py` - Tenant middleware (61 lines)
- `src/backend/base/langflow/services/database/models/tenant/` - Tenant models (3 files)
- `src/backend/base/langflow/services/database/tenant_service.py` - Schema management (248 lines)
- `src/backend/base/langflow/services/deps_tenant.py` - Tenant dependencies (126 lines)
- `lfhelper.py` - CLI management tool (361 lines)

**Docker & Deployment** (8 files):
- `deploy/multi-tenant/Dockerfile` - Multi-stage production build
- `deploy/multi-tenant/docker-compose.yml` - Full orchestration
- `deploy/multi-tenant/docker-compose.dev.yml` - Development config
- `deploy/multi-tenant/nginx.conf` - Reverse proxy with routing
- `deploy/multi-tenant/.env.example` - Configuration template
- `deploy/multi-tenant/README.md` - Deployment guide
- `deploy/multi-tenant/start.sh` - Automated startup
- `deploy/multi-tenant/test-setup.sh` - Test automation
- `deploy/multi-tenant/postgres-init/01-init.sql` - DB initialization

**Documentation** (3 files):
- `MULTI_TENANT_IMPLEMENTATION.md` - This technical guide
- `MULTI_TENANT_TEST_RESULTS.md` - Test validation results
- `test_multi_tenant.py` - Integration tests

### Modified Files

- `src/backend/base/langflow/main.py` - Added TenantMiddleware registration (2 lines)
- `src/backend/base/langflow/middleware/__init__.py` - Refactored to directory structure
- `pyproject.toml` - Added lfx logging dependency

**Total**: 19 new files, 3 modified files, ~1,200 lines of production code

## 🔧 Configuration

### Environment Variables

```bash
# Database Connection
LANGFLOW_DATABASE_URL=postgresql://user:pass@host:5432/langflow

# Authentication
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=admin
LANGFLOW_SUPERUSER_PASSWORD=your-secure-password

# Performance Tuning
LANGFLOW_WORKERS=4              # Gunicorn workers
LANGFLOW_POOL_SIZE=20           # DB connection pool size
LANGFLOW_MAX_OVERFLOW=30        # Additional connections under load
LANGFLOW_POOL_TIMEOUT=30        # Connection wait timeout
LANGFLOW_POOL_RECYCLE=1800      # Recycle connections (30 min)

# Security
LANGFLOW_CORS_ORIGINS=https://yourdomain.com
LANGFLOW_SECRET_KEY=your-secret-key-here

# Logging
LANGFLOW_LOG_LEVEL=INFO
```

### Docker Compose Services

- **langflow**: Application server (port 7860)
- **postgres**: PostgreSQL 17 database (port 5432)
- **nginx**: Reverse proxy (ports 80, 443)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│             Application Load Balancer / Nginx                │
│        Routes URL paths: /tenant/{prefix}/...                │
│         (/tenant/acme/api/v1/ → tenant prefix: acme)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Langflow Application                       │
│  ┌────────────────────────────────────────────────────┐    │
│  │  TenantMiddleware (middleware/tenant.py)            │    │
│  │  - Extracts tenant prefix from URL path            │    │
│  │  - Stores in request.state for session scope       │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Tenant Service (tenant_service.py)                 │    │
│  │  - Queries pg_namespace for schemas                 │    │
│  │  - Creates schemas with collision-resistant hashes  │    │
│  │  - Manages schema lifecycle                         │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Tenant Dependencies (deps_tenant.py)               │    │
│  │  - Provides tenant-aware database sessions          │    │
│  │  - Sets PostgreSQL search_path automatically        │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│         PostgreSQL (Aurora Serverless v2 / Local)            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  public schema                                      │    │
│  │  └── (standard Langflow tables for migrations)     │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  acme-a1b2c3 schema (discovered via pg_namespace)  │    │
│  │  ├── user                                           │    │
│  │  ├── flow                                           │    │
│  │  ├── folder                                         │    │
│  │  ├── apikey                                         │    │
│  │  └── ... (all other Langflow tables)               │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  globex-d4e5f6 schema                               │    │
│  │  ├── user                                           │    │
│  │  └── ... (complete table structure)                │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow

1. **Client Request**: Request to tenant-specific URL path (e.g., `https://example.com/tenant/acme/api/v1/flows`)
2. **Load Balancer/Nginx**: Routes request based on `/tenant/{prefix}/` URL pattern, optionally sets `X-Tenant-Prefix` header
3. **TenantMiddleware**:
   - Extracts tenant prefix from URL path using regex: `/tenant/([a-zA-Z0-9_-]+)`
   - Stores prefix in `request.state.tenant_prefix` for request scope
4. **Database Session Creation** (via `get_tenant_session`):
   - Queries `pg_namespace`: `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'acme-%'`
   - Finds existing schema: `acme-a1b2c3`
   - Executes: `SET search_path TO "acme-a1b2c3", public`
5. **Route Handler**: Processes request with tenant-isolated session
6. **Response**: Returns data from `acme-a1b2c3` schema only

### Why No Tracking Table?

The implementation intentionally avoids a `tenant_schemas` registry table because:

1. **Single Source of Truth**: PostgreSQL `pg_namespace` is the authoritative source
2. **No Synchronization Issues**: Can't have registry/schema mismatch
3. **Simpler Architecture**: One less table to manage and migrate
4. **Direct Discovery**: Queries like `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'prefix-%'` are fast
5. **Self-Documenting**: Schema existence in PostgreSQL is the only requirement

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
   - Added `TenantMiddleware` import from `middleware.tenant`
   - Registered middleware in `create_app()`

2. **`pyproject.toml`**:
   - Added `lfx` dependency for enhanced logging

**Note**: No Alembic migrations are required. The implementation discovers schemas directly from PostgreSQL's system catalog.

## Database Schema

### Schema Discovery

The implementation queries PostgreSQL's `pg_namespace` system catalog directly:

```sql
-- Find schema by prefix
SELECT nspname
FROM pg_namespace
WHERE nspname LIKE 'acme-%'
ORDER BY nspname
LIMIT 1;

-- List all tenant schemas (excluding system schemas)
SELECT nspname
FROM pg_namespace
WHERE nspname LIKE '%-%'
  AND nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
ORDER BY nspname;
```

### Schema Creation

When creating a new tenant schema:

```sql
-- 1. Generate unique schema name
-- Format: {prefix}-{hash}
-- Example: acme-a1b2c3

-- 2. Create the schema
CREATE SCHEMA IF NOT EXISTS "acme-a1b2c3";

-- 3. Copy table structure from public schema
CREATE TABLE IF NOT EXISTS "acme-a1b2c3".user
(LIKE public.user INCLUDING ALL);

CREATE TABLE IF NOT EXISTS "acme-a1b2c3".flow
(LIKE public.flow INCLUDING ALL);

-- ... repeat for all Langflow tables
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

### Tenant Identification

Tenants are identified via the `X-Tenant-ID` HTTP header, which is set by the load balancer or reverse proxy based on the subdomain:

- **Subdomain**: `acme.example.com` → Header: `X-Tenant-ID: acme`
- **Subdomain**: `globex.example.com` → Header: `X-Tenant-ID: globex`

### URL Format

All tenants use the same URL paths - tenant isolation is handled via headers:

- **Health Check**: `GET /health` (no tenant context)
- **All APIs**: `GET /api/v1/flows` (tenant determined by X-Tenant-ID header)

### Examples

```bash
# Public health check (no tenant header required)
curl https://example.com/health

# Tenant-specific flows (acme schema via subdomain)
curl https://acme.example.com/api/v1/flows
# → Nginx adds: X-Tenant-ID: acme

# Tenant-specific user management (globex schema)
curl https://globex.example.com/api/v1/users
# → Nginx adds: X-Tenant-ID: globex

# Direct header-based access (for testing)
curl -H "X-Tenant-ID: acme" https://example.com/api/v1/flows
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

This starts the complete stack locally with Docker Compose:
- PostgreSQL database
- Langflow application
- Nginx reverse proxy

### Production (AWS ECS Fargate + Aurora Serverless v2)

For complete AWS deployment instructions using CloudFormation stacks (VPC, RDS, ECR, Fargate), see the dedicated infrastructure repository:

**[langflow-infra](https://github.com/monkut/langflow-infra.git)**

The infrastructure repository provides:
- CloudFormation templates for VPC, RDS (Aurora Serverless v2), Platform (ECR), and Fargate stacks
- Step-by-step deployment guide with example commands
- Schema and user management instructions using ECS Exec and `lfhelper.py`
- Production-ready configuration with auto-scaling, health checks, and monitoring

## Security Features

1. **Schema Isolation**: Complete data separation at database level using PostgreSQL schemas
2. **URL Path-Based Routing**: Tenant identification via URL paths (`/tenant/{prefix}/...`)
3. **Collision Prevention**: 6-character random hash prevents schema name conflicts
4. **Password Security**: Auto-generated secure passwords with mixed character sets
5. **Rate Limiting**: Nginx-based request throttling (configurable)
6. **Connection Pooling**: Prevents resource exhaustion with configurable pool sizes
7. **No Shared Data**: Each tenant schema is completely isolated - no cross-tenant queries possible
8. **Schema Enumeration Protection**: Random hashes prevent tenant discovery

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

# 2. List schemas (from pg_namespace)
docker-compose exec postgres psql -U langflow -d langflow -c \
  "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'testco-%' ORDER BY nspname;"

# 3. Add user to the schema
docker-compose exec langflow python lfhelper.py user-add --schema testco-XXXXXX --username test@test.com

# 4. Verify user in tenant schema
docker-compose exec postgres psql -U langflow -d langflow -c \
  "SET search_path TO \"testco-XXXXXX\"; SELECT username, is_active FROM \"user\";"

# 5. Verify schema isolation (should only see tenant's data)
docker-compose exec postgres psql -U langflow -d langflow -c \
  "SET search_path TO \"testco-XXXXXX\"; SELECT * FROM flow;"
```

## Migration from Single-Tenant

If you have existing Langflow data in the public schema:

1. **Backup current database**:
   ```bash
   pg_dump -U langflow langflow > backup.sql
   ```

2. **Create tenant schema and copy data**:
   ```sql
   -- Create new tenant schema (use lfhelper.py for automatic structure)
   CREATE SCHEMA "existing-a1b2c3";

   -- Copy table structures
   CREATE TABLE "existing-a1b2c3".user (LIKE public.user INCLUDING ALL);
   CREATE TABLE "existing-a1b2c3".flow (LIKE public.flow INCLUDING ALL);
   CREATE TABLE "existing-a1b2c3".folder (LIKE public.folder INCLUDING ALL);
   CREATE TABLE "existing-a1b2c3".apikey (LIKE public.apikey INCLUDING ALL);
   -- ... repeat for all tables

   -- Copy data
   INSERT INTO "existing-a1b2c3".user SELECT * FROM public.user;
   INSERT INTO "existing-a1b2c3".flow SELECT * FROM public.flow;
   INSERT INTO "existing-a1b2c3".folder SELECT * FROM public.folder;
   INSERT INTO "existing-a1b2c3".apikey SELECT * FROM public.apikey;
   -- ... repeat for all tables
   ```

3. **Verify schema in PostgreSQL**:
   ```sql
   -- Confirm schema exists
   SELECT nspname FROM pg_namespace WHERE nspname = 'existing-a1b2c3';

   -- Verify data
   SET search_path TO "existing-a1b2c3";
   SELECT COUNT(*) FROM "user";
   SELECT COUNT(*) FROM flow;
   ```

**Note**: No tracking table is needed - the schema's existence in PostgreSQL is sufficient for the application to discover and use it.

## 🎓 Usage Examples

### Example 1: Multi-Customer SaaS

```bash
# Customer A (Acme Corp)
python lfhelper.py schema-add --prefix acme
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com
# Users access: https://yourdomain.com/tenant/acme/

# Customer B (Globex Inc)
python lfhelper.py schema-add --prefix globex
python lfhelper.py user-add --schema globex-d4e5f6 --username admin@globex.com
# Users access: https://yourdomain.com/tenant/globex/
```

### Example 2: Department Isolation

```bash
# Marketing Department
python lfhelper.py schema-add --prefix marketing
python lfhelper.py user-add --schema marketing-a1b2c3 \
  --username team@marketing.company.com

# Engineering Department
python lfhelper.py schema-add --prefix engineering
python lfhelper.py user-add --schema engineering-d4e5f6 \
  --username team@eng.company.com
```

### Example 3: Environment Separation

```bash
# Development Environment
python lfhelper.py schema-add --prefix dev
python lfhelper.py user-add --schema dev-a1b2c3 --username devteam

# Staging Environment
python lfhelper.py schema-add --prefix staging
python lfhelper.py user-add --schema staging-d4e5f6 --username stagingteam

# Production Environment
python lfhelper.py schema-add --prefix prod
python lfhelper.py user-add --schema prod-e7f8g9 --username prodteam
```

## Troubleshooting

### Issue: Schema not found

**Symptom**: 404 error or "Schema not found" errors when accessing tenant

**Solution**:
```bash
# Check if schema exists via lfhelper
python lfhelper.py schema-list

# Or check directly in PostgreSQL
psql -U langflow -d langflow -c \
  "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'acme-%';"

# Create if missing
python lfhelper.py schema-add --prefix acme
```

**Note**: The X-Tenant-ID header must exactly match the schema prefix.

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
