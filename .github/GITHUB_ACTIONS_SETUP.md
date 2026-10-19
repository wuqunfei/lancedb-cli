# GitHub Actions Setup Guide

This project includes GitHub Actions workflows to automatically build and publish your package to PyPI.

## Workflows

### 1. **test-build.yml** (Automatic on push/PR)
- Runs tests on Python 3.10, 3.11, 3.12
- Tests package import and help command
- Runs on every push to `main` or `develop` branches
- Runs on all pull requests

### 2. **release.yml** (Triggered on tags)
- Builds the package distribution
- Validates with `twine`
- Publishes to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC) — no API token stored in GitHub
- Triggers automatically when you push a tag matching `v*` (e.g., `v0.1.0`)

## Setup Instructions

### Step 1: Create a PyPI Account

1. Go to https://pypi.org/
2. Click "Sign up" and create an account
3. (Optional) Register your project name to reserve it

### Step 2: Configure a Trusted Publisher on PyPI

Trusted publishing lets PyPI verify the GitHub Actions run via OIDC instead of a long-lived API
token.

1. Log in to PyPI → https://pypi.org/manage/account/publishing/
2. Add a new pending publisher (or, for an existing project, go to the project's
   **Settings → Publishing**) with:
   - **PyPI project name**: `lsql`
   - **Owner**: your GitHub username/org
   - **Repository name**: `lsql`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`

### Step 3: Create the `pypi` environment on GitHub

1. Go to your GitHub repository → **Settings → Environments**
2. Click **New environment**, name it `pypi`
3. (Optional) Add protection rules — e.g. require a reviewer before a publish run proceeds

No secrets are needed here — the `publish` job in `release.yml` requests a short-lived OIDC token
(`permissions: id-token: write`) and `pypa/gh-action-pypi-publish` exchanges it with PyPI.

### Step 4: Configure your package

Make sure these values are updated in `pyproject.toml`:
- `name` - Your package name (e.g., `lsql`)
- `version` - Current version (e.g., `0.1.0`)
- `author` - Your name
- `author_email` - Your email
- `url` - Your GitHub repository URL

## Publishing a New Release

Once everything is configured, publishing is simple:

```bash
# 1. Update __version__ in lsql/__init__.py
# 2. Commit changes
git add lsql/__init__.py
git commit -m "Bump version to 0.2.0"

# 3. Create and push a tag
git tag v0.2.0
git push origin v0.2.0
```

The GitHub Action will automatically:
- ✅ Build the package
- ✅ Validate it with twine
- ✅ Upload to PyPI via trusted publishing
- ✅ Create a GitHub Release (optional - requires permissions)

## Verification

After publishing, verify your package is on PyPI:

```bash
pip install lsql
```

Check PyPI: https://pypi.org/project/lsql/

## Troubleshooting

### "Trusted publishing exchange failure" / 403 from PyPI
- Double-check the PyPI trusted publisher's **owner**, **repository**, **workflow filename**
  (`release.yml`), and **environment name** (`pypi`) match exactly
- Make sure the `publish` job still has `environment: pypi` and `permissions: id-token: write`
- Confirm the `pypi` environment exists under repo **Settings → Environments**

### "Package already exists"
- The workflow uses `skip-existing: true`
- You can't overwrite an existing version
- Increment the version number for new releases

### Test build fails
- Check Python version compatibility in your code
- Review error logs in GitHub Actions UI
- Run tests locally: `pytest tests/`

## Advanced: Test PyPI (Staging)

Trusted publishing also works against https://test.pypi.org/ — register a separate trusted
publisher there pointing at the same repo/workflow, then add a `test-publish.yml` workflow whose
publish job targets a `testpypi` environment and passes `repository-url:
https://test.pypi.org/legacy/` to `pypa/gh-action-pypi-publish`.

## Security Notes

- No PyPI token is stored in this repository — publishing relies on short-lived OIDC credentials
  scoped to the `release.yml` workflow and the `pypi` environment
- Consider adding required reviewers to the `pypi` environment to gate publishes manually

## More Information

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [twine Documentation](https://twine.readthedocs.io/)
- [Python Packaging Guide](https://packaging.python.org/)
