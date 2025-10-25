# Writing Tests for New Functionality

## Context
When new features are implemented, comprehensive test coverage ensures correctness, prevents regressions, and serves as living documentation. Tests should validate behavior, not implementation details.

## Running Tests

### Prefer Makefile Commands
**Prefer using `make` commands when available** - they handle environment setup correctly:

- **Unit tests**: `make test-unit`
- **Integration tests**: `make test-integration`
- **E2E tests**: `make test-e2e` ⚠️ **ALWAYS use make for E2E** - handles test isolation
- **All tests**: `make test` (runs unit → integration → e2e sequentially)
- **With coverage**: `make test-coverage` (unit + integration only, excludes e2e)

### When to Use pytest Directly
Use `pytest` directly only for:
- **Specific test file**: `pytest tests/unit/path/to/test_file.py -v`
- **Specific test function**: `pytest tests/unit/path/to/test_file.py::test_function_name -v`
- **Quick iteration during development**

⚠️ **Never** use `pytest` directly for E2E tests - they require sequential execution for isolation.

### Why Makefile is Preferred
The Makefile handles:
- ✅ Virtual environment activation (uses `.venv/bin/python`)
- ✅ `TESTING=true` environment variable
- ✅ Test isolation (especially for E2E tests)
- ✅ Consistent test flags and configuration
- ✅ Dependency checking

### Common Issues and Solutions

**Problem**: `pytest` command not found or wrong pytest version
- **Solution**: Use `make test-unit` instead, or activate venv: `source backend/.venv/bin/activate`

## Critical Rules

### 1. Be Pragmatic About Testing
**Write tests that add real value:**
- If a test requires overly complex mocking (multiple nested mocks, complex mock chains), question if it's testing the right thing at the right level
- If a test doesn't validate meaningful behavior (e.g., just testing that a mock was called), skip it
- **Prefer testing real behavior over implementation details**
- If you find yourself fighting with mocks, consider whether an integration test would be more appropriate
- **It's better to have no test than a brittle, confusing test that breaks with every minor change**

### 2. Test Behavior, Not Implementation
**Focus on what the code does, not how it does it:**
- ✅ Good: Test that error handling returns appropriate error response
- ❌ Bad: Test that a specific internal method was called
- ✅ Good: Test that data is correctly transformed and returned
- ❌ Bad: Test the exact sequence of internal function calls

### 3. Keep Code Clean - No Historical Comments
**Don't add historical context in code comments:**
- ❌ Bad: `# New feature added in EP-0025`
- ❌ Bad: `# Testing new async implementation`
- ❌ Bad: `# Added after refactoring in Q4 2024`
- ✅ Good: Clear test names and docstrings that explain WHAT is being tested

Historical context belongs in git commits and enhancement proposals, not in code. Write tests that are self-explanatory about current behavior.

### 4. All Tests Must Pass - No Exceptions
**New tests are done ONLY when they ALL pass 100%.**

This means **ALL test types**: unit, integration, AND e2e tests must pass.

Don't say things like:
- ❌ "The main tests are passing now, I'll add edge cases later"
- ❌ "Most tests pass, just a few failing"
- ❌ "Unit tests work, I'll add integration tests later"
- ❌ "The happy path tests work, error handling can be tested later"

**All tests must pass before the feature is considered complete.** If a test is too complex or doesn't add value (see rule #1), don't write it. But don't leave failing tests.

Run all test types to verify:
```bash
make test-unit
make test-integration
make test-e2e
```

## Systematic Approach to Creating Tests

### 1. Understand the New Functionality
- Read the implementation carefully
- Identify the public API: functions, classes, endpoints exposed
- Note the expected behavior: inputs, outputs, side effects
- Review the enhancement proposal (EP) if available in `docs/enhancements/`
- Understand error handling and edge cases

### 2. Determine What Needs Testing
For each new piece of functionality, identify:
- **Happy path**: Normal, expected behavior with valid inputs
- **Edge cases**: Boundary conditions, empty inputs, maximum values
- **Error handling**: Invalid inputs, missing data, constraint violations
- **Side effects**: Database changes, external API calls, events emitted
- **Integration points**: How it works with existing components

### 3. Choose the Right Test Level

**Unit Tests** (`tests/unit/`) - Isolated component testing:
- Test individual functions, classes, and methods in isolation
- Mock external dependencies (databases, APIs, other services)
- Fast, focused, numerous
- Use when: testing business logic, utility functions, data transformations

**Integration Tests** (`tests/integration/`) - Component interaction testing:
- Test how components work together with real dependencies
- Use real database (test DB), but mock external APIs
- Slower than unit tests, fewer in number
- Use when: testing database operations, service interactions, complex workflows

**E2E Tests** (`tests/e2e/`) - Full system testing:
- Test complete user workflows through the API
- Use real database and as many real components as possible
- Slowest, fewest in number
- Use when: testing critical user journeys, API endpoints, system integration

