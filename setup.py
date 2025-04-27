from setuptools import setup, find_packages

setup(
    name="arbitrage_odds",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pyventus',
        'requests',
        'websocket-client',
        'rich',
        'rapidfuzz',
    ],
    # Test dependencies
    extras_require={
        'test': [
            'pytest',
            'pytest-cov',
        ],
    },
)