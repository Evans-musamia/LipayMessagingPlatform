# Publishing `lipay-sdk` to PyPI

## 1. Accounts

| Registry | URL | Purpose |
|----------|-----|---------|
| **TestPyPI** | https://test.pypi.org | Sandbox — verify builds before production |
| **PyPI** | https://pypi.org | Production — `pip install lipay-sdk` |

Create an account on both. Enable **2FA** on PyPI production.

---

## 2. Trusted publishing (recommended — no API tokens in GitHub)

On **PyPI** → Account settings → **Publishing** → **Add a new pending publisher**:

| Field | Value |
|-------|--------|
| PyPI project name | `lipay-sdk` |
| Owner | `Evans-musamia` |
| Repository | `LipayMessagingPlatform` |
| Workflow name | `publish-pypi.yml` |
| Environment name | `pypi` |

Repeat on **TestPyPI** with environment name `testpypi`.

In GitHub → repo **Settings → Environments**, create:

- `pypi` — optional required reviewers for production uploads  
- `testpypi` — for sandbox uploads  

---

## 3. Manual upload (first-time smoke test)

```bash
cd lipay-python-sdk
python -m pip install --upgrade pip build twine
python -m build
```

**TestPyPI** (create API token at https://test.pypi.org/manage/account/):

```bash
python -m twine upload --repository testpypi dist/*
```

**Verify install:**

```bash
python -m venv /tmp/lipay-sdk-test
source /tmp/lipay-sdk-test/bin/activate   # Windows: Scripts\activate
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ lipay-sdk
python -c "from lipay_sdk import LipayCswSessionGuard; print('ok')"
```

**Production PyPI:**

```bash
python -m twine upload dist/*
```

---

## 4. Automated publishing (GitHub Actions)

### TestPyPI (manual)

Actions → **Publish to PyPI** → **Run workflow** → choose `testpypi`.

### Production PyPI (tag release)

1. Bump `version` in `pyproject.toml`.
2. Commit and push `main`.
3. Tag and push:

```bash
git tag v1.0.1
git push origin v1.0.1
```

This runs:

- `test-sdk.yml` on PRs  
- `publish-pypi.yml` — tests, build, upload to **PyPI**  
- `publish-sdk.yml` — attach wheels to **GitHub Release**  

---

## 5. Developer install after PyPI publish

```bash
pip install lipay-sdk
pip install "lipay-sdk[fastapi]"
```

`requirements.txt`:

```text
lipay-sdk==1.0.0
```

No Git URLs required.

---

## Security note

PyPI hosts **only** the public client SDK. Gateway switchboard logic, databases, and Meta credentials remain on Lipay private infrastructure.
