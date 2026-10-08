# Migrating from WireCloud 1

WireCloud includes an importer for a legacy Django-based instance backed by MySQL, PostgreSQL, or SQLite. The importer reads the old SQL database and calls the old instance over HTTP to retrieve packaged resources.

## What is imported

The command attempts to migrate:

- constants;
- users, groups, and their mappings;
- marketplace definitions;
- catalogue resources and access rules;
- workspaces, tabs, widget instances, preferences, and sharing rules; and
- version 2.0 wiring configurations and operators.

Unsupported or inconsistent records are reported while the importer continues where possible. A wiring configuration whose stored version is not `2.0` is skipped.

## Before migrating

1. Back up the old SQL database and old application files.
2. Back up the destination if it contains any data.
3. Keep the old WireCloud HTTP service reachable during the import.
4. Obtain an old-instance superuser account and direct SQL read credentials.
5. Configure and start the destination WireCloud instance with MongoDB and Elasticsearch.
6. Install migration dependencies in the environment that will run the command with `python -m pip install '.[migration]'`. The supplied runtime container does not install this extra; use a source environment or build a derived migration image rather than modifying a running production container.

Run the migration against a fresh destination. The command can reuse some existing users and groups, but name conflicts can skip workspaces or produce a partial result; it is not designed as continuous synchronization.

## Run the importer

MySQL example:

```bash
python -m manage migrate \
  --url https://old-wirecloud.example.com \
  --admin-user old-admin \
  --admin-password 'OLD_ADMIN_PASSWORD' \
  --db-type mysql \
  --db-host old-db.example.com \
  --db-name wirecloud \
  --db-user migration_reader \
  --db-password 'OLD_DATABASE_PASSWORD'
```

PostgreSQL uses `--db-type postgresql`; the default port becomes 5432. For SQLite, provide the database file as `--db-name` and omit database host/user/password options:

```bash
python -m manage migrate \
  --url http://old-wirecloud.internal:8000 \
  --admin-user old-admin \
  --admin-password 'OLD_ADMIN_PASSWORD' \
  --db-type sqlite \
  --db-name /srv/old-wirecloud/db.sqlite3
```

The command displays its source and requests confirmation. Add `--yes` only in reviewed automation. `--no-verify-ssl` disables verification for the old server and should be limited to a controlled migration network with a known certificate problem.

!!! warning
    Command-line passwords can be visible in shell history and process listings. Run the migration from a restricted administration host, use short-lived credentials, and rotate them afterward.

## Widget layouts

WireCloud 1.x widget positions and sizes use a different grid than the current one. The importer converts each widget's stored position into an approximate layout on the new grid. Column/grid and full-background states are retained, and the old left, right, bottom, and top sidebar indexes become retracted overlay docks. The old free layout has no exact GridStack equivalent, so pixel-based positions use automatic placement and approximate sizes. Review widget placement after migrating and adjust it if needed.

If the destination database was created by an earlier WireCloud FastAPI 2.0 development build, its workspaces may still store the old `positions` format instead of `layouts`. Such records are converted in memory when they are loaded and persisted in the new format on the next workspace change. Run `python -m manage convert_layouts` once to convert the whole database eagerly; the command is idempotent and is not needed for a database created by the current version or produced by `migrate`.

## Validate the result

Capture the command output and review every warning or failed record. Then:

```bash
python -m manage populate
python -m manage rebuildsearchindexes
```

Verify at least:

- administrator and normal-user login;
- user/group membership and permissions;
- private and public workspace access;
- catalogue package downloads and widget rendering;
- tab layouts and component preferences;
- wiring connections and operator behavior; and
- resource and workspace search.

Keep the old instance read-only until owners have validated representative workspaces. If the import must be repeated, restore a clean destination backup first rather than importing over the partial destination.
