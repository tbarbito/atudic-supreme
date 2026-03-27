"""
Pytest configuration and fixtures for AtuDIR_2 tests.
"""
import pytest
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def temp_encryption_key(tmp_path):
    """Create a temporary encryption key file for testing."""
    key_file = tmp_path / ".encryption_key"
    return str(key_file)


@pytest.fixture
def mock_db_connection(monkeypatch):
    """Mock database connection for unit tests."""
    class MockCursor:
        def execute(self, query, params=None):
            pass
        
        def fetchone(self):
            return None
        
        def fetchall(self):
            return []
        
        def close(self):
            pass
    
    class MockConnection:
        def cursor(self):
            return MockCursor()
        
        def commit(self):
            pass
        
        def close(self):
            pass
    
    def mock_get_db():
        return MockConnection()
    
    # This will be used when we extract database functions
    return mock_get_db


@pytest.fixture
def sample_token():
    """Sample token for encryption tests."""
    return "github_pat_1234567890abcdef"


@pytest.fixture
def sample_git_url():
    """Sample Git URL for validation tests."""
    return "https://github.com/user/repo.git"


@pytest.fixture
def sample_branch_name():
    """Sample branch name for validation tests."""
    return "feature/test-branch"


@pytest.fixture
def sample_path_component():
    """Sample path component for sanitization tests."""
    return "my_folder_123"


@pytest.fixture
def dangerous_path_component():
    """Dangerous path component for security tests."""
    return "../../../etc/passwd"


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter between tests."""
    from app.utils.rate_limiter import rate_limiter
    rate_limiter.requests.clear()
    yield
    rate_limiter.requests.clear()


@pytest.fixture
def flask_app():
    """Create a Flask app instance for testing."""
    from run import app
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(flask_app):
    """Create a test client for Flask app."""
    return flask_app.test_client()
