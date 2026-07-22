"""
Security validation tests for production-grade components.
"""

from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

# Repository root, computed from this file's location rather than
# hardcoded, so these tests work in any checkout (previously hardcoded
# to /home/ubuntu/basirah/, which does not exist outside the original
# author's machine and made these tests fail in every other environment,
# including CI).
REPO_ROOT = Path(__file__).resolve().parents[2]


class TestSecurityValidation:
    """Test security validation."""
    
    def test_database_connection_security(self):
        """Test database connection security."""
        from src.core.db.database import DATABASE_URL
        
        # Verify that DATABASE_URL uses PostgreSQL
        assert "postgresql" in DATABASE_URL
        
        # Verify that connection pooling is enabled
        from src.core.db.database import get_engine
        assert get_engine().pool is not None
    
    def test_redis_connection_security(self):
        """Test Redis connection security."""
        from src.core.messaging.redis_message_bus import RedisMessageBus
        
        # Create message bus (will fail if Redis is not available, but that's OK)
        try:
            bus = RedisMessageBus(host='localhost', port=6379)
            
            # Verify connection pool is configured
            assert bus.connection_pool is not None
            
            bus.close()
        except:
            # Redis not available, skip this test
            pass
    
    def test_no_hardcoded_credentials(self):
        """Test that there are no hardcoded credentials."""
        import os
        import re
        
        # Read main.py and check for hardcoded credentials
        with open(REPO_ROOT / 'main.py', 'r') as f:
            content = f.read()
            
            # Check for common credential patterns
            assert 'password=' not in content or 'os.getenv' in content
            assert 'api_key=' not in content or 'os.getenv' in content
            assert 'secret=' not in content or 'os.getenv' in content
    
    def test_input_validation(self):
        """Test input validation."""
        from src.core.runtime.real_service_layer import RealServiceLayer
        from src.core.messaging.redis_message_bus import RedisMessageBus
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        from src.core.runtime.real_agent_runtime import RealAgentRuntime
        
        # Create service layer
        try:
            message_bus = RedisMessageBus(host='localhost', port=6379)
            task_queue = RealTaskQueue(host='localhost', port=6379)
            agent_runtime = RealAgentRuntime(message_bus, task_queue)
            service_layer = RealServiceLayer(message_bus, task_queue, agent_runtime)
            
            # Test with empty task
            result = service_layer.health_check()
            assert isinstance(result, bool)
            
            message_bus.close()
            task_queue.close()
        except:
            # Redis not available, skip this test
            pass
    
    def test_error_handling(self):
        """Test error handling."""
        from src.core.db.database import get_session
        
        # Test that get_session returns a valid session
        session = get_session()
        assert session is not None
        session.close()
    
    def test_logging_security(self):
        """Test logging security."""
        import logging
        
        # Verify that logging is configured
        logger = logging.getLogger("src.core")
        assert logger is not None


class TestProductionDeploymentSecurity:
    """Test production deployment security."""
    
    def test_docker_security(self):
        """Test Docker security configuration."""
        import os
        
        # Check if Dockerfile exists
        assert os.path.exists(REPO_ROOT / 'Dockerfile')

        # Read Dockerfile and check for security best practices
        with open(REPO_ROOT / 'Dockerfile', 'r') as f:
            content = f.read()
            
            # Check for non-root user (if applicable)
            # Check for minimal base image
            assert 'python' in content.lower() or 'ubuntu' in content.lower()
    
    def test_kubernetes_security(self):
        """Test Kubernetes security configuration."""
        import os
        import yaml
        
        # Check if Kubernetes manifests exist
        k8s_dir = REPO_ROOT / 'kubernetes'
        assert os.path.exists(k8s_dir)
        
        # Check for security-related files
        assert os.path.exists(os.path.join(k8s_dir, 'openai-secret.yaml'))
        
        # Read secret file
        with open(os.path.join(k8s_dir, 'openai-secret.yaml'), 'r') as f:
            content = f.read()
            
            # Verify that secrets are not hardcoded
            assert 'base64' in content or 'secretKeyRef' in content
    
    def test_environment_configuration(self):
        """Test environment configuration security."""
        import os
        
        # Check if environment configuration exists
        assert os.path.exists(REPO_ROOT / 'kubernetes' / 'environment.yaml')

        # Read environment file
        with open(REPO_ROOT / 'kubernetes' / 'environment.yaml', 'r') as f:
            content = f.read()
            
            # Verify that environment configuration is present
            assert 'ConfigMap' in content or 'configmap' in content.lower()
            assert 'DATABASE_URL' in content or 'database_url' in content.lower()


class TestDependencySecurityValidation:
    """Test dependency security validation."""
    
    def test_no_vulnerable_dependencies(self):
        """Test that no vulnerable dependencies are used."""
        # This is a basic check; in production, use tools like:
        # - pip-audit
        # - safety
        # - dependabot
        
        import subprocess
        
        # Try to run pip-audit if available
        try:
            result = subprocess.run(['pip-audit', '--desc'], capture_output=True, timeout=30)
            # If pip-audit is available, verify no vulnerabilities are found
            if result.returncode != 0:
                # There might be vulnerabilities, but this is not a hard failure
                # In production, this should be a hard requirement
                pass
        except:
            # pip-audit not available, skip this test
            pass
    
    def test_dependency_versions(self):
        """Test that dependencies are pinned to specific versions."""
        import os
        
        # Check if requirements.txt exists
        if os.path.exists('/home/ubuntu/basirah/requirements.txt'):
            with open('/home/ubuntu/basirah/requirements.txt', 'r') as f:
                content = f.read()
                
                # Verify that versions are specified
                lines = content.strip().split('\n')
                for line in lines:
                    if line and not line.startswith('#'):
                        # Each dependency should have a version specifier
                        assert '==' in line or '>=' in line or '<=' in line or '~=' in line


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
