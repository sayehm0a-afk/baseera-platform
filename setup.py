from setuptools import setup, find_packages

setup(
    name='basirah',
    version='0.1.0',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
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
        'alembic>=1.13.0',
        'redis>=5.0.0',
    ],
    extras_require={
        'dev': [
            'pytest',
            'pytest-mock',
        ],
    },
    python_requires='>=3.9',
)
