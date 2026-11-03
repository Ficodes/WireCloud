# Docker deployment

This directory contains a complete Docker setup for WireCloud:

- `Dockerfile`: multi-stage image build (frontend assets + python wheel)
- `settings.py`: environment-driven runtime settings
- `entrypoint.sh`: initializes writable directories and starts the app
- `docker-compose.yml`: Wirecloud + MongoDB + Elasticsearch stack
- `.env.example`: environment variable template

## Quick start

1. Create the environment file:

```bash
cp docker/.env.example docker/.env
```

2. Replace `WIRECLOUD_JWT_KEY` and `WIRECLOUD_SECRET_KEY` in `docker/.env`
   with different random values.

3. Start the stack from the repository root:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

4. Install the bundled resources and create an administrator:

```bash
docker compose -f docker/docker-compose.yml exec wirecloud python -m manage populate
docker compose -f docker/docker-compose.yml exec wirecloud python -m manage createsuperuser
```

5. Open <http://localhost:8000/>.

## Published images

Each published release builds regular and MCP variants for `linux/amd64` and
`linux/arm64` in one configurable repository. The default is Docker Hub:

```bash
docker pull fiware/wirecloud:2.0.0
docker pull fiware/wirecloud:2.0.0-mcp
```

The regular image installs the base application. The `-mcp` image also installs
the MCP SDK and its tested dependency constraints using
`WIRECLOUD_INSTALL_MCP=true`. Enable `wirecloud.oauth2provider` and `wirecloud.mcp`
in the deployment's `WIRECLOUD_INSTALLED_APPS` and configure their public URLs as
described in the [MCP guide](../docs/mcp.md#docker).

Stable releases also update major/minor aliases and `latest` for the regular
image, with matching `-mcp` aliases for the MCP image (for example, `2.0-mcp`,
`2-mcp`, and `latest-mcp`). Prereleases publish only their full version tags,
with and without `-mcp`; they do not replace stable aliases. CI keeps the two
variants' build caches separate.

Check the release notes for the canonical location when the repository's
publishing configuration overrides this default.

For a deployment based on a published image, remove the `build` block from the
`wirecloud` service in `docker-compose.yml` and replace its image with a pinned
release, for example `image: fiware/wirecloud:2.0.0` or
`image: fiware/wirecloud:2.0.0-mcp`. Keep the supplied
environment, ports, dependencies, and volumes.

## Notes

- `settings.py` is loaded through `PYTHONPATH=/app/docker` in the image.
- Persistent application, MongoDB, and Elasticsearch data are stored in named
  volumes. Do not run `docker compose down --volumes` unless you intend to
  delete them.
- The complete procedure, configuration reference, backup notes, and production
  checklist are in the [installation documentation](../docs/installation.md).
