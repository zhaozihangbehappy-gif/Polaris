"""Generate candidate v4 patterns into experience-packs-v4-candidates/.

Candidates are schema-valid but carry NO live evidence. They never count toward
the 1000-pattern target. The pool is a breadth scaffold; promotion to the
official pack requires an agent reproducibility run (eval/orchestrator +
evidence_writer).

Every generated record:
  source = "candidate_generated"
  agent_reproducibility.evidence = []
  needs_human_review ⊇ {"false_paths","applicability_bounds","agent_reproducibility"}
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "experience-packs-v4-candidates"

SOURCE = "candidate_generated"
HUMAN_REVIEW_FIELDS = ["false_paths", "applicability_bounds", "agent_reproducibility"]


def _record(
    ecosystem: str,
    error_class: str,
    index: int,
    description: str,
    stderr_regex: list[str],
    verify_command: str,
    fix_description: str,
    structured_hints: list[dict] | None = None,
    file_markers: list[str] | None = None,
    package_managers: list[str] | None = None,
) -> dict:
    pid = f"candidate.{ecosystem}.{error_class}.{index:03d}"
    return {
        "pattern_id": pid,
        "ecosystem": ecosystem,
        "error_class": error_class,
        "description": description,
        "source": SOURCE,
        "trigger_signals": {
            "stderr_regex": stderr_regex,
            "file_markers": file_markers or [],
            "package_managers": package_managers or [],
            "ci_env": [],
        },
        "false_paths": [],
        "shortest_verification": {
            "command": verify_command,
            "trigger_env": {},
            "expected_stderr_match": stderr_regex[0] if stderr_regex else None,
            "expected_fix_outcome": "different_error_or_success",
        },
        "fix_path": {
            "structured_hints": structured_hints or [],
            "fix_command": None,
            "fix_env": {},
            "description": fix_description,
        },
        "applicability_bounds": {"applies_when": [], "do_not_apply_when": []},
        "agent_reproducibility": {"evidence": []},
        "needs_human_review": list(HUMAN_REVIEW_FIELDS),
    }


# ---------------- Python candidates (~120) ----------------

PY_PKGS_MISSING = [
    "numpy", "pandas", "scipy", "torch", "tensorflow", "requests", "fastapi",
    "flask", "django", "pyyaml", "cryptography", "pillow", "lxml", "sqlalchemy",
    "pytest", "httpx", "aiohttp", "boto3", "redis", "psycopg2",
]

PY_VERSION_CONFLICT = [
    ("numpy", "pandas", "numpy<2 vs pandas>=2.1"),
    ("protobuf", "tensorflow", "protobuf 5.x vs tf 2.15"),
    ("cryptography", "pyopenssl", "cryptography>=42 vs pyopenssl<24"),
    ("pydantic", "fastapi", "pydantic v2 vs fastapi<0.100"),
    ("sqlalchemy", "alembic", "sqlalchemy 2.0 vs alembic<1.11"),
    ("urllib3", "requests", "urllib3 v2 vs requests<2.30"),
    ("typing-extensions", "torch", "typing_extensions too old for torch>=2"),
    ("click", "flask", "click 8.x vs flask<2.1"),
    ("importlib-metadata", "various", "importlib_metadata version mismatch"),
    ("setuptools", "pkg_resources", "setuptools>=70 dropped pkg_resources"),
]

PY_BUILD = [
    ("Missing Python.h C header", r"fatal error: Python\.h: No such file"),
    ("gcc not found for C extension", r"error: command 'gcc' failed"),
    ("clang not found on macOS build", r"unable to execute 'clang'"),
    ("Rust toolchain missing for maturin", r"Cargo, the Rust package manager, is not installed"),
    ("Cython missing at setup time", r"Cython\.Build.*ModuleNotFoundError"),
    ("Missing OpenSSL headers", r"openssl/ssl\.h.*No such file"),
    ("Missing libffi headers", r"ffi\.h.*No such file"),
    ("Missing libxml2 headers", r"libxml/xmlversion\.h.*No such file"),
    ("Missing libpq dev for psycopg2", r"pg_config executable not found"),
    ("Missing HDF5 headers for h5py", r"Could not find HDF5 installation"),
    ("Missing mysqlclient dev headers", r"mysql_config: not found"),
    ("setuptools.build_meta import failure", r"ModuleNotFoundError: No module named 'setuptools\.build_meta'"),
]

PY_CONFIG = [
    ("pytest.ini conflicts with pyproject", r"pytest\.ini.*pyproject\.toml.*both found"),
    ("conftest.py rootdir mismatch", r"rootdir.*does not contain the tests"),
    ("tox env python interpreter missing", r"ERROR: InterpreterNotFound: python\d"),
    ("pyproject build backend misspelled", r"Cannot import build backend"),
    ("setup.cfg trailing comma invalid", r"setup\.cfg.*parsing error"),
    ("mypy config section missing", r"mypy: error: Section \[mypy\] not found"),
    ("ruff config TOML key unknown", r"ruff.*Unknown config key"),
    ("black config incompatible", r"black.*Invalid option"),
    ("isort profile vs black mismatch", r"isort.*mismatch"),
    ("Pipfile lock outdated vs Pipfile", r"Pipfile\.lock .* out of date"),
]

PY_SYNTAX = [
    ("f-string nested quotes pre-3.12", r"SyntaxError.*f-string"),
    ("walrus operator in Python<3.8", r"SyntaxError.*:="),
    ("match statement in Python<3.10", r"SyntaxError.*match"),
    ("async generator in old Python", r"SyntaxError.*yield inside async function"),
    ("positional-only params pre-3.8", r"SyntaxError.*positional-only"),
]

PY_ENCODING = [
    ("UTF-8 decode error reading file", r"UnicodeDecodeError.*utf-8.*invalid start byte"),
    ("GBK decode on non-Chinese host", r"UnicodeDecodeError.*gbk"),
    ("BOM in JSON file", r"json\.decoder\.JSONDecodeError.*Expecting value"),
    ("CRLF in shell script", r"/bin/bash\^M: bad interpreter"),
    ("mixed tabs/spaces", r"TabError.*inconsistent use of tabs and spaces"),
]

PY_FILE_NOT_FOUND = [
    ("requirements.txt path resolution", r"ERROR: Could not open requirements file"),
    ("setup.py missing when sdist", r"error: can't copy 'setup\.py': doesn't exist"),
    ("VERSION file missing at install", r"FileNotFoundError.*VERSION"),
    ("README relative path in pyproject", r"readme file .* does not exist"),
    (".env not found by python-dotenv", r"dotenv.*\.env.*not found"),
    ("pytest collecting missing test dir", r"ERROR: file or directory not found: tests"),
    ("alembic migration file missing", r"Can't locate revision identified by"),
    ("Django template not found", r"TemplateDoesNotExist"),
]

PY_PERMISSION = [
    ("pip install needs sudo globally", r"PermissionError.*site-packages"),
    ("Read-only fs for cache", r"\[Errno 30\] Read-only file system"),
    ("Cannot write to /usr/local/lib", r"Permission denied.*/usr/local/lib"),
    ("Temp dir permission in container", r"PermissionError.*/tmp"),
    ("Pickle file unwritable", r"PermissionError.*\.pkl"),
    ("Pytest cache dir unwritable", r"\.pytest_cache.*Permission denied"),
    ("Django migrations dir readonly", r"migrations.*Permission denied"),
    ("Coverage data file unwritable", r"\.coverage.*Permission denied"),
]

PY_NETWORK = [
    ("PyPI SSL verify failure corp proxy", r"SSLError.*CERTIFICATE_VERIFY_FAILED"),
    ("pip install connection timeout", r"ReadTimeoutError.*pypi\.org"),
    ("DNS resolution of PyPI mirror", r"NewConnectionError.*Name or service not known"),
    ("requests proxy auth required", r"407 Proxy Authentication Required"),
    ("urllib3 retry exhausted", r"Max retries exceeded"),
    ("pip TLS handshake failure", r"TLSV1_ALERT_PROTOCOL_VERSION"),
    ("websocket connection closed", r"ConnectionClosedError"),
    ("httpx read timeout", r"httpx\.ReadTimeout"),
]

PY_RESOURCE = [
    ("OOM during numpy allocation", r"MemoryError|numpy\.core\._exceptions\._ArrayMemoryError"),
    ("Too many open files socket", r"OSError.*Too many open files"),
    ("Process fork fails in container", r"BlockingIOError.*Resource temporarily unavailable"),
    ("Recursion depth exceeded", r"RecursionError.*maximum recursion depth"),
    ("Disk full writing wheel cache", r"No space left on device"),
    ("ulimit stack size small", r"Fatal Python error.*Cannot recover from stack overflow"),
]

PY_TIMEOUT = [
    ("pytest timeout plugin fires", r"Failed: Timeout >\d+\.\d+s"),
    ("asyncio.wait_for timeout", r"asyncio\.TimeoutError"),
    ("httpx pool timeout", r"httpx\.PoolTimeout"),
    ("sqlalchemy statement_timeout", r"canceling statement due to statement timeout"),
    ("CI job overall timeout", r"Timed out after \d+ minutes"),
]

PY_PORT = [
    ("Gunicorn port already in use", r"OSError.*Address already in use.*:\d+"),
    ("Uvicorn port busy", r"uvicorn.*address already in use"),
    ("Django runserver 8000 busy", r"Error: That port is already in use"),
    ("Celery flower 5555 conflict", r"5555.*already in use"),
    ("Jupyter default port taken", r"jupyter.*port .* already in use"),
]

PY_IMPORT = [
    ("Circular import in app package", r"ImportError.*cannot import name.*partially initialized"),
    ("Relative import in __main__", r"ImportError.*attempted relative import with no known parent"),
    ("Namespace package collision", r"pkg_resources.*VersionConflict"),
    ("Stale .pyc from py2→py3", r"ImportError.*bad magic number"),
    ("Egg-info shadowing installed version", r"DistributionNotFound"),
    ("from __future__ placement error", r"SyntaxError.*from __future__ imports must occur"),
    ("__init__.py accidentally empty dir pkg", r"ModuleNotFoundError.*No module named"),
    ("importlib.resources API change", r"AttributeError.*open_text"),
    ("C extension ABI mismatch", r"ImportError.*undefined symbol"),
    ("numpy .so ABI stale", r"numpy\.core\.multiarray failed to import"),
]

PY_ENV = [
    ("venv activate script missing", r"activate: No such file"),
    ("PYTHONPATH shadowing stdlib", r"ImportError.*No module named '_bootlocale'"),
    ("virtualenv python symlink broken", r"bad interpreter.*No such file"),
    ("PATH missing pipx shims", r"pipx: command not found"),
    ("pyenv shims not in PATH", r"pyenv: command not found|python: command not found"),
    ("poetry env not linked", r"poetry.*No virtualenv created"),
    ("conda env activation hook missing", r"CondaError.*activate"),
    ("uv cache dir env var invalid", r"uv.*cache directory"),
]


def build_python() -> list[dict]:
    out: list[dict] = []
    for i, pkg in enumerate(PY_PKGS_MISSING):
        out.append(_record(
            "python", "missing_dependency", i,
            description=f"ModuleNotFoundError for '{pkg}' — install via pip",
            stderr_regex=[rf"ModuleNotFoundError: No module named '{pkg}'",
                          rf"ImportError.*No module named {pkg}"],
            verify_command=f"python3 -c \"import {pkg}\" 2>&1",
            fix_description=f"pip install {pkg} (check pyproject/requirements for version pin)",
            structured_hints=[{"kind": "install_package", "manager": "pip", "name": pkg}],
            package_managers=["pip"],
        ))
    for i, (a, b, why) in enumerate(PY_VERSION_CONFLICT):
        out.append(_record(
            "python", "version_conflict", i,
            description=f"Version incompatibility between {a} and {b}: {why}",
            stderr_regex=[rf"{a}.*(incompatible|requires|conflict).*{b}",
                          rf"ERROR: Cannot install.*{a}.*{b}"],
            verify_command=f"pip check 2>&1 | grep -E '{a}|{b}' || true",
            fix_description=f"Pin both {a} and {b} to compatible versions; see: {why}",
            structured_hints=[{"kind": "pin_versions", "packages": [a, b]}],
            package_managers=["pip"],
        ))
    for i, (desc, rx) in enumerate(PY_BUILD):
        out.append(_record(
            "python", "build_error", i,
            description=desc,
            stderr_regex=[rx],
            verify_command="python3 -m pip install --no-binary :all: dummy-pkg 2>&1 || true",
            fix_description=f"Install system build deps; root cause: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_CONFIG):
        out.append(_record(
            "python", "config_error", i,
            description=desc, stderr_regex=[rx],
            verify_command="pytest --collect-only 2>&1 || true",
            fix_description=f"Resolve config conflict: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_SYNTAX):
        out.append(_record(
            "python", "syntax_error", i,
            description=desc, stderr_regex=[rx],
            verify_command="python3 -c 'import sys; print(sys.version)' 2>&1",
            fix_description=f"Upgrade Python or rewrite syntax: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_ENCODING):
        out.append(_record(
            "python", "encoding_error", i,
            description=desc, stderr_regex=[rx],
            verify_command="file --mime-encoding 2>&1 || true",
            fix_description=f"Fix encoding: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_FILE_NOT_FOUND):
        out.append(_record(
            "python", "file_not_found", i,
            description=desc, stderr_regex=[rx],
            verify_command="ls -la 2>&1",
            fix_description=f"Resolve path: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_PERMISSION):
        out.append(_record(
            "python", "permission_denial", i,
            description=desc, stderr_regex=[rx],
            verify_command="id && umask 2>&1",
            fix_description=f"Adjust permissions or use venv: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_NETWORK):
        out.append(_record(
            "python", "network_error", i,
            description=desc, stderr_regex=[rx],
            verify_command="python3 -c 'import urllib.request; urllib.request.urlopen(\"https://pypi.org\", timeout=3)' 2>&1 || true",
            fix_description=f"Network/TLS: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_RESOURCE):
        out.append(_record(
            "python", "resource_exhaustion", i,
            description=desc, stderr_regex=[rx],
            verify_command="ulimit -a 2>&1",
            fix_description=f"Adjust resource limits: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_TIMEOUT):
        out.append(_record(
            "python", "timeout", i,
            description=desc, stderr_regex=[rx],
            verify_command="true",
            fix_description=f"Increase timeout or optimize: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_PORT):
        out.append(_record(
            "python", "port_conflict", i,
            description=desc, stderr_regex=[rx],
            verify_command="ss -ltn 2>&1 || netstat -ltn 2>&1 || true",
            fix_description=f"Free port or change binding: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_IMPORT):
        out.append(_record(
            "python", "import_error", i,
            description=desc, stderr_regex=[rx],
            verify_command="python3 -c 'import sys; print(sys.path)' 2>&1",
            fix_description=f"Resolve import: {desc}",
        ))
    for i, (desc, rx) in enumerate(PY_ENV):
        out.append(_record(
            "python", "env_error", i,
            description=desc, stderr_regex=[rx],
            verify_command="env | grep -E 'PYTHON|PATH|VIRTUAL' 2>&1",
            fix_description=f"Fix environment: {desc}",
        ))
    return out


# ---------------- Node candidates (~120) ----------------

NODE_PKGS = [
    "react", "vue", "next", "webpack", "typescript", "eslint", "prettier",
    "axios", "lodash", "express", "jest", "vitest", "tsx", "rollup",
    "esbuild", "turbo", "nx", "storybook", "playwright", "cypress",
]

NODE_VERSION_CONFLICT = [
    ("react", "react-dom", "react 18 vs react-dom 17"),
    ("typescript", "@types/node", "ts 5.x vs @types/node<20"),
    ("webpack", "webpack-cli", "webpack 5 vs webpack-cli 3"),
    ("eslint", "typescript-eslint", "eslint 9 vs typescript-eslint 6"),
    ("next", "react", "next 14 requires react 18"),
    ("vitest", "vite", "vitest 1.x vs vite 4"),
    ("vue", "@vue/compiler-sfc", "vue 3 vs compiler-sfc 2"),
    ("jest", "ts-jest", "jest 29 vs ts-jest 27"),
    ("storybook", "@storybook/react", "sb 7 vs @sb/react 6"),
    ("prisma", "@prisma/client", "prisma 5 vs client 4"),
    ("commander", "various", "commander 12 vs consumers"),
    ("chalk", "various", "chalk v5 ESM-only"),
]

NODE_BUILD = [
    ("TypeScript TS2307 cannot find module", r"TS2307.*Cannot find module"),
    ("TS2304 cannot find name", r"TS2304.*Cannot find name"),
    ("webpack module parse failed", r"Module parse failed.*Unexpected token"),
    ("babel preset not found", r"Cannot find module 'babel-preset"),
    ("swc plugin not loaded", r"swc.*plugin.*not found"),
    ("esbuild service crashed", r"esbuild.*Service was stopped"),
    ("vite rollup out of memory", r"JavaScript heap out of memory"),
    ("tsconfig paths alias unresolved", r"Cannot find module.*paths"),
    ("next.config mjs syntax error", r"Error loading config.*next\.config"),
    ("postcss plugin missing", r"Cannot find module.*postcss"),
    ("node-gyp rebuild fails", r"gyp ERR!"),
    ("python not found for node-gyp", r"gyp ERR!.*Python"),
]

NODE_CONFIG = [
    ("package.json type=module breaks require", r"require\(\) of ES Module"),
    ("tsconfig moduleResolution mismatch", r"TS1084|moduleResolution"),
    ("jest.config.js vs .ts conflict", r"jest.*config.*Could not load"),
    ("eslintrc vs eslint.config.js both present", r"eslint.*Both .*config.*detected"),
    (".npmrc auth token wrong for private", r"npm ERR!.*401 Unauthorized"),
    ("nx.json target missing", r"Cannot find configuration for task"),
    ("turbo.json pipeline missing task", r"turbo.*no task named"),
    ("next.config output mode mismatch", r"output.*standalone.*not supported"),
    ("yarn workspaces hoist conflict", r"yarn.*workspace.*conflict"),
    ("package.json exports field gate", r"Package subpath.*not defined by \"exports\""),
]

NODE_FNF = [
    ("tsconfig.json not found", r"error TS5057.*Cannot find a tsconfig\.json"),
    ("missing package.json in workspace", r"ENOENT.*package\.json"),
    ("lockfile not found in CI", r"ERR_PNPM_NO_LOCKFILE|npm.*No lockfile found"),
    ("entry file path in package.json wrong", r"Cannot find module.*main"),
    ("node-modules/.bin missing", r"ENOENT.*node_modules/\.bin"),
    ("build output dir missing pre-deploy", r"ENOENT.*dist|ENOENT.*build"),
]

NODE_PERM = [
    ("EACCES on global npm install", r"EACCES.*permission denied.*npm"),
    ("pnpm store dir unwritable", r"EACCES.*\.pnpm-store"),
    ("EPERM on Windows rename during install", r"EPERM.*rename"),
    ("eslint cache dir read-only", r"EACCES.*\.eslintcache"),
    ("tsbuildinfo readonly", r"EACCES.*tsbuildinfo"),
    ("ci cache write denied", r"EACCES.*\.cache"),
]

NODE_NETWORK = [
    ("npm registry 503", r"npm ERR!.*503 Service Unavailable"),
    ("pnpm registry certificate error", r"SELF_SIGNED_CERT_IN_CHAIN"),
    ("yarn network timeout", r"Request failed \"ETIMEDOUT\""),
    ("corepack download 403", r"corepack.*403 Forbidden"),
    ("github packages auth 401", r"npm ERR!.*401.*github"),
    ("npm proxy env ignored", r"npm ERR!.*ECONNREFUSED"),
    ("DNS lookup failed in CI", r"getaddrinfo ENOTFOUND"),
    ("TLS version too old for registry", r"TLSV1_ALERT_PROTOCOL_VERSION"),
    ("ETIMEDOUT during fetch-metadata", r"ETIMEDOUT.*registry"),
    ("ECONNRESET during tarball fetch", r"ECONNRESET.*\.tgz"),
]

NODE_RESOURCE = [
    ("Node heap OOM during build", r"FATAL ERROR.*Allocation failed.*heap out of memory"),
    ("EMFILE too many open files", r"EMFILE.*too many open files"),
    ("ulimit small in Docker build", r"resource temporarily unavailable"),
    ("pnpm install disk full", r"ENOSPC.*no space left"),
    ("webpack cache corruption", r"Pack has been invalidated"),
    ("swc workers stack overflow", r"Maximum call stack size exceeded"),
]

NODE_TIMEOUT = [
    ("jest test timeout 5s default", r"Exceeded timeout of \d+ ms"),
    ("playwright test timeout", r"Timeout of \d+ms exceeded"),
    ("vitest hook timeout", r"Hook timed out"),
    ("cypress command timeout", r"Timed out retrying"),
    ("next build static export timeout", r"next.*timeout.*static export"),
    ("esbuild watch stuck", r"esbuild.*watch.*not responding"),
]

NODE_PORT = [
    ("Next dev 3000 in use", r"Port 3000 is in use"),
    ("Vite 5173 conflict", r"Port 5173 is in use"),
    ("Storybook 6006 conflict", r"Port 6006 is already in use"),
    ("Express listen EADDRINUSE", r"EADDRINUSE.*listen"),
    ("HMR websocket port taken", r"HMR.*port"),
    ("Playwright trace viewer port taken", r"playwright.*port"),
]

NODE_LOCK = [
    ("pnpm-lock outdated ERR_PNPM_OUTDATED_LOCKFILE", r"ERR_PNPM_OUTDATED_LOCKFILE"),
    ("npm ci lockfile mismatch", r"npm ERR!.*can only install packages when your package\.json"),
    ("yarn.lock integrity check failed", r"yarn.*Integrity check failed"),
    ("mixed npm+pnpm lockfiles", r"both package-lock\.json and pnpm-lock\.yaml"),
    ("lockfile schema version bump", r"ERR_PNPM_LOCKFILE_BREAKING_CHANGE"),
    ("corepack signature mismatch", r"corepack.*signature"),
    ("package-lock v3 vs v2", r"npm ERR!.*lockfileVersion"),
    ("yarn berry vs classic lock format", r"yarn\.lock.*header"),
    ("lockfile drift after manual edit package.json", r"lockfile.*out of sync"),
    ("missing optional dep causes lock mismatch", r"missing optional dependency"),
]

NODE_MONOREPO = [
    ("pnpm workspace pkg not linked", r"ERR_PNPM_WORKSPACE_PKG_NOT_FOUND"),
    ("turbo cache miss due to inputs config", r"turbo.*cache miss"),
    ("nx affected base sha missing in CI", r"NX.*--base=.*does not exist"),
    ("workspace protocol version spec", r"workspace:.*not a valid semver"),
    ("pnpm publish workspace dep not bumped", r"workspace package was not published"),
    ("lerna changed detected none", r"lerna notice.*No changed packages"),
    ("rush install rush.json version mismatch", r"rush.*rushVersion"),
    ("yarn workspaces focus unsupported", r"yarn workspaces focus.*not supported"),
]

NODE_ESM_CJS = [
    ("ESM require() of .mjs", r"Must use import to load ES Module"),
    ("CJS dynamic require in ESM", r"require is not defined in ES module scope"),
    ("top-level await in CJS", r"SyntaxError.*await is only valid"),
    ("default export interop missing", r"Cannot use import statement outside a module"),
    ("__dirname undefined in ESM", r"ReferenceError.*__dirname is not defined"),
    ("exports map conditional mismatch", r"ERR_PACKAGE_PATH_NOT_EXPORTED"),
    ("ts-node ESM loader required", r"ts-node.*ESM.*loader"),
    ("tsx vs ts-node behavior diff", r"tsx.*Cannot find package"),
]


def build_node() -> list[dict]:
    out: list[dict] = []
    for i, pkg in enumerate(NODE_PKGS):
        out.append(_record(
            "node", "missing_dependency", i,
            description=f"Cannot find module '{pkg}' — install via npm/pnpm/yarn",
            stderr_regex=[rf"Cannot find module '{pkg}'",
                          rf"Error: Cannot find package '{pkg}'"],
            verify_command=f"node -e \"require('{pkg}')\" 2>&1 || true",
            fix_description=f"npm/pnpm/yarn install {pkg}",
            structured_hints=[{"kind": "install_package", "manager": "npm", "name": pkg}],
            package_managers=["npm", "pnpm", "yarn"],
        ))
    for i, (a, b, why) in enumerate(NODE_VERSION_CONFLICT):
        out.append(_record(
            "node", "version_conflict", i,
            description=f"{a} vs {b}: {why}",
            stderr_regex=[rf"{a}.*peer.*{b}", rf"ERESOLVE.*{a}.*{b}"],
            verify_command="npm ls 2>&1 | head -30",
            fix_description=f"Align versions: {why}",
            package_managers=["npm", "pnpm", "yarn"],
        ))
    for i, (desc, rx) in enumerate(NODE_BUILD):
        out.append(_record("node", "build_error", i, desc, [rx],
                           "tsc --noEmit 2>&1 || true", f"Build: {desc}"))
    for i, (desc, rx) in enumerate(NODE_CONFIG):
        out.append(_record("node", "config_error", i, desc, [rx],
                           "cat package.json 2>&1 | head -20", f"Config: {desc}"))
    for i, (desc, rx) in enumerate(NODE_FNF):
        out.append(_record("node", "file_not_found", i, desc, [rx],
                           "ls -la 2>&1", f"Path: {desc}"))
    for i, (desc, rx) in enumerate(NODE_PERM):
        out.append(_record("node", "permission_denial", i, desc, [rx],
                           "id && umask 2>&1", f"Permissions: {desc}"))
    for i, (desc, rx) in enumerate(NODE_NETWORK):
        out.append(_record("node", "network_error", i, desc, [rx],
                           "npm ping 2>&1 || true", f"Network: {desc}"))
    for i, (desc, rx) in enumerate(NODE_RESOURCE):
        out.append(_record("node", "resource_exhaustion", i, desc, [rx],
                           "node -e 'console.log(process.memoryUsage())' 2>&1",
                           f"Resource: {desc}"))
    for i, (desc, rx) in enumerate(NODE_TIMEOUT):
        out.append(_record("node", "timeout", i, desc, [rx],
                           "true", f"Timeout: {desc}"))
    for i, (desc, rx) in enumerate(NODE_PORT):
        out.append(_record("node", "port_conflict", i, desc, [rx],
                           "ss -ltn 2>&1 || netstat -ltn 2>&1 || true",
                           f"Port: {desc}"))
    for i, (desc, rx) in enumerate(NODE_LOCK):
        out.append(_record("node", "lockfile_error", i, desc, [rx],
                           "ls *lock* 2>&1 || true", f"Lockfile: {desc}"))
    for i, (desc, rx) in enumerate(NODE_MONOREPO):
        out.append(_record("node", "monorepo_error", i, desc, [rx],
                           "cat pnpm-workspace.yaml 2>&1 || cat turbo.json 2>&1 || true",
                           f"Monorepo: {desc}"))
    for i, (desc, rx) in enumerate(NODE_ESM_CJS):
        out.append(_record("node", "esm_cjs_error", i, desc, [rx],
                           "node --version 2>&1", f"ESM/CJS: {desc}"))
    return out


# ---------------- Docker candidates (~100) ----------------

DOCKER_BUILD = [
    ("COPY source path not in context", r"COPY failed.*no such file or directory"),
    ("ADD with URL failed HTTPS", r"ADD failed.*https"),
    ("RUN apt-get update 404 suite", r"E: Failed to fetch .* 404 Not Found"),
    ("RUN apk add package not found", r"ERROR: unable to select packages"),
    ("Dockerfile syntax frontend parse error", r"dockerfile parse error"),
    ("heredoc syntax requires buildkit", r"--mount.*requires BuildKit"),
    ("FROM image manifest unknown", r"manifest for .* not found"),
    ("buildx platform not supported", r"no match for platform"),
    ("ARG used before FROM", r"ARG requires exactly one argument"),
    ("multi-stage COPY --from unknown", r"COPY failed.*stage"),
    ("WORKDIR absolute path required", r"WORKDIR.*must be absolute"),
    ("SHELL command parse error", r"SHELL.*invalid"),
    ("USER numeric id not in passwd", r"unable to find user.*no matching entries"),
    ("ENV with = and space confusion", r"environment variable.*empty"),
    ("HEALTHCHECK missing CMD", r"HEALTHCHECK requires the CMD"),
    ("ENTRYPOINT json array syntax", r"entrypoint.*JSON"),
    ("Dockerfile not found in context", r"unable to prepare context.*Dockerfile"),
    ("buildkit inline cache missing", r"inline cache.*failed"),
]

DOCKER_IMG = [
    ("pull access denied private registry", r"pull access denied.*repository does not exist"),
    ("image not found in local cache for --pull=never", r"Error response from daemon.*No such image"),
    ("Docker Hub rate limit toomanyrequests", r"toomanyrequests"),
    ("tag mutable vs digest immutable", r"no such manifest.*digest"),
    ("platform linux/arm64 unavailable", r"no matching manifest for linux/arm64"),
    ("registry auth token expired", r"unauthorized.*authentication"),
    ("insecure registry not configured", r"http: server gave HTTP response to HTTPS"),
    ("registry mirror misconfigured", r"registry mirror.*failed"),
]

DOCKER_NET = [
    ("container cannot reach host via 127.0.0.1", r"connect.*127\.0\.0\.1.*refused"),
    ("DNS unresolvable inside container", r"Temporary failure in name resolution"),
    ("iptables missing in minimal OS", r"iptables.*command not found"),
    ("network name conflict", r"network.*has active endpoints"),
    ("bridge network MTU mismatch", r"MTU.*mismatch"),
    ("overlay network swarm not active", r"This node is not a swarm manager"),
    ("host.docker.internal linux fallback", r"host\.docker\.internal.*not found"),
    ("port mapping conflict with existing", r"port is already allocated"),
    ("dockerd socket permission denied", r"permission denied.*docker\.sock"),
    ("container network removed while attached", r"error while removing network.*endpoints"),
]

DOCKER_PERM = [
    ("chown inside container UID conflict", r"chown.*invalid user"),
    ("/var/run/docker.sock permission", r"permission denied.*\/var\/run\/docker\.sock"),
    ("COPY preserves wrong owner in slim", r"chown: invalid group"),
    ("bind mount selinux context", r"selinux.*permission denied"),
    ("userns-remap missing subuid entry", r"subuid.*missing"),
    ("read-only rootfs blocks /tmp writes", r"read-only file system.*\/tmp"),
    ("cgroup v2 docker older incompat", r"OCI runtime.*cgroup"),
    ("capability drop CAP_NET_ADMIN needed", r"permission denied.*CAP_NET_ADMIN"),
    ("container user override without uid", r"unable to find user"),
    ("volume mount chown loop in start", r"chown: changing ownership"),
]

DOCKER_RESOURCE = [
    ("build disk full in /var/lib/docker", r"no space left on device.*\/var\/lib\/docker"),
    ("buildkit cache full", r"buildkit.*no space"),
    ("container OOM killed", r"OOMKilled.*true"),
    ("ulimit nofile too low", r"too many open files.*docker"),
    ("memory limit too small for build", r"runtime: out of memory"),
    ("inode exhaustion overlay2", r"no space left.*inode"),
    ("CPU throttling build slowdown", r"cpu.*throttled"),
    ("pid limit hit cgroup", r"pids-limit.*exceeded"),
]

DOCKER_AUTH = [
    ("docker login saved plain text warning", r"credentials are stored unencrypted"),
    ("ECR token expired mid-build", r"no basic auth credentials"),
    ("GCR keyless auth missing workload identity", r"gcr\.io.*unauthorized"),
    ("ACR AAD auth refresh token bad", r"azurecr.*401"),
    ("ghcr.io PAT needs read:packages scope", r"ghcr\.io.*401|ghcr\.io.*unauthorized"),
    ("docker-config.json corrupted", r"error getting credentials.*error parsing"),
    ("credHelpers binary missing", r"credential-helper.*not found"),
    ("registry proxy cache auth pass-through", r"registry.*proxy.*401"),
]

DOCKER_CONFIG = [
    ("daemon.json invalid JSON", r"unable to configure the Docker daemon"),
    ("buildx builder inactive", r"builder.*is not running"),
    ("compose v1 vs v2 schema drift", r"Compose file.*is invalid|version is obsolete"),
    ("compose profile not enabled", r"service.*no matching profile"),
    ("compose env_file not found", r"env file .* not found"),
    ("compose depends_on healthcheck missing", r"service.*depends on.*no healthcheck"),
    ("swarm mode not enabled for stack deploy", r"This node is not part of a swarm"),
    ("seccomp profile path invalid", r"seccomp.*failed to load profile"),
    ("apparmor profile not loaded", r"apparmor.*profile.*not loaded"),
    ("container_name conflict compose", r"container name.*already in use"),
]

DOCKER_PORT = [
    ("compose port clash with host nginx", r"bind.*port is already allocated"),
    ("published port range exhausted", r"port is already allocated.*5432"),
    ("IPv6 port binding not enabled", r"::.*not available"),
    ("random port range conflict", r"failed.*random port"),
    ("docker-proxy binary missing", r"docker-proxy.*not found"),
    ("host network mode port ignored", r"host.*network mode.*ports ignored"),
]

DOCKER_VERCONF = [
    ("docker engine too old for buildx", r"docker buildx.*requires"),
    ("compose file version too high for CLI", r"Version .* in .* is invalid"),
    ("runc version mismatch after upgrade", r"runc.*version"),
    ("containerd image store incompat", r"containerd.*image store"),
]

DOCKER_LAYER = [
    ("cache bust by package version regex", r"failed to compute cache key"),
    ("COPY . invalidates on VCS metadata", r"COPY.*cache.*miss"),
    ("timestamp-based cache bust", r"mtime.*cache"),
    (".gitignore not .dockerignore confusion", r".dockerignore.*not found"),
    ("buildx cache-to inline failure", r"cache-to.*inline.*failed"),
    ("registry cache-from missing creds", r"cache-from.*unauthorized"),
    ("buildkit gc cleared mid-build", r"buildkit.*gc.*cleared"),
    ("stage rename breaks --from", r"no stage named"),
]

DOCKER_IGNORE = [
    (".dockerignore excludes required file", r"executor failed.*COPY.*excluded"),
    (".dockerignore negation syntax wrong", r"dockerignore.*pattern"),
    ("workspace marker dir excluded", r"\.git.*excluded|\.codex.*excluded"),
    (".dockerignore vs multi-stage staged copy", r"COPY --from.*excluded"),
    (".dockerignore symlink traversal", r"symlink.*excluded"),
    (".dockerignore case-sensitivity surprise", r"Dockerfile.*filename case"),
]

DOCKER_MULTISTAGE = [
    ("stage target name typo in --target", r"target stage .* could not be found"),
    ("BUILDPLATFORM vs TARGETPLATFORM mix-up", r"TARGETPLATFORM.*not set"),
    ("ONBUILD instruction in multi-stage", r"ONBUILD.*trigger"),
    ("heredoc not propagated across stages", r"heredoc.*stage"),
]


def build_docker() -> list[dict]:
    out: list[dict] = []
    sections = [
        ("build_error", DOCKER_BUILD),
        ("image_not_found", DOCKER_IMG),
        ("network_error", DOCKER_NET),
        ("permission_denial", DOCKER_PERM),
        ("resource_exhaustion", DOCKER_RESOURCE),
        ("auth_error", DOCKER_AUTH),
        ("config_error", DOCKER_CONFIG),
        ("port_conflict", DOCKER_PORT),
        ("version_conflict", DOCKER_VERCONF),
        ("layer_cache", DOCKER_LAYER),
        ("dockerignore", DOCKER_IGNORE),
        ("multistage", DOCKER_MULTISTAGE),
    ]
    for ec, entries in sections:
        for i, (desc, rx) in enumerate(entries):
            out.append(_record(
                "docker", ec, i, desc, [rx],
                "docker info 2>&1 | head -5", f"Docker {ec}: {desc}",
            ))
    return out


# ---------------- Go candidates (~60) ----------------

GO_MISSING = [
    "github.com/stretchr/testify", "github.com/pkg/errors", "go.uber.org/zap",
    "github.com/spf13/cobra", "github.com/gin-gonic/gin", "gorm.io/gorm",
    "google.golang.org/grpc", "github.com/prometheus/client_golang",
    "golang.org/x/sync/errgroup", "k8s.io/client-go",
]

GO_BUILD = [
    ("undefined symbol in generated code", r"undefined: .*\\.(pb|gen)\\.go"),
    ("cgo requires gcc", r"exec: \"gcc\": executable file not found"),
    ("build constraints exclude all files", r"build constraints exclude all Go files"),
    ("import cycle not allowed", r"import cycle not allowed"),
    ("syntax error near unexpected token", r"syntax error: unexpected"),
    ("undefined type after go.mod replace", r"undefined: .*replace"),
    ("linker: undefined reference", r"undefined reference to"),
    ("tag build constraint mismatch", r"cannot find package.*build tag"),
    ("go:generate not run", r"undefined.*generated"),
    ("tests build but main does not", r"main\.go.*does not compile"),
]

GO_VERCONF = [
    ("go.sum mismatch against go.mod", r"checksum mismatch"),
    ("go toolchain version too old", r"requires go \d+\.\d+"),
    ("go directive vs go.mod module version", r"go: module.*requires"),
    ("replace directive path does not exist", r"replace.*directory does not exist"),
    ("ambiguous import after major bump v2", r"ambiguous import"),
    ("require vs replace mismatch", r"go: inconsistent vendoring"),
]

GO_CONFIG = [
    ("GOFLAGS overrides breaks modules", r"GOFLAGS.*-mod=vendor.*conflict"),
    ("GOPROXY misconfigured private", r"module lookup disabled by GOPROXY=off"),
    ("GOPRIVATE not set for private repo", r"reading.*git.*HTTPS.*401"),
    ("go env GOROOT wrong after brew upgrade", r"GOROOT.*does not exist"),
    ("go workspace go.work not synced", r"go: go\.work.*inconsistent"),
    ("CGO_ENABLED mismatch in cross-compile", r"CGO_ENABLED=0.*cannot use cgo"),
]

GO_MODULE = [
    ("go mod tidy removes needed test dep", r"go\.mod.*no required module provides package"),
    ("sum mismatch after manual go.sum edit", r"SECURITY ERROR.*go\.sum"),
    ("pseudo-version from commit not allowed", r"invalid pseudo-version"),
    ("module path capitalisation conflict", r"module declares its path as.*but was required"),
    ("replace with relative path breaks ci", r"replace.*local path"),
    ("main module contains vendor dir", r"vendor.*inconsistent"),
    ("go.mod parse error bad directive", r"go\.mod.*syntax error"),
    ("minimum go version unmet", r"go: module requires Go \d"),
    ("unknown directive toolchain", r"unknown directive: toolchain"),
    ("GOPROXY 410 gone permanent", r"410 Gone"),
]

GO_VENDOR = [
    ("vendor/modules.txt out of sync", r"inconsistent vendoring"),
    ("vendored package missing LICENSE", r"vendor.*LICENSE.*missing"),
    ("vendor and module version drift", r"vendor.*does not match go\.mod"),
    ("go build -mod=vendor with no vendor dir", r"no vendor directory"),
    ("vendor exclusions via go mod why", r"go mod why.*not imported"),
    ("vendor shipping generated code stale", r"vendor.*out of date"),
]

GO_TEST = [
    ("test fails only under -race", r"DATA RACE"),
    ("TestMain conflicts with package tests", r"TestMain.*already declared"),
    ("goroutine leak in test", r"goroutines running after Test"),
    ("testing.Short skip not respected", r"testing\.Short"),
    ("test binary requires network but sandboxed", r"dial tcp.*timeout"),
    ("parallel tests share state", r"t\.Parallel.*shared state"),
]

GO_CGO = [
    ("cgo on Alpine musl vs glibc", r"undefined reference.*__explicit_bzero_chk"),
    ("pkg-config missing dev package", r"pkg-config: exec.*not found"),
    ("cgo LDFLAGS malformed", r"cgo.*LDFLAGS.*invalid"),
    ("cross-compile cgo CC not set", r"CC.*not found.*cross"),
    ("dlopen shared lib path missing", r"libc\\.so.*cannot open"),
    ("cgo callback ABI mismatch", r"cgo argument has Go pointer"),
]


def build_go() -> list[dict]:
    out: list[dict] = []
    for i, pkg in enumerate(GO_MISSING):
        out.append(_record(
            "go", "missing_dependency", i,
            description=f"Go module '{pkg}' not found; run go get",
            stderr_regex=[rf"no required module provides package {pkg}",
                          rf"cannot find package \"{pkg}\""],
            verify_command=f"go list {pkg} 2>&1 || true",
            fix_description=f"go get {pkg}",
            structured_hints=[{"kind": "install_package", "manager": "go", "name": pkg}],
            package_managers=["go"],
        ))
    sections = [
        ("build_error", GO_BUILD),
        ("version_conflict", GO_VERCONF),
        ("config_error", GO_CONFIG),
        ("module_error", GO_MODULE),
        ("vendor_error", GO_VENDOR),
        ("test_error", GO_TEST),
        ("cgo_error", GO_CGO),
    ]
    for ec, entries in sections:
        for i, (desc, rx) in enumerate(entries):
            out.append(_record("go", ec, i, desc, [rx],
                               "go env 2>&1 | head -20", f"Go {ec}: {desc}"))
    return out


# ---------------- Rust candidates (~50) ----------------

RUST_MISSING = [
    "tokio", "serde", "serde_json", "reqwest", "clap",
    "anyhow", "thiserror", "tracing",
]

RUST_BUILD = [
    ("cannot find macro in scope", r"error: cannot find macro `.*` in this scope"),
    ("use of unstable feature", r"use of unstable library feature"),
    ("mismatched types lifetime elision", r"mismatched types.*lifetime"),
    ("trait bound not satisfied", r"trait bound.*is not satisfied"),
    ("cannot borrow as mutable", r"cannot borrow.*as mutable"),
    ("temporary value dropped", r"temporary value dropped while borrowed"),
    ("generic arg count mismatch", r"wrong number of type arguments"),
    ("orphan rule violation", r"only traits defined in the current crate"),
    ("cyclic dependency between crates", r"cyclic package dependency"),
    ("rustc internal compiler error", r"internal compiler error"),
]

RUST_VERCONF = [
    ("rustc version too old for edition 2024", r"edition.*requires"),
    ("MSRV bumped by dep", r"package requires rustc >="),
    ("cargo-lock version 4 incompat", r"Cargo\.lock.*version is not supported"),
    ("toolchain channel nightly required", r"requires.*nightly"),
    ("multiple versions of same crate", r"multiple.*versions.*of crate"),
    ("feature flag 'default' conflict", r"features.*conflict"),
]

RUST_CARGO = [
    ("cargo fetch network timeout", r"failed to fetch.*https://crates\.io"),
    ("registry sparse index not supported", r"sparse.*protocol.*not enabled"),
    ("cargo home readonly in CI", r"cargo.*cannot create.*permission denied"),
    ("workspace member missing Cargo.toml", r"workspace member.*not found"),
    ("path dep outside workspace root", r"workspace.*path.*outside"),
    ("cargo publish dry-run registry auth", r"cargo publish.*401"),
    ("vendored deps not used due to config", r"vendor.*not used"),
    ("git dep branch moved", r"git.*branch .* not found"),
    ("git dep tag deleted upstream", r"tag .* not found"),
    ("cargo-config.toml syntax", r"could not parse.*config"),
]

RUST_LINKER = [
    ("cc linker not found", r"linker `cc` not found"),
    ("lld required but missing", r"error: linker `lld`"),
    ("musl target libs missing", r"x86_64-unknown-linux-musl.*not found"),
    ("macOS framework not linked", r"framework not found"),
    ("Windows MSVC linker missing", r"link\.exe.*not found"),
    ("static link libssl missing", r"ld.*cannot find -lssl"),
]

RUST_FEATURE = [
    ("feature 'default-tls' conflicts with 'rustls'", r"features.*default-tls.*rustls"),
    ("no-default-features required in CI", r"default feature.*not supported"),
    ("feature gate required but stable", r"requires nightly.*feature gate"),
    ("crate without any features has unused", r"unused features"),
    ("dev-dep feature leaks to release", r"dev-dependency.*feature.*leaked"),
]

RUST_MACRO = [
    ("proc-macro panic in derive", r"proc macro panicked"),
    ("declarative macro recursion limit", r"recursion limit reached.*macro"),
    ("macro_rules hygiene violation", r"hygiene.*violation"),
    ("#[cfg(feature)] mis-spelled", r"unexpected cfg condition"),
    ("attribute macro not found", r"cannot find attribute.*in this scope"),
]


def build_rust() -> list[dict]:
    out: list[dict] = []
    for i, pkg in enumerate(RUST_MISSING):
        out.append(_record(
            "rust", "missing_dependency", i,
            description=f"Rust crate '{pkg}' not in Cargo.toml",
            stderr_regex=[rf"can't find crate for `{pkg}`",
                          rf"unresolved import `{pkg}`"],
            verify_command=f"cargo tree | grep {pkg} 2>&1 || true",
            fix_description=f"cargo add {pkg}",
            structured_hints=[{"kind": "install_package", "manager": "cargo", "name": pkg}],
            package_managers=["cargo"],
        ))
    sections = [
        ("build_error", RUST_BUILD),
        ("version_conflict", RUST_VERCONF),
        ("cargo_error", RUST_CARGO),
        ("linker_error", RUST_LINKER),
        ("feature_flag", RUST_FEATURE),
        ("macro_error", RUST_MACRO),
    ]
    for ec, entries in sections:
        for i, (desc, rx) in enumerate(entries):
            out.append(_record("rust", ec, i, desc, [rx],
                               "cargo --version 2>&1", f"Rust {ec}: {desc}"))
    return out


# ---------------- Java candidates (~50) ----------------

JAVA_MISSING = [
    "org.springframework:spring-core", "com.fasterxml.jackson.core:jackson-databind",
    "org.slf4j:slf4j-api", "org.apache.commons:commons-lang3",
    "com.google.guava:guava", "junit:junit", "org.mockito:mockito-core",
    "org.projectlombok:lombok", "io.netty:netty-all", "org.postgresql:postgresql",
]

JAVA_BUILD = [
    ("javac unsupported source release", r"source release \d+ requires target release"),
    ("missing module-info path", r"module-info.*not found"),
    ("annotation processor not found", r"Annotation processor.*not found"),
    ("jar contains duplicate entry", r"duplicate entry.*\\.class"),
    ("preview feature requires --enable-preview", r"preview.*feature.*enable-preview"),
    ("TOOLCHAIN toolchains.xml misconfig", r"toolchains\.xml.*invalid"),
    ("javadoc -html5 vs -html4", r"javadoc.*-html4.*removed"),
    ("bytecode version mismatch", r"Unsupported class file major version"),
    ("static imports ambiguous", r"reference to .* is ambiguous"),
    ("enum switch default missing", r"missing default case"),
]

JAVA_VERCONF = [
    ("JDK 21 runs code built for 23", r"Unsupported class file major version 67"),
    ("maven surefire JVM fork version", r"surefire.*JVM.*incompatible"),
    ("gradle wrapper Java too new for gradle", r"Minimum supported Gradle version"),
    ("jackson version split across deps", r"Jackson version .* incompatible"),
    ("slf4j binding version mismatch", r"SLF4J.*Class path contains multiple"),
    ("spring-boot starter version mix", r"spring-boot.*version mismatch"),
]

JAVA_MAVEN = [
    ("settings.xml mirror auth missing", r"401.*repository"),
    ("snapshot pom not updated", r"SNAPSHOT.*resolving"),
    ("plugin version not pinned", r"plugin.*latest.*warning"),
    ("missing parent POM relativePath", r"Non-resolvable parent POM"),
    ("reactor build order broken", r"reactor.*Failed to build"),
    ("dependencyManagement scope wrong", r"scope.*overridden"),
    ("profile not activated by env", r"profile.*not active"),
    ("maven-release-plugin SCM not set", r"release-plugin.*SCM"),
]

JAVA_GRADLE = [
    ("gradle daemon OOM", r"Gradle Daemon.*OOM|gradle.*Metaspace"),
    ("kotlin dsl syntax error", r"Script compilation error"),
    ("composite build missing settings.gradle", r"composite build.*no settings\.gradle"),
    ("gradle version catalog typo", r"version catalog.*alias"),
    ("configuration cache not reusable", r"configuration cache problems"),
    ("task dependency graph cycle", r"Circular dependency between tasks"),
    ("gradle wrapper checksum mismatch", r"wrapper.*checksum"),
    ("gradle plugin portal 403", r"plugin portal.*403"),
]

JAVA_CLASSPATH = [
    ("ClassNotFoundException at runtime only", r"ClassNotFoundException"),
    ("NoClassDefFoundError shaded jar", r"NoClassDefFoundError"),
    ("duplicate service loader entry", r"ServiceConfigurationError"),
    ("META-INF/services not shaded", r"No provider found"),
    ("war lib conflict with container", r"javax\\.servlet.*signer"),
    ("spring boot fat jar nested class", r"Unable to find main class"),
    ("JPMS split package", r"reads package .* from both"),
    ("ClassLoader parent-first order", r"LinkageError.*ClassLoader"),
]


def build_java() -> list[dict]:
    out: list[dict] = []
    for i, pkg in enumerate(JAVA_MISSING):
        out.append(_record(
            "java", "missing_dependency", i,
            description=f"Java dep '{pkg}' not resolved by Maven/Gradle",
            stderr_regex=[rf"Could not find artifact {pkg}",
                          rf"Failed to resolve: {pkg}"],
            verify_command="mvn -q dependency:list 2>&1 | head -20 || true",
            fix_description=f"Add {pkg} to pom.xml / build.gradle",
            package_managers=["maven", "gradle"],
        ))
    sections = [
        ("build_error", JAVA_BUILD),
        ("version_conflict", JAVA_VERCONF),
        ("maven_error", JAVA_MAVEN),
        ("gradle_error", JAVA_GRADLE),
        ("classpath_error", JAVA_CLASSPATH),
    ]
    for ec, entries in sections:
        for i, (desc, rx) in enumerate(entries):
            out.append(_record("java", ec, i, desc, [rx],
                               "java --version 2>&1", f"Java {ec}: {desc}"))
    return out


# ---------------- Ruby candidates (~15) ----------------

RUBY_MISSING = [
    "rails", "sidekiq", "puma", "rspec",
]

RUBY_BUNDLER = [
    ("bundle install native extension libpq", r"An error occurred while installing pg"),
    ("Gemfile.lock PLATFORM drift on CI", r"Your bundle only supports platforms"),
    ("bundler version requirement mismatch", r"Bundler.*you must use Bundler"),
    ("frozen lockfile blocks auto-update", r"frozen.*changes detected"),
]

RUBY_BUILD = [
    ("bundle exec rake build fails mkmf", r"mkmf\\.rb can't find header"),
    ("ruby FFI gem arch mismatch", r"FFI.*cannot load"),
    ("native mysql2 gem openssl missing", r"mysql2.*openssl"),
]

RUBY_VERCONF = [
    ("rbenv version file missing", r"rbenv: version .* is not installed"),
    ("Gemfile ruby version unavailable", r"Your Ruby version is .* but your Gemfile specified"),
    ("activesupport vs actionpack drift", r"activesupport.*actionpack.*incompatible"),
    ("rails 7 vs sprockets 3 incompat", r"sprockets.*rails.*incompatible"),
]


def build_ruby() -> list[dict]:
    out: list[dict] = []
    for i, pkg in enumerate(RUBY_MISSING):
        out.append(_record(
            "ruby", "missing_dependency", i,
            description=f"Ruby gem '{pkg}' missing",
            stderr_regex=[rf"cannot load such file -- {pkg}",
                          rf"Could not find gem '{pkg}'"],
            verify_command=f"gem list | grep {pkg} 2>&1 || true",
            fix_description=f"bundle add {pkg} or gem install {pkg}",
            package_managers=["bundler", "gem"],
        ))
    sections = [
        ("bundler_error", RUBY_BUNDLER),
        ("build_error", RUBY_BUILD),
        ("version_conflict", RUBY_VERCONF),
    ]
    for ec, entries in sections:
        for i, (desc, rx) in enumerate(entries):
            out.append(_record("ruby", ec, i, desc, [rx],
                               "ruby --version 2>&1", f"Ruby {ec}: {desc}"))
    return out


# ---------------- Terraform candidates (~15) ----------------

TF_PROVIDER = [
    ("provider aws plan drift from v4 to v5", r"Error: Unsupported argument"),
    ("provider version locked older", r"no available releases.*provider"),
    ("required_providers block missing", r"Missing required provider"),
    ("registry source mirror auth", r"Failed to query available provider packages.*401"),
]

TF_STATE = [
    ("state lock held by dead CI job", r"Error acquiring the state lock"),
    ("backend config S3 bucket region mismatch", r"backend.*region"),
    ("state schema version too new", r"state snapshot was created by.*newer"),
    ("import address exists in state", r"already managed by Terraform"),
]

TF_VERCONF = [
    ("terraform core too old for feature", r"required_version"),
    ("tfstate moved resource not known", r"moved block.*unknown"),
    ("opentofu vs terraform state difference", r"OpenTofu.*Terraform.*state"),
]

TF_CONFIG = [
    ("HCL interpolation deprecated syntax", r"interpolation-only expressions are deprecated"),
    ("for_each with unknown values", r"for_each.*unknown"),
    ("count vs for_each mix-up", r"count.*for_each.*cannot"),
    ("sensitive output to module caller", r"sensitive.*output"),
]


def build_terraform() -> list[dict]:
    out: list[dict] = []
    sections = [
        ("provider_error", TF_PROVIDER),
        ("state_error", TF_STATE),
        ("version_conflict", TF_VERCONF),
        ("config_error", TF_CONFIG),
    ]
    for ec, entries in sections:
        for i, (desc, rx) in enumerate(entries):
            out.append(_record("terraform", ec, i, desc, [rx],
                               "terraform version 2>&1", f"Terraform {ec}: {desc}"))
    return out


# ---------------- Main ----------------

def main() -> int:
    all_records: list[dict] = []
    all_records.extend(build_python())
    all_records.extend(build_node())
    all_records.extend(build_docker())
    all_records.extend(build_go())
    all_records.extend(build_rust())
    all_records.extend(build_java())
    all_records.extend(build_ruby())
    all_records.extend(build_terraform())

    # Write per (ecosystem, error_class) shard.
    by_shard: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in all_records:
        by_shard[(r["ecosystem"], r["error_class"])].append(r)

    if OUT_DIR.exists():
        for p in OUT_DIR.rglob("*.json"):
            p.unlink()
    for (eco, ec), recs in by_shard.items():
        shard_dir = OUT_DIR / eco
        shard_dir.mkdir(parents=True, exist_ok=True)
        shard_path = shard_dir / f"{ec}.json"
        shard = {"ecosystem": eco, "error_class": ec, "schema_version": 4, "records": recs}
        shard_path.write_text(json.dumps(shard, indent=2))

    by_eco: dict[str, int] = defaultdict(int)
    for r in all_records:
        by_eco[r["ecosystem"]] += 1
    print(f"candidate total: {len(all_records)}")
    for eco, n in sorted(by_eco.items()):
        print(f"  {eco}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