**Rule of thumb**: Write mostly unit tests, some integration tests, few e2e tests.

### 4. Test Quality Standards

**Essential Elements:**
- ✅ **Clear, descriptive test names** that explain what's being tested
- ✅ **Single responsibility**: Each test verifies one specific behavior
- ✅ **Proper fixtures**: `isolated_test_settings`, `test_database_session`, `sample_*_alert` fixtures
- ✅ **Async consistency**: Use `async def test_*` and `await` for async code
- ✅ **Test markers**: `@pytest.mark.unit`, `.integration`, `.e2e`, `.slow`, `.external`
- ✅ **Type hints**: Include for test functions (following project standards)
- ✅ **Docstrings**: Brief description of what behavior is being validated

**Test Structure (Arrange-Act-Assert):**
```python
async def test_calculate_discount_for_premium_user_applies_twenty_percent() -> None:
    """Test that premium users receive 20% discount on purchases."""
    # Arrange - Set up test data and dependencies
    user = User(membership="premium", id=1)
    purchase_amount = Decimal("100.00")
    
    # Act - Execute the function under test
    discounted_price = await calculate_discount(user, purchase_amount)
    
    # Assert - Verify the expected outcome
    assert discounted_price == Decimal("80.00")
    assert user.discount_applied is True
```

### 5. Prefer Test Matrices for Multiple Cases

**When testing multiple similar cases, use parameterized tests instead of duplicating test code.**

Test matrices make it crystal clear what you're testing by listing all cases and expected results in an easy-to-read format:

```python
import pytest

@pytest.mark.unit
@pytest.mark.parametrize(
    "severity,expected_priority,expected_notification",
    [
        ("critical", 1, True),
        ("high", 2, True),
        ("medium", 3, False),
        ("low", 4, False),
        ("info", 5, False),
    ],
)
async def test_alert_severity_mapping(
    severity: str, expected_priority: int, expected_notification: bool
) -> None:
    """Test that alert severity correctly maps to priority and notification settings."""
    alert = Alert(severity=severity)
    
    assert alert.priority == expected_priority
    assert alert.send_notification == expected_notification


@pytest.mark.unit
@pytest.mark.parametrize(
    "input_value,expected_result,expected_error",
    [
        ("10.5", 10.5, None),
        ("0", 0.0, None),
        ("-5.2", -5.2, None),
        ("invalid", None, ValueError),
        ("", None, ValueError),
        (None, None, TypeError),
    ],
)
async def test_parse_numeric_value(
    input_value: str | None, expected_result: float | None, expected_error: type | None
) -> None:
    """Test numeric value parsing with various inputs."""
    if expected_error:
        with pytest.raises(expected_error):
            parse_numeric(input_value)
    else:
        result = parse_numeric(input_value)
        assert result == expected_result
```

**Use parameterization when:**
- Testing the same logic with different inputs
- Validating boundary conditions
- Testing error handling for various invalid inputs
- Verifying mappings or transformations

### 6. When to Ask vs. Proceed

**Proceed** when:
- New feature has clear, well-defined behavior
- Similar tests exist as examples
- All requirements are understood
- You can write meaningful, valuable tests

**Ask** when:
- Feature behavior is ambiguous or unclear
- Unsure what level of testing is appropriate (unit vs integration vs e2e)
- Not sure if specific edge cases should be tested
- Testing strategy for complex feature is unclear
- Need clarification on expected error handling

## Common Pitfalls to Avoid

- **Don't test implementation details** - test behavior, not internals
- **Don't write brittle tests** - tests should survive refactoring
- **Don't over-mock** - keep mocks simple or test at a different level
- **Don't forget `await`** when testing async functions
- **Don't leave commented code** or historical annotations in tests
- **Don't skip error handling tests** - they're as important as happy paths
- **Don't test the framework** - trust pytest, FastAPI, SQLAlchemy work correctly
- **Don't write tests that depend on execution order** - each test should be independent
- **Don't hardcode timestamps or random values** - use fixtures or freeze time
- **Don't assert on multiple unrelated things in one test** - split into separate tests

## Checklist for New Feature Testing

Before considering a feature complete, verify:

- ✅ Unit tests written for all new business logic
- ✅ Integration tests written for database operations and service interactions
- ✅ Consider writing E2E tests for new API endpoints but only if it doesn't require heavy mocking
- ✅ Happy path tested with valid inputs
- ✅ Edge cases tested (empty, null, boundary values)
- ✅ Error handling tested with invalid inputs
- ✅ All tests pass: `make test`
- ✅ Test coverage is reasonable (check with `make test-coverage`)
- ✅ Tests are clear, well-named, and documented
- ✅ No brittle mocks or implementation-detail testing
- ✅ Tests follow project conventions and standards

---

IMPORTANT!!! BE PRACTICAL! CREATE ONLY TESTS WHICH BRING REAL VALUE! DO NOT DUPLICATE TESTS!

**Now create comprehensive tests for the new functionality following the above guidelines.**


