# Development Guide

## Required Tools

This project requires the following tools to be installed for development:

### 1. Python 3.12+
```bash
python --version  # Should be 3.12 or higher
```

### 2. uv (Fast Python Package Manager)
```bash
# Install uv if not present (optional, tox-uv includes it)
pip install uv

# Verify installation
uv --version
```

**Note**: Installing tox-uv automatically installs uv, so this step is optional.

### 3. tox-uv (Test Runner with uv Backend)
```bash
# Install tox-uv (includes uv automatically)
pip install tox-uv

# Verify installation
tox --version
```

**This is the main tool you need!** All development tasks use tox commands.

## Development Workflow

### First Time Setup

```bash
# 1. Clone the repository
git clone https://github.com/canonical/kube-galaxy-test.git
cd kube-galaxy-test

# 2. Install tox-uv (this is all you need!)
pip install tox-uv

# 3. Verify setup works
tox -e test
```

### Before Committing Changes

**ALWAYS run these checks before committing:**

```bash
# Run all checks (type, lint, test)
tox -e type,lint,test

# Or run individually:
tox -e type    # Type checking with mypy
tox -e lint    # Linting with ruff
tox -e test    # Unit tests with pytest
```

### Common Development Tasks

#### Install Package in Development Mode
```bash
# Let tox handle this
tox -e test  # Installs package automatically
```

#### Run Unit Tests
```bash
# All tests
tox -e test

# For quick iteration, you can use pytest directly
# (but tox is recommended for consistency)
pytest tests/unit/test_arch.py -v
```

#### Run Type Checking
```bash
# Type check with mypy
tox -e type
```

#### Run Linter
```bash
# Lint and format code
tox -e lint
```

#### Build Package
```bash
tox -e build
```

## Quick Reference for AI Agents

When working with this repository:

1. **ALWAYS install tox-uv first**: `pip install tox-uv`
2. **ALWAYS run checks before committing**: `tox -e type,lint,test`
3. **Use tox commands, not direct tool calls**: Prefer `tox -e lint` over `ruff check`
4. **Follow the type hints**: This project uses strict type checking

## Project Structure

```
kube-galaxy-test/
├── src/kube_galaxy/          # Main package source code
│   ├── cli.py                # CLI entry point
│   ├── cmd/                  # Command implementations
│   └── pkg/                  # Core packages
│       ├── arch/             # Architecture detection
│       ├── cluster/          # Cluster setup
│       ├── components/       # Component system
│       ├── manifest/         # Manifest models
│       └── utils/            # Utilities
├── tests/                    # Test suite
│   └── unit/                 # Unit tests
├── manifests/                # Cluster manifests
├── docs/                     # Documentation
├── pyproject.toml           # Project metadata & dependencies
├── tox.ini                  # Test configuration
└── uv.lock                  # Dependency lock file
```

## Troubleshooting

### "tox: command not found"
```bash
# Install tox-uv
pip install tox-uv
```

### "ModuleNotFoundError" when running tests
```bash
# Sync dependencies
tox -e test
# tox will handle dependencies automatically
```

### Type checking errors
```bash
# Run type checker
tox -e type
```

### Linting errors
```bash
# Run linter (auto-fixes what it can)
tox -e lint
```

## CI/CD

The project uses GitHub Actions for CI/CD:

- **Lint workflow**: Runs ruff on every push/PR
- **Test workflow**: Runs pytest on every push/PR
- **Baseline cluster workflow**: Tests cluster setups (manual/PR)

Check `.github/workflows/` for workflow definitions.

## Contributing

1. Create a feature branch
2. Make your changes
3. **Run `tox -e type,lint,test`** ✅
4. Commit with descriptive message
5. Push and create a pull request
6. Wait for CI checks to pass

## Additional Resources

- [README.md](README.md) - Project overview and usage
- [docs/](docs/) - Detailed documentation
- [Component Lifecycle Hooks](docs/component-lifecycle-hooks.md)
- [Hook System Design](docs/hook-system-design.md)
