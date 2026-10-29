# Contributing

WireCloud contains a Python/FastAPI backend and a TypeScript/JavaScript/Sass frontend bundled with Webpack.

## Development environment

Requirements:

- Python 3.9 or newer;
- Node.js and npm;
- MongoDB; and
- Elasticsearch.

Set up the repository:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test,migration]'
npm ci
npm run build
```

The default source settings live in `src/settings.py`. For a custom local environment, put another `settings.py` earlier on `PYTHONPATH` rather than committing credentials to the repository.

Initialize the development data and start the service:

```bash
PYTHONPATH=src python -m manage populate
PYTHONPATH=src python -m manage createsuperuser
PYTHONPATH=src python -m manage runserver --reload
```

## Frontend commands

The commands in `package.json` are:

| Command | Purpose |
| --- | --- |
| `npm run build` | Generate settings and build all frontend assets. |
| `npm run build:js` | Generate settings and build JavaScript assets. |
| `npm run build:css` | Generate settings and build Sass/CSS assets. |
| `npm run test:js` | Run JavaScript tests. |
| `npm run test:js:cov` | Run JavaScript tests with coverage. |

The prebuild step chooses Python from `PYTHON`, `./venv/bin/python`, the Windows virtual environment path, or a system Python, in that order. Set `PYTHON` explicitly if the selected interpreter does not have access to the intended settings.

## Python tests

Run the full Python suite:

```bash
pytest
```

Generate terminal and HTML coverage reports when needed:

```bash
pytest --cov
pytest --cov --cov-report=html
```

### OAuth and MCP integration

CI runs the full backend suite on Python 3.11 and 3.13 with the pinned MCP
dependencies, alongside the regular Python 3.9 and JavaScript jobs. To reproduce
the MCP environment in a Python 3.11+ virtual environment:

```bash
python -m pip install -c constraints-mcp.txt -r requirements.txt -r requirements-test.txt mcp
python -m pytest tests
```

The `oauth-mcp-python-*` CI artifacts contain JUnit results and branch coverage
for OAuth, MCP, and the authentication module. Both matrix jobs require 100% line
and branch coverage for these modules. To run the same coverage gate locally:

```bash
python -m pytest tests \
  --cov=wirecloud.oauth2provider --cov=wirecloud.mcp \
  --cov=wirecloud.commons.auth \
  --cov-branch --cov-fail-under=100 --cov-report=term-missing
```

The integration tests exercise all
33 tools through the official SDK and run discovery, consent, token exchange,
an authenticated SDK call, and revocation over real HTTP sockets with a deployment
URL prefix. MongoDB and search remain mocked; these tests do not contact a live
identity provider. See the [OAuth](oauth2.md#verification) and
[MCP](mcp.md#maintenance-and-verification) pages for the boundaries covered.

## Documentation

Install the pinned documentation tool and build in strict mode:

```bash
python -m pip install -r docs/requirements.txt
mkdocs build --strict
```

Preview changes locally:

```bash
mkdocs serve
```

The navigation is declared in `mkdocs.yml`. Add each new page there; strict builds reject broken internal links and configuration warnings. Read the Docs uses `.readthedocs.yaml` and installs only `docs/requirements.txt`, so documentation builds remain independent of the application and its external services.

## Release wheels

The package workflow builds the regular wheel once, then generates the standalone
MCP variant from it:

```bash
python -m pip install build packaging
python -m build --wheel
python scripts/build-mcp-wheel.py dist/*.whl
```

Run the last command with the regular wheel only. It creates a second wheel with
a `+mcp` local version, Python 3.11 minimum, and mandatory dependency pins from
`constraints-mcp.txt`. Application files and frontend assets remain byte-identical;
the script updates distribution metadata, installation paths, and wheel integrity
records. CI verifies each wheel in a separate environment before storing both in
the `wirecloud-wheels` artifact and attaching both files to published releases.

## Translations

Extract messages for all configured languages or one language:

```bash
PYTHONPATH=src python -m manage gentranslations
PYTHONPATH=src python -m manage gentranslations --language es
```

Compile translations before testing them:

```bash
PYTHONPATH=src python -m manage compiletranslations
PYTHONPATH=src python -m manage compiletranslations --language es --verbose
```

Review generated catalogue changes carefully. Do not overwrite translators' work when updating source locations.
