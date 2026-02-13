# Development Guide

## Required Tools

This project requires the following tools to be installed for development:

### 1. Python 3.12+
```bash
python --version  # Should be 3.12 or higher
```

### 2. uv (Fast Python Package Manager)
```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv

# Verify installation
uv --version
```

### 3. tox-uv (Test Runner with uv Backend)
```bash
# Install tox-uv
uv tool install tox-uv

# Or using pip
pip install tox-uv

# Verify installation
tox --version
```

## Development Workflow

### First Time Setup

```bash
# 1. Clone the repository
git clone https://github.com/canonical/kube-galaxy-test.git
cd kube-galaxy-test

# 2. Install development dependencies
uv sync --all-extras --dev

# 3. Verify tools are available
tox --version
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
uv pip install -e .
```

#### Run Unit Tests
```bash
# All tests
tox -e test

# Specific test file
pytest tests/unit/test_arch.py -v

# With coverage
pytest tests/unit --cov=src/kube_galaxy --cov-report=html
```

#### Run Type Checking
```bash
# Standard mode
tox -e type

# Strict mode (more thorough)
mypy src --strict
```

#### Run Linter
```bash
# Check for issues
tox -e lint

# Auto-fix issues
ruff check src tests --fix

# Format code
ruff format src tests
```

#### Build Package
```bash
tox -e build
```

## Quick Reference for AI Agents

When working with this repository:

1. **ALWAYS install tox-uv first**: `uv tool install tox-uv`
2. **ALWAYS run checks before committing**: `tox -e type,lint,test`
3. **Use uv for package management**: It's faster than pip
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
uv tool install tox-uv
```

### "ModuleNotFoundError" when running tests
```bash
# Sync dependencies
uv sync --all-extras --dev
```

### Type checking errors
```bash
# Make sure you're using strict mode for consistency
mypy src --strict
```

### Linting errors
```bash
# Auto-fix what can be fixed
ruff check src tests --fix
ruff format src tests
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
