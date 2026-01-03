from setuptools import setup, find_packages

setup(
    name="music-man",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "watchdog>=3.0.0",
        "google-generativeai>=0.3.0",
        "click>=8.0.0",
        "pyyaml>=6.0",
        "rich>=13.0.0",
        "textual>=0.50.0",
    ],
    entry_points={
        "console_scripts": [
            "mm=mm.cli:main",
        ],
    },
    python_requires=">=3.9",
    author="Jeremy Chrysler",
    description="Session continuity daemon for AI coding tools",
)
