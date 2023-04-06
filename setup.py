#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import find_packages, setup

extras_require = {
    "test": [  # `test` GitHub Action jobs uses this
        "pytest>=6.0",  # Core testing package
        "pytest-asyncio",  # For 'ape test' integration
        "pytest-xdist",  # multi-process runner
        "pytest-cov",  # Coverage analyzer plugin
        "hypothesis>=6.2.0,<7.0",  # Strategy-based fuzzer
        "ape-cairo",  # For compiling contracts in tests
    ],
    "lint": [
        "black>=22.12",  # auto-formatter and linter
        "mypy>=0.991,<1.0",  # Static type analyzer
        "types-requests",  # Needed due to mypy typeshed
        "types-setuptools",  # Needed due to mypy typeshed
        "types-PyYAML",  # Needed due to mypy typeshed
        "flake8>=5.0.4",  # Style linter
        "isort>=5.10.1",  # Import sorting linter
        "mdformat>=0.7.16",  # Auto-formatter for markdown
        "mdformat-gfm>=0.3.5",  # Needed for formatting GitHub-flavored markdown
        "mdformat-frontmatter>=0.4.1",  # Needed for frontmatters-style headers in issue templates
        "types-pkg-resources>=0.1.3,<0.2",
    ],
    "docs": [
        # Tools for parsing markdown files in the docs
        # "myst-parser",  # TODO: Uncomment/re-pin once Sphinx 6 support is released
        "sphinx-click>=4.4.0,<5.0",  # For documenting CLI
        "Sphinx>=6.1.3,<7.0",  # Documentation generator
        "sphinx_rtd_theme>=1.2.0rc3,<2",  # Readthedocs.org theme
        "sphinxcontrib-napoleon>=0.7",  # Allow Google-style documentation
    ],
    "release": [  # `release` GitHub Action job uses this
        "setuptools",  # Installation tool
        "wheel",  # Packaging tool
        "twine",  # Package upload tool
    ],
    "dev": [
        "commitizen",  # Manage commits and publishing releases
        "pre-commit",  # Ensure that linters are run prior to committing
        "pytest-watch",  # `ptw` test watcher/runner
        "IPython",  # Console for interacting
        "ipdb",  # Debugger (Must use `export PYTHONBREAKPOINT=ipdb.set_trace`)
    ],
}

# NOTE: `pip install -e .[dev]` to install package
extras_require["dev"] = (
    extras_require["test"]
    + extras_require["lint"]
    + extras_require["release"]
    + extras_require["dev"]
)

with open("./README.md") as readme:
    long_description = readme.read()


setup(
    name="ape-starknet",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="""ape-starknet: An ape plugin for the Starknet networks""",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="ApeWorX Ltd.",
    author_email="admin@apeworx.io",
    url="https://github.com/ApeWorX/ape-starknet",
    include_package_data=True,
    install_requires=[
        "click",  # Use same version as eth-ape
        "hexbytes",  # Use same version as eth-ape
        "pydantic",  # Use same version as eth-ape
        # ** ApeWorX maintained **
        "eth-ape>=0.6.7,<0.7",
        "ethpm-types",  # Use same version as eth-ape
        # ** Starknet Ecosystem **
        "cairo-lang==0.11.0.2",
        "starknet-py>=0.15.2,<0.16",
        "starknet-devnet>=0.5.0a2,<0.6.0",
    ],
    entry_points={"ape_cli_subcommands": ["ape_starknet=ape_starknet._cli:cli"]},
    python_requires=">=3.8,<3.11",
    extras_require=extras_require,
    py_modules=["ape_starknet"],
    license="Apache-2.0",
    zip_safe=False,
    keywords="ethereum starknet",
    packages=find_packages(exclude=["tests", "tests.*"]),
    package_data={"ape_starknet": ["py.typed"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: MacOS",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
