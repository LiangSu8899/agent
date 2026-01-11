#!/usr/bin/env python3
"""
Setup script for Agent OS - AI-powered debugging assistant.
"""
from setuptools import setup, find_packages
import os

# Read README for long description
readme_path = os.path.join(os.path.dirname(__file__), "README.md")
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "Agent OS - AI-powered debugging assistant"

# Read requirements
requirements = [
    "pyyaml>=6.0",
    "rich>=13.0",
    "prompt_toolkit>=3.0",
    "requests>=2.28",
    "beautifulsoup4>=4.11",
]

# Optional requirements
extras_require = {
    "dev": [
        "pytest>=7.0",
        "pytest-cov>=4.0",
        "black>=23.0",
        "isort>=5.0",
        "mypy>=1.0",
    ],
    "llm": [
        "tiktoken>=0.5",
        "llama-cpp-python>=0.2",
    ],
    "docker": [
        "docker>=6.0",
    ],
    "search": [
        "duckduckgo-search>=3.0",
    ],
}

# All extras
extras_require["all"] = list(set(
    dep for deps in extras_require.values() for dep in deps
))

setup(
    name="agent-os",
    version="0.1.0",
    author="Agent OS Team",
    author_email="team@agent-os.dev",
    description="AI-powered debugging assistant with hybrid model support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/agent-os/agent-os",
    project_urls={
        "Bug Tracker": "https://github.com/agent-os/agent-os/issues",
        "Documentation": "https://agent-os.dev/docs",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Debuggers",
        "Topic :: Software Development :: Testing",
    ],
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require=extras_require,
    entry_points={
        "console_scripts": [
            "agent-os=agent_core.cli:main",
            "aos=agent_core.cli:main",  # Short alias
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.yaml", "*.json"],
    },
    zip_safe=False,
)
