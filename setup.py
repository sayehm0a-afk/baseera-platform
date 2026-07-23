from setuptools import setup, find_packages

# The canonical import convention for this repository is the `src.` prefix
# (e.g. `from src.core.db.database import ...`), matching the application's
# entry point (main.py) and its live dependency-injection path. Packages are
# therefore installed rooted at the repository root, with `src` itself as a
# regular package (src/__init__.py), not stripped via package_dir remapping.
# See docs/architecture/m0-build-status.md for the rationale.
setup(
    name='basirah',
    version='0.1.0',
    packages=find_packages(include=['src', 'src.*']),
    install_requires=[
        'python-dotenv>=1.0.0',
        'pydantic>=2.0.0',
        'pydantic-settings>=2.0.0',
        'openai>=1.0.0',
        'langchain>=0.2.0',
        'langchain-openai>=0.1.0',
        'pandas>=2.0.0',
        'numpy>=1.26.0',
        'fastapi>=0.110.0',
        'uvicorn[standard]>=0.27.0',
        'sqlalchemy>=2.0.0',
        'asyncpg>=0.29.0',
        'psycopg2-binary>=2.9.12',
        'alembic>=1.13.0',
        'aiohttp>=3.14.2',
        'tenacity>=9.1.4',
        'redis>=8.0.1',
        'prometheus-client>=0.25.0',
    ],
    extras_require={
        'dev': [
            'pytest',
            'pytest-asyncio',
            'pytest-cov',
            'pytest-mock',
            'pytest-benchmark',
            'PyYAML',
        ],
    },
    python_requires='>=3.9',
)
