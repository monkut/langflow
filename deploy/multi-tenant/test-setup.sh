#!/bin/bash
# Test script to validate multi-tenant setup

set -e

echo "🧪 Testing Langflow Multi-Tenant Setup"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
tests_passed=0
tests_failed=0

# Helper function for test assertions
assert_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ PASS${NC}: $1"
        tests_passed=$((tests_passed + 1))
    else
        echo -e "${RED}❌ FAIL${NC}: $1"
        tests_failed=$((tests_failed + 1))
    fi
}

assert_contains() {
    local output="$1"
    local expected="$2"
    local test_name="$3"

    if echo "$output" | grep -q "$expected"; then
        echo -e "${GREEN}✅ PASS${NC}: $test_name"
        tests_passed=$((tests_passed + 1))
    else
        echo -e "${RED}❌ FAIL${NC}: $test_name"
        echo "   Expected to find: $expected"
        echo "   Got: $output"
        tests_failed=$((tests_failed + 1))
    fi
}

echo "1. Testing Docker services..."
docker-compose ps | grep -q "langflow.*Up"
assert_success "Langflow container is running"

docker-compose ps | grep -q "postgres.*Up"
assert_success "PostgreSQL container is running"

echo ""
echo "2. Testing database connectivity..."
docker-compose exec -T postgres pg_isready -U langflow > /dev/null 2>&1
assert_success "PostgreSQL is accepting connections"

echo ""
echo "3. Testing Langflow health endpoint..."
health_response=$(curl -s http://localhost:7860/health)
assert_contains "$health_response" "ok" "Health check returns OK"

echo ""
echo "4. Testing schema creation..."
schema_output=$(docker-compose exec -T langflow python lfhelper.py schema-add --prefix testco 2>&1)
assert_contains "$schema_output" "Successfully created tenant schema" "Schema creation succeeds"

# Extract schema ID from output
schema_id=$(echo "$schema_output" | grep "Schema ID:" | awk '{print $3}')
echo "   Created schema: $schema_id"

echo ""
echo "5. Testing schema listing..."
list_output=$(docker-compose exec -T langflow python lfhelper.py schema-list 2>&1)
assert_contains "$list_output" "testco" "Schema appears in list"
assert_contains "$list_output" "$schema_id" "Schema ID is correct"

echo ""
echo "6. Testing user creation..."
user_output=$(docker-compose exec -T langflow python lfhelper.py user-add --schema "$schema_id" --username test@testco.com --password TestPass123! 2>&1)
assert_contains "$user_output" "Successfully created user" "User creation succeeds"

echo ""
echo "7. Testing user listing..."
user_list=$(docker-compose exec -T langflow python lfhelper.py user-list --schema "$schema_id" 2>&1)
assert_contains "$user_list" "test@testco.com" "User appears in list"

echo ""
echo "8. Testing password reset..."
reset_output=$(docker-compose exec -T langflow python lfhelper.py user-reset --schema "$schema_id" --username test@testco.com --password NewPass123! 2>&1)
assert_contains "$reset_output" "Successfully reset password" "Password reset succeeds"

echo ""
echo "9. Testing duplicate schema prevention..."
duplicate_output=$(docker-compose exec -T langflow python lfhelper.py schema-add --prefix testco 2>&1 || true)
assert_contains "$duplicate_output" "already exists" "Duplicate schema is rejected"

echo ""
echo "10. Testing PostgreSQL schema existence..."
schema_exists=$(docker-compose exec -T postgres psql -U langflow -d langflow -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name = '$schema_id';" -t 2>&1)
assert_contains "$schema_exists" "$schema_id" "PostgreSQL schema exists in database"

echo ""
echo "11. Testing tenant_schemas table..."
tenant_table=$(docker-compose exec -T postgres psql -U langflow -d langflow -c "SELECT prefix FROM public.tenant_schemas WHERE prefix = 'testco';" -t 2>&1)
assert_contains "$tenant_table" "testco" "Tenant registry contains entry"

echo ""
echo "12. Testing schema isolation..."
user_in_schema=$(docker-compose exec -T postgres psql -U langflow -d langflow -c "SET search_path TO \"$schema_id\"; SELECT username FROM \"user\" WHERE username = 'test@testco.com';" -t 2>&1)
assert_contains "$user_in_schema" "test@testco.com" "User exists in tenant schema"

user_not_in_public=$(docker-compose exec -T postgres psql -U langflow -d langflow -c "SET search_path TO public; SELECT username FROM \"user\" WHERE username = 'test@testco.com';" -t 2>&1 || true)
if ! echo "$user_not_in_public" | grep -q "test@testco.com"; then
    echo -e "${GREEN}✅ PASS${NC}: User is isolated to tenant schema"
    tests_passed=$((tests_passed + 1))
else
    echo -e "${RED}❌ FAIL${NC}: User should not exist in public schema"
    tests_failed=$((tests_failed + 1))
fi

echo ""
echo "======================================"
echo "📊 Test Results:"
echo "   Passed: $tests_passed"
echo "   Failed: $tests_failed"
echo ""

if [ $tests_failed -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    echo ""
    echo "✅ Multi-tenant setup is working correctly"
    echo ""
    echo "You can now:"
    echo "  - Access the tenant at: http://localhost/tenant/testco/"
    echo "  - Login with: test@testco.com / NewPass123!"
    echo ""
    exit 0
else
    echo -e "${RED}❌ Some tests failed${NC}"
    echo ""
    echo "Check the logs for more details:"
    echo "  docker-compose logs langflow"
    echo "  docker-compose logs postgres"
    exit 1
fi
