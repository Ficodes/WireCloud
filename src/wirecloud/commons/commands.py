# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.
import argparse
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable, Any, Optional
import json
import re
from bson import ObjectId
import traceback

from wirecloud.catalogue.utils import add_packaged_resource, create_widget_on_resource_creation, \
    deploy_operators_on_resource_creation
from wirecloud.commons.auth.crud import get_user_by_username
from wirecloud.commons.utils.template.base import convert_legacy_layout, default_desktop_screen_size_id, \
    is_legacy_default_screen_sizes
from wirecloud.commons.utils.template.schemas.macdschemas import MACDWidget, MACDOperator, MACDMashup
from wirecloud.platform.workspace.models import WorkspaceAccessPermissions, DBWorkspacePreference

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import pymysql
    from pymysql.cursors import DictCursor as MySQLDictCursor
except ImportError:
    pymysql = None
    MySQLDictCursor = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

try:
    import sqlite3
except ImportError:
    sqlite3 = None

from wirecloud.database import get_session, commit, Id


def _hash_password(password: str) -> str:
    """Hash a password using pbkdf2_sha256, compatible with Django's password hashing."""
    import os
    from hashlib import pbkdf2_hmac
    from base64 import b64encode

    iterations = 600000
    salt = b64encode(os.urandom(16)).decode('ascii').rstrip('=')[:22]
    hashed = pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${b64encode(hashed).decode('ascii')}"


async def createsuperuser_cmd(args: argparse.Namespace) -> None:
    import getpass

    username = args.username
    email = args.email
    password = args.password

    # Prompt for missing values interactively
    if not username:
        while True:
            username = input("Username: ").strip()
            if username:
                break
            print("Error: Username cannot be empty.")

    if not email:
        email = input("Email address (optional): ").strip()

    if not password:
        while True:
            password = getpass.getpass("Password: ")
            if not password:
                print("Error: Password cannot be empty.")
                continue
            password_confirm = getpass.getpass("Password (again): ")
            if password != password_confirm:
                print("Error: Passwords do not match.")
                continue
            break

    async for session in get_session():
        from wirecloud.commons.auth.crud import get_user_by_username, create_user
        from wirecloud.commons.auth.schemas import UserCreate

        existing = await get_user_by_username(session, username)
        if existing is not None:
            print(f"Error: A user with username '{username}' already exists.")
            return

        user_data = UserCreate(
            username=username,
            email=email or '',
            first_name='',
            last_name='',
            is_superuser=True,
            is_staff=True,
            is_active=True,
            idm_data={},
            password=_hash_password(password)
        )

        await create_user(session, user_data)
        await commit(session)
        print(f"Superuser '{username}' created successfully.")
        break


async def migrate_cmd(args: argparse.Namespace) -> None:
    """
    Migrate data from an old Django-based Wirecloud instance to the new FastAPI/MongoDB version.

    This command will:
    1. Migrate users and groups from the old SQL database
    2. Migrate catalogue resources using the API and file system
    3. Migrate workspaces using the API
    4. Copy catalogue and deployment media files
    """

    # Check dependencies
    if args.db_type == 'mysql' and pymysql is None:
        print("Error: pymysql is required for MySQL. Install it with: pip install pymysql")
        sys.exit(1)
    elif args.db_type == 'postgresql' and psycopg2 is None:
        print("Error: psycopg2 is required for PostgreSQL. Install it with: pip install psycopg2-binary")
        sys.exit(1)
    elif args.db_type == 'sqlite' and sqlite3 is None:
        print("Error: sqlite3 is required for SQLite")
        sys.exit(1)

    if aiohttp is None:
        print("Error: aiohttp is required for migration. Install it with: pip install aiohttp")
        sys.exit(1)

    # Validate database credentials for non-SQLite databases
    if args.db_type != 'sqlite':
        if not args.db_user:
            print(f"Error: --db-user is required for {args.db_type}")
            sys.exit(1)
        if not args.db_password:
            print(f"Error: --db-password is required for {args.db_type}")
            sys.exit(1)

    # Set default port if not specified
    if args.db_port is None:
        if args.db_type == 'mysql':
            args.db_port = 3306
        elif args.db_type == 'postgresql':
            args.db_port = 5432

    print("=" * 80)
    print("Wirecloud Migration Tool")
    print("=" * 80)
    print()
    print("This tool will migrate data from an old Wirecloud instance to this new version.")
    print(f"Source URL: {args.url}")
    if args.db_type == 'sqlite':
        print(f"Database: SQLite {args.db_name}")
    else:
        print(f"Database: {args.db_type.upper()} - {args.db_name} at {args.db_host}:{args.db_port}")
    print()

    if not args.yes:
        confirm = input("Do you want to continue? (yes/no): ")
        if confirm.lower() not in ['yes', 'y']:
            print("Migration cancelled.")
            return

    try:
        # Connect to old database
        print("\n[1/7] Connecting to old database...")

        db_connection = None
        if args.db_type == 'mysql':
            db_connection = pymysql.connect(
                host=args.db_host,
                port=args.db_port,
                user=args.db_user,
                password=args.db_password,
                database=args.db_name,
                charset='utf8mb4',
                cursorclass=MySQLDictCursor
            )
            print(f"✓ Connected to MySQL database: {args.db_name}")
        elif args.db_type == 'postgresql':
            db_connection = psycopg2.connect(
                host=args.db_host,
                port=args.db_port,
                user=args.db_user,
                password=args.db_password,
                dbname=args.db_name,
                cursor_factory=RealDictCursor
            )
            print(f"✓ Connected to PostgreSQL database: {args.db_name}")
        elif args.db_type == 'sqlite':
            db_connection = sqlite3.connect(args.db_name)
            db_connection.row_factory = sqlite3.Row
            print(f"✓ Connected to SQLite database: {args.db_name}")

        if db_connection is None:
            print("Error: Failed to establish database connection")
            sys.exit(1)

        # Setup HTTP client for API calls
        connector = aiohttp.TCPConnector(ssl=not args.no_verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as http_session:

            # Login to old instance
            print("\n[2/7] Authenticating with old Wirecloud instance...")
            token = await _login_old_wirecloud(http_session, args.url, args.admin_user, args.admin_password)
            print(f"✓ Authenticated as {args.admin_user}")

            # Check if user is an administrator
            with _db_cursor(db_connection) as cursor:
                cursor.execute(_adapt_sql_query("""SELECT is_superuser FROM auth_user WHERE username = %s""", args.db_type), (args.admin_user,))
                is_superuser = cursor.fetchone()['is_superuser']
                if not is_superuser:
                    print("Error: User is not an administrator")
                    sys.exit(1)

            # Get database session
            async for session in get_session():
                # Migrate constants
                print("\n[3/7] Migrating constants...")
                count = await _migrate_constants(db_connection, session, args.db_type)
                print(f"✓ Migrated {count} constants")

                # Migrate users and groups
                print("\n[4/7] Migrating users and groups...")
                user_id_mapping, group_id_mapping = await _migrate_users_and_groups(db_connection, session, args.db_type)
                print(f"✓ Migrated {len(user_id_mapping)} users and {len(group_id_mapping)} groups")

                # Migrate markets
                print("\n[5/7] Migrating markets...")
                market_count = await _migrate_markets(db_connection, session, user_id_mapping, args.db_type)
                print(f"✓ Migrated {market_count} markets")

                # Migrate catalogue resources
                print("\n[6/7] Migrating catalogue resources...")
                resource_mapping = await _migrate_catalogue_resources(
                    db_connection, session, http_session, args.url, token,
                    user_id_mapping, group_id_mapping, args.db_type
                )
                print(f"✓ Migrated {len(resource_mapping)} catalogue resources")

                # Migrate workspaces
                print("\n[7/7] Migrating workspaces...")
                workspace_count = await _migrate_workspaces(
                    db_connection, session, http_session, args.url, token,
                    user_id_mapping, group_id_mapping, resource_mapping, args.db_type
                )
                print(f"✓ Migrated {workspace_count} workspaces")
                break

        db_connection.close()

        print("\n" + "=" * 80)
        print("Migration completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        traceback.print_exc()
        print("Migration cancelled.")
        raise


async def convert_layouts_cmd(args: argparse.Namespace) -> None:
    """
    Convert workspace documents already stored in this instance's MongoDB database that still carry the
    old, pre-GridStack fields ('positions'/'layout' on widget instances, 'baselayout'/'initiallayout'
    workspace and tab preferences) into the new 'layouts'-based format, using the same best-effort
    conversion rule used by the 'migrate' command. Safe to run more than once: documents that have
    already been converted (no 'positions'/'layout' widget field left) are left untouched.
    """
    examined = 0
    converted = 0

    async for session in get_session():
        workspaces = await session.client.workspaces.find({}).to_list()

        for workspace in workspaces:
            examined += 1
            set_fields: dict[str, Any] = {}
            unset_fields: dict[str, Any] = {}

            workspace_prefs = workspace.get('preferences') or []
            preferences, preferences_changed = _convert_legacy_preferences(workspace_prefs)
            if preferences_changed:
                set_fields['preferences'] = preferences

            for tab_id, tab in (workspace.get('tabs') or {}).items():
                tab_prefs = tab.get('preferences') or []
                tab_preferences, tab_preferences_changed = _convert_legacy_preferences(tab_prefs)
                if tab_preferences_changed:
                    set_fields[f'tabs.{tab_id}.preferences'] = tab_preferences

                tab_legacy_default_screen_sizes = _tab_uses_legacy_default_screen_sizes(tab_prefs, workspace_prefs)

                for widget_id, widget in (tab.get('widgets') or {}).items():
                    if 'positions' not in widget and 'layout' not in widget:
                        continue

                    layouts = _migrate_widget_positions_to_layouts(
                        widget.get('positions') or {}, tab_legacy_default_screen_sizes
                    )
                    layouts.update(widget.get('layouts') or {})

                    set_fields[f'tabs.{tab_id}.widgets.{widget_id}.layouts'] = layouts
                    unset_fields[f'tabs.{tab_id}.widgets.{widget_id}.positions'] = ""
                    unset_fields[f'tabs.{tab_id}.widgets.{widget_id}.layout'] = ""

            if not set_fields and not unset_fields:
                continue

            update: dict[str, Any] = {}
            if set_fields:
                update['$set'] = set_fields
            if unset_fields:
                update['$unset'] = unset_fields

            await session.client.workspaces.update_one({"_id": workspace['_id']}, update)
            converted += 1

        break

    print(f"Examined {examined} workspace(s), converted {converted}.")


def _convert_legacy_preferences(rows: list[dict]) -> tuple[list[dict], bool]:
    # Drop the removed 'baselayout'/'initiallayout' preferences. For 'screenSizes': drop it when
    # it is 'legacy default' so the platform's new responsive defaults apply; otherwise keep it
    # and fix up its entries (add 'columns'). Returns the (possibly unchanged) preference list and
    # whether it was modified.
    changed = False
    new_rows = []
    for pref in rows:
        name = pref.get('name')
        if name in ('baselayout', 'initiallayout'):
            changed = True
            continue

        if name == 'screenSizes':
            if is_legacy_default_screen_sizes(pref.get('value')):
                changed = True
                continue

            new_value = _migrate_screensizes_value(pref.get('value') or "")
            if new_value != pref.get('value'):
                pref = {**pref, 'value': new_value}
                changed = True

        new_rows.append(pref)

    return new_rows, changed


def _adapt_sql_query(query: str, db_type: str) -> str:
    """Adapt SQL query for different database types."""
    if db_type == 'sqlite':
        # SQLite uses ? as placeholder instead of %s
        return query.replace('%s', '?')
    return query


def _sql_identifier(name: str, db_type: str) -> str:
    """Quote legacy camel-case columns without relying on backend SQL modes."""
    if db_type == "mysql":
        return f"`{name}`"
    return f'"{name}"'


@contextmanager
def _db_cursor(db_connection):
    """Yield and reliably close cursors for sqlite, psycopg, and pymysql."""
    cursor = db_connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _dict_from_row(row, db_type: str):
    """Convert database row to dictionary based on database type."""
    if db_type == 'sqlite':
        return dict(row)
    # For MySQL and PostgreSQL with DictCursor, rows are already dicts
    return row


def _table_exists(cursor, table_name: str, db_type: str) -> bool:
    """Check if a table exists in the database."""
    if db_type == 'mysql':
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        return cursor.fetchone() is not None
    elif db_type == 'postgresql':
        cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s)", (table_name,))
        return cursor.fetchone()["exists"]
    elif db_type == 'sqlite':
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cursor.fetchone() is not None
    return False


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_datetime(value: Any) -> Optional[datetime]:
    """Normalize Django database datetime values across supported SQL backends."""
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        # WireCloud v2 stores some dates as JavaScript timestamps in milliseconds.
        timestamp = float(value)
        if abs(timestamp) >= 100_000_000_000:
            timestamp /= 1000
        result = datetime.fromtimestamp(timestamp, timezone.utc)
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if re.fullmatch(r"-?\d+(?:\.\d+)?", normalized):
            return _as_datetime(float(normalized))
        result = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    else:
        raise TypeError(f"Unsupported datetime value: {value!r}")

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _group_codename(name: str) -> str:
    codename = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return codename or "group"


_LEGACY_PERMISSION_MAP = {
    ("auth", "user", "add_user"): "USER.CREATE",
    ("auth", "user", "change_user"): "USER.EDIT",
    ("auth", "user", "delete_user"): "USER.DELETE",
    ("auth", "user", "view_user"): "USER.VIEW",
    ("auth", "group", "add_group"): "GROUP.CREATE",
    ("auth", "group", "change_group"): "GROUP.EDIT",
    ("auth", "group", "delete_group"): "GROUP.DELETE",
    ("auth", "group", "view_group"): "GROUP.VIEW",
    ("commons", "organization", "add_organization"): "ORGANIZATION.CREATE",
    ("commons", "organization", "change_organization"): "ORGANIZATION.EDIT",
    ("commons", "organization", "delete_organization"): "ORGANIZATION.DELETE",
    ("commons", "organization", "view_organization"): "ORGANIZATION.VIEW",
    ("commons", "team", "add_team"): "GROUP.CREATE",
    ("commons", "team", "change_team"): "GROUP.EDIT",
    ("commons", "team", "delete_team"): "GROUP.DELETE",
    ("commons", "team", "view_team"): "GROUP.VIEW",
    ("platform", "workspace", "add_workspace"): "WORKSPACE.CREATE",
    ("platform", "workspace", "change_workspace"): "WORKSPACE.*",
    ("platform", "workspace", "delete_workspace"): "WORKSPACE.DELETE",
    ("platform", "workspace", "view_workspace"): "WORKSPACE.VIEW",
    ("platform", "tab", "add_tab"): "WORKSPACE.TAB.CREATE",
    ("platform", "tab", "change_tab"): "WORKSPACE.TAB.*",
    ("platform", "tab", "delete_tab"): "WORKSPACE.TAB.DELETE",
    ("platform", "iwidget", "add_iwidget"): "WORKSPACE.WIDGET.CREATE",
    ("platform", "iwidget", "change_iwidget"): "WORKSPACE.WIDGET.*",
    ("platform", "iwidget", "delete_iwidget"): "WORKSPACE.WIDGET.DELETE",
    ("platform", "iwidget", "view_iwidget"): "WORKSPACE.WIDGET.VIEW",
    ("platform", "widget", "add_widget"): "WORKSPACE.WIDGET.CREATE",
    ("platform", "widget", "change_widget"): "WORKSPACE.WIDGET.*",
    ("platform", "widget", "delete_widget"): "WORKSPACE.WIDGET.DELETE",
    ("platform", "widget", "view_widget"): "WORKSPACE.WIDGET.VIEW",
    ("platform", "workspacepreference", "change_workspacepreference"): "WORKSPACE.PREFERENCES.EDIT",
    ("platform", "userworkspace", "change_userworkspace"): "WORKSPACE.SHARE",
    ("platform", "market", "add_market"): "MARKETPLACE.CREATE",
    ("platform", "market", "change_market"): "MARKETPLACE.PUBLISH",
    ("platform", "market", "delete_market"): "MARKETPLACE.DELETE",
    ("platform", "market", "view_market"): "MARKETPLACE.VIEW",
    ("catalogue", "catalogueresource", "add_catalogueresource"): "COMPONENT.INSTALL",
    ("catalogue", "catalogueresource", "change_catalogueresource"): "COMPONENT.MASSIVE_UPDATE",
    ("catalogue", "catalogueresource", "delete_catalogueresource"): "COMPONENT.DELETE",
    ("catalogue", "catalogueresource", "view_catalogueresource"): "COMPONENT.VIEW",
}


def _map_legacy_permission(app_label: str, model: str, codename: str) -> str:
    key = (app_label.lower(), model.lower(), codename.lower())
    return _LEGACY_PERMISSION_MAP.get(key, f"{app_label}.{codename}")


def _load_legacy_permissions(cursor, relation_table: str, owner_column: str,
                             db_type: str) -> dict[int, list[str]]:
    if not _table_exists(cursor, relation_table, db_type):
        return {}

    cursor.execute(f"""
        SELECT relation.{owner_column} AS owner_id,
               content_type.app_label AS app_label,
               content_type.model AS model,
               permission.codename AS codename
        FROM {relation_table} relation
        JOIN auth_permission permission ON permission.id = relation.permission_id
        JOIN django_content_type content_type ON content_type.id = permission.content_type_id
        ORDER BY relation.{owner_column}, permission.id
    """)
    permissions: dict[int, list[str]] = {}
    for row in cursor.fetchall():
        permission = _map_legacy_permission(row["app_label"], row["model"], row["codename"])
        permissions.setdefault(row["owner_id"], [])
        if permission not in permissions[row["owner_id"]]:
            permissions[row["owner_id"]].append(permission)
    return permissions


async def _login_old_wirecloud(session: aiohttp.ClientSession, url: str, username: str, password: str) -> str:
    """Login to old Wirecloud instance and return authentication token."""
    login_url = f"{url.rstrip('/')}/login"

    try:
        # First, do a GET request to obtain the CSRF token
        async with session.get(login_url) as resp:
            if resp.status != 200:
                raise Exception(f"Could not access login page: {resp.status}")

            html_content = await resp.text()

            # Extract CSRF token from the HTML
            # Look for: <input type="hidden" name="csrfmiddlewaretoken" value="...">
            import re
            csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\'][^>]+value=["\']([^"\']+)["\']', html_content)
            if not csrf_match:
                csrf_match = re.search(r'value=["\']([^"\']+)["\'][^>]+name=["\']csrfmiddlewaretoken["\']', html_content)

            if not csrf_match:
                raise Exception("Could not find CSRF token in login page")

            csrf_token = csrf_match.group(1)

        # Now POST with the CSRF token and credentials
        async with session.post(login_url, data={
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": csrf_token
        }, headers={
            "Referer": login_url
        }) as resp:
            if resp.status in [200, 302]:
                # Check if login was successful by looking for redirect or checking cookies
                return "session"  # Use session cookies
            else:
                raise Exception(f"Authentication failed with status: {resp.status}")

    except Exception as e:
        raise Exception(f"Could not authenticate with old Wirecloud instance: {e}")


async def _migrate_constants(db_connection, new_db_session, db_type: str) -> int:
    with _db_cursor(db_connection) as cursor:
        cursor.execute(_adapt_sql_query("""
                                        SELECT concept, value
                                        FROM wirecloud_constant
                                        ORDER BY id
                                        """, db_type))
        constants = cursor.fetchall()

        for constant in constants:
            await new_db_session.client.constants.update_one(
                {"concept": constant['concept']},
                {
                    "$set": {"value": constant['value']},
                    "$setOnInsert": {"_id": Id()},
                },
                upsert=True,
            )

    await commit(new_db_session)

    return len(constants)


async def _migrate_users_and_groups(db_connection, new_db_session, db_type: str) -> tuple[dict[int, str], dict[int, str]]:
    from wirecloud.commons.auth.crud import create_user_db, create_group_if_not_exists, get_group_by_name
    from wirecloud.commons.auth.schemas import Permission, UserCreate
    from wirecloud.commons.auth.models import Group

    user_id_mapping = {}  # old_id -> new_id
    group_id_mapping = {}  # old_id -> new_id

    with _db_cursor(db_connection) as cursor:
        organizations_by_group: dict[int, dict[str, Any]] = {}
        organizations_by_id: dict[int, dict[str, Any]] = {}
        if _table_exists(cursor, "wirecloud_organization", db_type):
            cursor.execute("""
                SELECT id, user_id, group_id
                FROM wirecloud_organization
                ORDER BY id
            """)
            for organization in cursor.fetchall():
                organization = _dict_from_row(organization, db_type)
                organizations_by_group[organization["group_id"]] = organization
                organizations_by_id[organization["id"]] = organization

        user_permissions = _load_legacy_permissions(
            cursor, "auth_user_user_permissions", "user_id", db_type
        )
        group_permissions = _load_legacy_permissions(
            cursor, "auth_group_permissions", "group_id", db_type
        )

        # Migrate groups first
        cursor.execute(_adapt_sql_query("""
            SELECT id, name
            FROM auth_group
            ORDER BY id
        """, db_type))
        groups = cursor.fetchall()

        for group in groups:
            group = _dict_from_row(group, db_type)
            group_id = Id(str(ObjectId()))
            is_organization = group["id"] in organizations_by_group
            group_obj = Group(
                _id=group_id,
                name=group['name'],
                codename=_group_codename(group['name']),
                is_organization=is_organization,
                path=[group_id],
                group_permissions=[
                    Permission(codename=codename)
                    for codename in group_permissions.get(group["id"], [])
                ],
            )
            await create_group_if_not_exists(new_db_session, group_obj)

            # Retrieve the created/existing group to get its ID
            new_group = await get_group_by_name(new_db_session, group['name'])
            if new_group:
                group_id_mapping[group['id']] = str(new_group.id)
                await new_db_session.client.groups.update_one(
                    {"_id": ObjectId(new_group.id)},
                    {"$set": {
                        "codename": group_obj.codename,
                        "is_organization": is_organization,
                        "path": [ObjectId(new_group.id)],
                        "group_permissions": [
                            permission.model_dump()
                            for permission in group_obj.group_permissions
                        ],
                    }},
                )
            await commit(new_db_session)

        # Migrate users
        organization_user_ids = {
            organization["user_id"] for organization in organizations_by_id.values()
        }
        cursor.execute(_adapt_sql_query("""
            SELECT id, password, last_login, is_superuser, username, first_name, last_name,
                   email, is_staff, is_active, date_joined
            FROM auth_user
            ORDER BY id
        """, db_type))
        users = cursor.fetchall()

        for user in users:
            user = _dict_from_row(user, db_type)
            # Organizations were represented by synthetic, non-login users in v2.
            # Their replacement is the organization root group created above.
            if user["id"] in organization_user_ids:
                continue
            user_data = UserCreate(
                username=user['username'],
                email=user['email'] or '',
                first_name=user['first_name'] or '',
                last_name=user['last_name'] or '',
                is_superuser=_as_bool(user['is_superuser']),
                is_staff=_as_bool(user['is_staff']),
                is_active=_as_bool(user['is_active']),
                idm_data={},
                password=user['password'] or '!'
            )

            new_user = await get_user_by_username(new_db_session, user['username'])
            if new_user is None:
                await create_user_db(new_db_session, user_data)
                new_user = await get_user_by_username(new_db_session, user['username'])
            if new_user is None:
                print(f"  ✗ Failed to migrate user {user['username']}")
                continue

            user_id_mapping[user['id']] = str(new_user.id)

            user_updates = {
                "password": user_data.password,
                "username": user_data.username,
                "email": user_data.email,
                "first_name": user_data.first_name,
                "last_name": user_data.last_name,
                "is_superuser": user_data.is_superuser,
                "is_staff": user_data.is_staff,
                "is_active": user_data.is_active,
            }
            last_login = _as_datetime(user['last_login'])
            date_joined = _as_datetime(user['date_joined'])
            if last_login is not None:
                user_updates["last_login"] = last_login
            if date_joined is not None:
                user_updates["date_joined"] = date_joined

            await new_db_session.client.users.update_one(
                {"_id": ObjectId(new_user.id)},
                {"$set": user_updates},
            )

            legacy_permissions = [
                {"codename": codename}
                for codename in user_permissions.get(user["id"], [])
            ]
            if legacy_permissions:
                await new_db_session.client.users.update_one(
                    {"_id": ObjectId(new_user.id)},
                    {"$addToSet": {"user_permissions": {"$each": legacy_permissions}}},
                )

            # Migrate user preferences
            preferences = []
            if _table_exists(cursor, "wirecloud_platformpreference", db_type):
                cursor.execute(_adapt_sql_query("""
                    SELECT name, value
                    FROM wirecloud_platformpreference
                    WHERE user_id = %s
                """, db_type), (user['id'],))
                preferences = cursor.fetchall()

            if preferences:
                pref_list = [{"name": p['name'], "value": p['value'] or ""} for p in preferences]
                await new_db_session.client.users.update_one(
                    {"_id": ObjectId(new_user.id)},
                    {"$set": {"preferences": pref_list}}
                )

            await commit(new_db_session)

        async def add_memberships(group_id: ObjectId, user_ids: list[ObjectId]) -> None:
            if not user_ids:
                return
            await new_db_session.client.groups.update_one(
                {"_id": group_id},
                {"$addToSet": {"users": {"$each": user_ids}}},
            )
            await new_db_session.client.users.update_many(
                {"_id": {"$in": user_ids}},
                {"$addToSet": {"groups": group_id}},
            )

        # Organization groups contain all members in v2, while the new model reserves
        # root-group users for organization owners. Preserve direct members in a child
        # group so they inherit access without accidentally gaining owner privileges.
        organization_members: dict[int, list[ObjectId]] = {}
        if _table_exists(cursor, "auth_user_groups", db_type):
            cursor.execute("""
                SELECT user_id, group_id
                FROM auth_user_groups
                ORDER BY group_id, user_id
            """)
            for relation in cursor.fetchall():
                old_user_id = relation['user_id']
                old_group_id = relation['group_id']
                if old_user_id not in user_id_mapping or old_group_id not in group_id_mapping:
                    continue

                new_user_id = ObjectId(user_id_mapping[old_user_id])
                if old_group_id in organizations_by_group:
                    organization_members.setdefault(old_group_id, []).append(new_user_id)
                else:
                    await add_memberships(
                        ObjectId(group_id_mapping[old_group_id]),
                        [new_user_id],
                    )

        team_groups: dict[tuple[int, str], ObjectId] = {}
        organization_owners: dict[int, list[ObjectId]] = {}
        if _table_exists(cursor, "wirecloud_team", db_type):
            cursor.execute("""
                SELECT id, name, organization_id
                FROM wirecloud_team
                ORDER BY organization_id, id
            """)
            teams = cursor.fetchall()
            for team in teams:
                organization = organizations_by_id.get(team["organization_id"])
                if organization is None or organization["group_id"] not in group_id_mapping:
                    continue

                root_group_id = ObjectId(group_id_mapping[organization["group_id"]])
                root_group = await new_db_session.client.groups.find_one(
                    {"_id": root_group_id}, {"name": 1}
                )
                if root_group is None:
                    continue

                team_name = f"{root_group['name']}/{team['name']}"
                team_id = Id(str(ObjectId()))
                team_obj = Group(
                    _id=team_id,
                    name=team_name,
                    codename=_group_codename(team_name),
                    is_organization=True,
                    path=[root_group_id, team_id],
                )
                await create_group_if_not_exists(new_db_session, team_obj)
                new_team = await get_group_by_name(new_db_session, team_name)
                if new_team is None:
                    continue

                await new_db_session.client.groups.update_one(
                    {"_id": ObjectId(new_team.id)},
                    {"$set": {
                        "codename": team_obj.codename,
                        "is_organization": True,
                        "path": [root_group_id, ObjectId(new_team.id)],
                    }},
                )
                team_groups[(team["organization_id"], team["name"].lower())] = ObjectId(new_team.id)

                cursor.execute(_adapt_sql_query("""
                    SELECT user_id
                    FROM wirecloud_team_users
                    WHERE team_id = %s
                    ORDER BY user_id
                """, db_type), (team["id"],))
                team_user_ids = [
                    ObjectId(user_id_mapping[row["user_id"]])
                    for row in cursor.fetchall()
                    if row["user_id"] in user_id_mapping
                ]
                await add_memberships(ObjectId(new_team.id), team_user_ids)
                if team["name"].lower() == "owners":
                    organization_owners[organization["group_id"]] = team_user_ids

        for old_group_id, members in organization_members.items():
            organization = organizations_by_group[old_group_id]
            member_group_id = team_groups.get((organization["id"], "members"))
            if member_group_id is None:
                root_group_id = ObjectId(group_id_mapping[old_group_id])
                root_group = await new_db_session.client.groups.find_one(
                    {"_id": root_group_id}, {"name": 1}
                )
                if root_group is None:
                    continue
                member_name = f"{root_group['name']}/members"
                new_member_id = Id(str(ObjectId()))
                member_obj = Group(
                    _id=new_member_id,
                    name=member_name,
                    codename=_group_codename(member_name),
                    is_organization=True,
                    path=[root_group_id, new_member_id],
                )
                await create_group_if_not_exists(new_db_session, member_obj)
                member_group = await get_group_by_name(new_db_session, member_name)
                if member_group is None:
                    continue
                member_group_id = ObjectId(member_group.id)
                await new_db_session.client.groups.update_one(
                    {"_id": member_group_id},
                    {"$set": {
                        "codename": member_obj.codename,
                        "is_organization": True,
                        "path": [root_group_id, member_group_id],
                    }},
                )
            await add_memberships(member_group_id, members)

        for old_group_id, owners in organization_owners.items():
            root_group_id = ObjectId(group_id_mapping[old_group_id])
            await new_db_session.client.groups.update_one(
                {"_id": root_group_id},
                {"$set": {"users": owners}},
            )

        await commit(new_db_session)

    return user_id_mapping, group_id_mapping


async def _migrate_markets(db_connection, new_db_session, user_id_mapping: dict[int, str], db_type: str) -> int:
    migrated_count = 0
    with _db_cursor(db_connection) as cursor:
        cursor.execute(_adapt_sql_query("""
            SELECT name, public, options, user_id
            FROM wirecloud_market
            ORDER BY id
        """, db_type))
        markets = cursor.fetchall()

        for market in markets:
            if market['user_id'] not in user_id_mapping:
                print(f"  ⚠ Skipping market '{market['name']}' - owner not found")
                continue

            user_id = Id(user_id_mapping[market['user_id']])
            market_data = {
                "name": market['name'],
                "public": _as_bool(market['public']),
                "options": json.loads(market['options']) if market['options'] else {},
                "user_id": user_id,
            }

            await new_db_session.client.markets.update_one(
                {"name": market['name'], "user_id": user_id},
                {"$set": market_data, "$setOnInsert": {"_id": Id()}},
                upsert=True,
            )
            migrated_count += 1

    await commit(new_db_session)
    return migrated_count


async def _migrate_catalogue_resources(
    db_connection, new_db_session, http_session: aiohttp.ClientSession,
    old_url: str, token: str, user_id_mapping: dict[int, str],
    group_id_mapping: dict[int, str], db_type: str
) -> dict[int, str]:
    from wirecloud.catalogue.crud import create_catalogue_resource, get_catalogue_resource
    from wirecloud.catalogue.schemas import CatalogueResourceCreate, CatalogueResourceType
    from wirecloud.commons.auth.crud import get_user_by_id
    import settings

    resource_id_mapping = {}  # old_id -> new_id

    # Get catalogue media path from settings
    catalogue_media_path = Path(settings.CATALOGUE_MEDIA_ROOT) if hasattr(settings, 'CATALOGUE_MEDIA_ROOT') else Path('./catalogue/media')

    # Create catalogue media directory if it doesn't exist
    catalogue_media_path.mkdir(parents=True, exist_ok=True)

    with _db_cursor(db_connection) as cursor:
        # Get all catalogue resources
        cursor.execute(_adapt_sql_query("""
            SELECT cr.id, cr.vendor, cr.short_name, cr.version, cr.type,
                   cr.creation_date, cr.template_uri, cr.popularity,
                   cr.public, cr.creator_id, cr.json_description
            FROM catalogue_catalogueresource cr
            ORDER BY cr.creation_date
        """, db_type))
        resources = cursor.fetchall()

        for resource in resources:
            try:
                # Parse template description
                description_data = json.loads(resource['json_description']) if resource['json_description'] else {}
                resource_type = description_data.get('type', '')

                if resource_type == 'widget':
                    description = MACDWidget.model_validate(description_data)
                elif resource_type == 'operator':
                    description = MACDOperator.model_validate(description_data)
                elif resource_type == 'mashup':
                    description = MACDMashup.model_validate(description_data)
                else:
                    print(f"  ⚠ Unknown resource type for {resource['vendor']}/{resource['short_name']}/{resource['version']}, skipping.")
                    continue

                # Map creator
                creator = None
                if resource['creator_id'] and resource['creator_id'] in user_id_mapping:
                    creator_id = Id(user_id_mapping[resource['creator_id']])
                    creator = await get_user_by_id(new_db_session, creator_id)

                # Create resource
                resource_data = CatalogueResourceCreate(
                    vendor=resource['vendor'],
                    short_name=resource['short_name'],
                    version=resource['version'],
                    type=CatalogueResourceType(resource['type']),
                    public=resource['public'] if type(resource['public']) == bool else (str(resource['public']).lower() == "true" or str(resource['public']).lower() == "1"),
                    creation_date=_as_datetime(resource['creation_date']) or datetime.now(timezone.utc),
                    template_uri=resource['template_uri'],
                    popularity=float(resource['popularity'] or 0.0),
                    description=description,
                    creator=creator
                )

                new_resource = await get_catalogue_resource(
                    new_db_session,
                    resource_data.vendor,
                    resource_data.short_name,
                    resource_data.version,
                )
                if new_resource is None:
                    new_resource = await create_catalogue_resource(new_db_session, resource_data)
                resource_id_mapping[resource['id']] = str(new_resource.id)

                # Migrate resource-user relationships
                cursor.execute(_adapt_sql_query("""
                    SELECT user_id FROM catalogue_catalogueresource_users
                    WHERE catalogueresource_id = %s
                """, db_type), (resource['id'],))
                resource_users = cursor.fetchall()

                for ru in resource_users:
                    if ru['user_id'] in user_id_mapping:
                        await new_db_session.client.catalogue_resources.update_one(
                            {"_id": ObjectId(new_resource.id)},
                            {"$addToSet": {"users": ObjectId(user_id_mapping[ru['user_id']])}}
                        )

                # Migrate resource-group relationships
                cursor.execute(_adapt_sql_query("""
                    SELECT group_id FROM catalogue_catalogueresource_groups
                    WHERE catalogueresource_id = %s
                """, db_type), (resource['id'],))
                resource_groups = cursor.fetchall()

                for rg in resource_groups:
                    if rg['group_id'] in group_id_mapping:
                        await new_db_session.client.catalogue_resources.update_one(
                            {"_id": ObjectId(new_resource.id)},
                            {"$addToSet": {"groups": ObjectId(group_id_mapping[rg['group_id']])}}
                        )

                await commit(new_db_session)

                # Download and save widget/operator files via API, then deploy them
                try:
                    wgt_url = None
                    wgt_type = None
                    resource_info_url = (
                        f"{old_url.rstrip('/')}/api/resource/{resource['vendor']}/"
                        f"{resource['short_name']}/{resource['version']}/description"
                    )
                    async with http_session.get(resource_info_url) as resp:
                        if resp.status != 200:
                            print(f"  ✓ {resource['vendor']}/{resource['short_name']}/{resource['version']} (metadata only)")
                            continue

                        info = json.loads(await resp.text())
                        wgt_url = info['uriTemplate']
                        wgt_type = info['type']

                    # Download the WGT file from old instance
                    async with http_session.get(wgt_url) as resp:
                        if resp.status == 200:
                            wgt_bytes = await resp.read()

                            await add_packaged_resource(new_db_session, BytesIO(wgt_bytes), user=None, deploy_only=True)

                            # Deploy the widget/operator for use
                            try:
                                if wgt_type == "widget":
                                    await create_widget_on_resource_creation(new_db_session, new_resource)
                                elif wgt_type == "operator":
                                    deploy_operators_on_resource_creation(new_resource)

                                print(f"  ✓ {resource['vendor']}/{resource['short_name']}/{resource['version']} (downloaded & deployed)")
                            except Exception as deploy_error:
                                print(f"  ✓ {resource['vendor']}/{resource['short_name']}/{resource['version']} (downloaded, deployment failed: {deploy_error})")
                        else:
                            print(f"  ✓ {resource['vendor']}/{resource['short_name']}/{resource['version']} (metadata only)")
                except Exception as e:
                    print(f"  ✓ {resource['vendor']}/{resource['short_name']}/{resource['version']} (metadata only, download failed: {e})")

            except Exception as e:
                print(f"  ✗ Failed to migrate {resource['vendor']}/{resource['short_name']}/{resource['version']}: {e}")

    await commit(new_db_session)

    return resource_id_mapping


def _migrate_prop_users(field: dict[str, Any], user_id_mapping: dict[int, str]) -> None:
    for prop_name, prop_value in field.items():
        if not 'users' in prop_value:
            prop_value['users'] = {}

        new_users = {}
        for user_id, value in prop_value['users'].items():
            if int(user_id) in user_id_mapping:
                new_users[user_id_mapping[int(user_id)]] = value

        prop_value['users'] = new_users


def _migrate_prop_value_users(field: dict[str, Any], user_id_mapping: dict[int, str]) -> None:
    for prop_name, prop_value in field.items():
        if not 'value' in prop_value:
            prop_value['value'] = {}
        if not 'users' in prop_value['value']:
            prop_value['value']['users'] = {}

        new_users = {}
        for user_id, value in prop_value['value']['users'].items():
            if int(user_id) in user_id_mapping:
                new_users[user_id_mapping[int(user_id)]] = value

        prop_value['value']['users'] = new_users


def _migrate_screensizes_value(value: str) -> str:
    # Add a 'columns' entry (default 12) to every screen size that doesn't already have one
    try:
        screen_sizes = json.loads(value)
    except (TypeError, ValueError):
        return value

    if not isinstance(screen_sizes, list):
        return value

    changed = False
    for screen_size in screen_sizes:
        if isinstance(screen_size, dict) and 'columns' not in screen_size:
            screen_size['columns'] = 12
            changed = True

    return json.dumps(screen_sizes) if changed else value


def _migrate_preference_rows(rows: list[dict]) -> list[dict]:
    # Drop the removed 'baselayout'/'initiallayout' preferences. For 'screenSizes': drop it when
    # it is 'legacy default' (a single [0, +inf) interval, or missing) so the platform's new
    # responsive defaults apply; otherwise keep it and fix up its entries (add 'columns').
    pref_list = []
    for p in rows:
        name = p['name']
        if name in ('baselayout', 'initiallayout'):
            continue

        value = p['value'] or ""
        if name == 'screenSizes':
            if is_legacy_default_screen_sizes(value):
                continue
            value = _migrate_screensizes_value(value)

        pref_list.append({
            "name": name,
            "value": value,
            "inherit": p['inherit'] if type(p['inherit']) == bool else (str(p['inherit']).lower() == "true" or str(p['inherit']).lower() == "1")
        })

    return pref_list


def _tab_uses_legacy_default_screen_sizes(tab_prefs: list, workspace_prefs: list) -> bool:
    # Effective 'screenSizes' preference for a tab: its own value if present and not inherited,
    # else the workspace's value if present, else none. Returns whether that effective value is
    # 'legacy default' (see is_legacy_default_screen_sizes) -- in which case widget layouts
    # converted from the legacy position/rendering format must be remapped to the id of the new
    # default desktop screen size instead of reusing the old (now meaningless) screen size id.
    tab_pref = next((p for p in tab_prefs if p['name'] == 'screenSizes'), None)
    if tab_pref is not None and not _as_bool(tab_pref['inherit']):
        return is_legacy_default_screen_sizes(tab_pref['value'])

    workspace_pref = next((p for p in workspace_prefs if p['name'] == 'screenSizes'), None)
    if workspace_pref is not None:
        return is_legacy_default_screen_sizes(workspace_pref['value'])

    return True


def _migrate_widget_positions_to_layouts(positions: dict, legacy_default_screen_sizes: bool) -> dict[str, dict]:
    # Convert the old 'positions.configurations' structure into the new 'layouts' dict, using the
    # best-effort legacy grid conversion rule (old grid: 20 columns x 12px rows; new grid: 12 columns x 40px rows).
    # When the tab's effective screenSizes preference is 'legacy default' (the old single
    # "Default" screen size covering everything), the converted (12-column-targeted) layout is
    # keyed to the new default desktop screen size instead of the old screen size id, which no
    # longer refers to a 12-column screen size under the new responsive defaults.
    layouts = {}
    desktop_key = str(default_desktop_screen_size_id()) if legacy_default_screen_sizes else None
    for conf in positions.get('configurations', []):
        widget_conf = conf.get('widget', {}) or {}
        key = desktop_key if legacy_default_screen_sizes else str(conf.get('id', 0))
        layouts[key] = convert_legacy_layout(
            top=float(widget_conf.get('top', 0) or 0),
            left=float(widget_conf.get('left', 0) or 0),
            width=float(widget_conf.get('width', 10) or 10),
            height=float(widget_conf.get('height', 10) or 10),
            relx=bool(widget_conf.get('relx', True)),
            rely=bool(widget_conf.get('rely', False)),
            relwidth=bool(widget_conf.get('relwidth', True)),
            relheight=bool(widget_conf.get('relheight', False)),
            minimized=bool(widget_conf.get('minimized', False)),
            titlevisible=bool(widget_conf.get('titlevisible', True)),
            fulldragboard=bool(widget_conf.get('fulldragboard', False)),
        )

    return layouts


async def _migrate_workspaces(
    db_connection, new_db_session, http_session: aiohttp.ClientSession,
    old_url: str, token: str, user_id_mapping: dict[int, str],
    group_id_mapping: dict[int, str], resource_mapping: dict[int, str], db_type: str
) -> int:
    from wirecloud.platform.workspace.crud import create_empty_workspace
    from wirecloud.platform.workspace.utils import create_tab
    from wirecloud.commons.auth.crud import get_user_by_id
    from wirecloud.platform.iwidget.models import WidgetInstance

    workspace_count = 0

    with _db_cursor(db_connection) as cursor:
        # Get all workspaces
        forced_values_column = _sql_identifier("forcedValues", db_type)
        wiring_status_column = _sql_identifier("wiringStatus", db_type)
        cursor.execute(_adapt_sql_query(f"""
            SELECT w.id, w.name, w.title, w.creation_date, w.creator_id, w.last_modified,
                   w.description, w.longdescription, w.public, w.searchable,
                   w.requireauth, w.{forced_values_column} AS forced_values,
                   w.{wiring_status_column} AS wiring_status
            FROM wirecloud_workspace w
            ORDER BY w.creation_date
        """, db_type))
        workspaces = cursor.fetchall()

        for workspace in workspaces:
            try:
                iwidget_mapping = {}  # old_iwidget_id -> new_iwidget_id (for wiring migration)

                # Map creator
                if workspace['creator_id'] not in user_id_mapping:
                    print(f"  ⚠ Skipping workspace '{workspace['name']}' - creator not found")
                    continue

                creator_id = Id(user_id_mapping[workspace['creator_id']])
                creator = await get_user_by_id(new_db_session, creator_id)
                if not creator:
                    continue

                # Create workspace
                new_workspace = await create_empty_workspace(
                    new_db_session,
                    title=workspace['title'],
                    user=creator,
                    name=workspace['name'],
                    translate=False
                )

                if new_workspace is None:
                    print(f"  ⚠ Could not create workspace '{workspace['name']}' - name conflict")
                    continue

                new_workspace.creation_date = (
                    _as_datetime(workspace['creation_date']) or datetime.now(timezone.utc)
                )
                legacy_last_modified = (
                    _as_datetime(workspace['last_modified']) or new_workspace.creation_date
                )
                new_workspace.last_modified = legacy_last_modified

                new_workspace.description = workspace['description'] or ''
                new_workspace.longdescription = workspace['longdescription'] or ''
                new_workspace.public = _as_bool(workspace['public'])
                new_workspace.searchable = _as_bool(workspace['searchable'])
                new_workspace.requireauth = _as_bool(workspace['requireauth'])

                # Update workspace metadata
                await new_db_session.client.workspaces.update_one(
                    {"_id": ObjectId(new_workspace.id)},
                    {"$set": {
                        "description": new_workspace.description,
                        "longdescription": new_workspace.longdescription,
                        "public": new_workspace.public,
                        "searchable": new_workspace.searchable,
                        "requireauth": new_workspace.requireauth,
                        "creation_date": new_workspace.creation_date,
                        "last_modified": new_workspace.last_modified
                    }}
                )

                # Migrate workspace user permissions
                cursor.execute(_adapt_sql_query("""
                    SELECT user_id, accesslevel
                    FROM wirecloud_userworkspace
                    WHERE workspace_id = %s
                """, db_type), (workspace['id'],))
                workspace_users = cursor.fetchall()

                for wu in workspace_users:
                    if int(wu['user_id']) in user_id_mapping:
                        user_perm = {
                            "id": ObjectId(user_id_mapping[int(wu['user_id'])]),
                            "accesslevel": wu['accesslevel'] or 1
                        }

                        new_workspace.users.append(WorkspaceAccessPermissions(**user_perm))

                        await new_db_session.client.workspaces.update_one(
                            {"_id": ObjectId(new_workspace.id)},
                            {"$addToSet": {"users": user_perm}}
                        )

                # Migrate workspace group permissions (if groups exist in old system)
                table_name = 'wirecloud_groupworkspace' if _table_exists(cursor, 'wirecloud_groupworkspace', db_type) else 'wirecloud_workspace_groups'
                column_name = None if table_name == 'wirecloud_workspace_groups' else 'accesslevel'

                cursor.execute(_adapt_sql_query(f"""
                    SELECT group_id{', ' + column_name if column_name else ''}
                    FROM {table_name}
                    WHERE workspace_id = %s
                """, db_type), (workspace['id'],))
                workspace_groups = cursor.fetchall()

                for wg in workspace_groups:
                    if wg['group_id'] in group_id_mapping:
                        group_perm = {
                            "id": ObjectId(group_id_mapping[wg['group_id']]),
                            "accesslevel": (wg[column_name] or 1) if column_name else 1
                        }

                        new_workspace.groups.append(WorkspaceAccessPermissions(**group_perm))

                        await new_db_session.client.workspaces.update_one(
                            {"_id": ObjectId(new_workspace.id)},
                            {"$addToSet": {"groups": group_perm}}
                        )

                # Migrate workspace preferences
                cursor.execute(_adapt_sql_query("""
                    SELECT name, value, inherit
                    FROM wirecloud_workspacepreference
                    WHERE workspace_id = %s
                """, db_type), (workspace['id'],))
                workspace_prefs = cursor.fetchall()

                if workspace_prefs:
                    pref_list = _migrate_preference_rows(workspace_prefs)

                    for pref in pref_list:
                        new_workspace.preferences.append(DBWorkspacePreference(**pref))

                    await new_db_session.client.workspaces.update_one(
                        {"_id": ObjectId(new_workspace.id)},
                        {"$set": {"preferences": pref_list}}
                    )

                # Migrate tabs
                cursor.execute(_adapt_sql_query("""
                    SELECT id, name, title, visible, position
                    FROM wirecloud_tab
                    WHERE workspace_id = %s
                    ORDER BY position
                """, db_type), (workspace['id'],))
                tabs = cursor.fetchall()

                # Remove default tab if we have tabs to migrate
                if tabs:
                    new_workspace.tabs.clear()

                old_tab_id_to_new = {}  # Mapping for widget migration

                for tab_data in tabs:
                    tab = await create_tab(
                        new_db_session,
                        creator,
                        tab_data['title'],
                        new_workspace,
                        name=tab_data['name']
                    )

                    old_tab_id_to_new[tab_data['id']] = tab.id

                    tab.visible = tab_data['visible'] if type(tab_data['visible']) == bool else (str(tab_data['visible']).lower() == "true" or str(tab_data['visible']).lower() == "1")
                    await new_db_session.client.workspaces.update_one(
                        {"_id": ObjectId(new_workspace.id)},
                        {"$set": {f"tabs.{tab.id}.visible": tab.visible}}
                    )

                    # Migrate tab preferences
                    cursor.execute(_adapt_sql_query("""
                        SELECT name, value, inherit
                        FROM wirecloud_tabpreference
                        WHERE tab_id = %s
                    """, db_type), (tab_data['id'],))
                    tab_prefs = cursor.fetchall()
                    tab_legacy_default_screen_sizes = _tab_uses_legacy_default_screen_sizes(tab_prefs, workspace_prefs)

                    if tab_prefs:
                        pref_list = _migrate_preference_rows(tab_prefs)

                        for pref in pref_list:
                            tab.preferences.append(DBWorkspacePreference(**pref))

                        await new_db_session.client.workspaces.update_one(
                            {"_id": ObjectId(new_workspace.id)},
                            {"$set": {f"tabs.{tab.id}.preferences": pref_list}}
                        )

                    # Migrate widget instances (IWidgets)
                    read_only_column = _sql_identifier("readOnly", db_type)
                    cursor.execute(_adapt_sql_query(f"""
                        SELECT iw.id, iw.name, iw.widget_uri,
                            iw.positions, iw.{read_only_column} AS read_only,
                            iw.variables, iw.permissions,
                            w.resource_id
                        FROM wirecloud_iwidget iw JOIN wirecloud_widget w ON iw.widget_id = w.id
                        WHERE iw.tab_id = %s
                    """, db_type), (tab_data['id'],))
                    iwidgets = cursor.fetchall()

                    iwidget_id = 0

                    for iwidget in iwidgets:
                        new_resource_id = resource_mapping.get(iwidget['resource_id'])
                        if not new_resource_id:
                            print(f"    ⚠ Skipping widget instance '{iwidget['name']}' - resource not found")
                            continue

                        # Fix variables ids
                        variables = json.loads(iwidget['variables']) if iwidget['variables'] else {}
                        _migrate_prop_users(variables, user_id_mapping)

                        # Fix old positions
                        positions = json.loads(iwidget['positions']) if iwidget['positions'] else {}
                        if not 'configurations' in positions:
                            new_positions = {}

                            if not 'widget' in positions:
                                print(f"    ⚠ Widget instance '{iwidget['name']}' has no position information, skipping")
                                continue

                            new_positions["configurations"] = []
                            new_positions["configurations"].append({
                                "id": 0,
                                "moreOrEqual": 0,
                                "lessOrEqual": -1,
                                "widget": {
                                    "id": 0,
                                    "top": int(positions['widget']['top']) if 'top' in positions['widget'] else 0,
                                    "left": int(positions['widget']['left']) if 'left' in positions['widget'] else 0,
                                    "zIndex": int(positions['widget']['zIndex']) if 'zIndex' in positions['widget'] else 0,
                                    "height": int(positions['widget']['height']) if 'height' in positions['widget'] else 10,
                                    "width": int(positions['widget']['width']) if 'width' in positions['widget'] else 10,
                                    "minimized": positions['widget']['minimized'] if 'minimized' in positions['widget'] else False,
                                    "titlevisible": positions['widget']['titlevisible'] if 'titlevisible' in positions['widget'] else True,
                                    "fulldragboard": positions['widget']['fulldragboard'] if 'fulldragboard' in positions['widget'] else False,
                                    "relx": positions['widget']['relx'] if 'relx' in positions['widget'] else True,
                                    "rely": positions['widget']['rely'] if 'rely' in positions['widget'] else False,
                                    "relwidth": positions['widget']['relwidth'] if 'relwidth' in positions['widget'] else True,
                                    "relheight": positions['widget']['relheight'] if 'relheight' in positions['widget'] else False,
                                    "anchor": positions['widget']['anchor'] if 'anchor' in positions['widget'] else "top-left",
                                }
                            })

                            positions = new_positions

                        # Convert positions.configurations into the new layouts format
                        layouts = _migrate_widget_positions_to_layouts(positions, tab_legacy_default_screen_sizes)

                        # Fix permissions
                        permissions = json.loads(iwidget['permissions']) if iwidget['permissions'] else {}
                        if not 'viewer' in permissions:
                            permissions['viewer'] = {}

                        if not 'editor' in permissions:
                            permissions['editor'] = {}

                        # Create widget instance structure
                        widget_instance = {
                            "id": f"{tab.id}-{str(iwidget_id)}",
                            "resource": ObjectId(new_resource_id),
                            "widget_uri": iwidget['widget_uri'],
                            "title": iwidget['name'],
                            "read_only": _as_bool(iwidget['read_only']),
                            "variables": variables,
                            "layouts": layouts,
                            "permissions": permissions
                        }

                        iwidget_mapping[iwidget['id']] = widget_instance['id']

                        iwidget_id += 1

                        # Keep the in-memory model synchronized. Creating a later tab
                        # replaces the whole workspace document and would otherwise
                        # discard widgets written only through the field update below.
                        tab.widgets[widget_instance['id']] = WidgetInstance.model_validate(widget_instance)

                        # Add widget to tab
                        await new_db_session.client.workspaces.update_one(
                            {"_id": ObjectId(new_workspace.id)},
                            {"$set": {f"tabs.{tab.id}.widgets.{widget_instance['id']}": widget_instance}}
                        )

                # Migrate workspace forced values after widget IDs are known.
                try:
                    forced_values = json.loads(workspace['forced_values']) if workspace['forced_values'] else {}
                    migrated_widget_values = {}
                    for old_widget_id, values in forced_values.get("iwidget", {}).items():
                        try:
                            new_widget_id = iwidget_mapping.get(int(old_widget_id), old_widget_id)
                        except (TypeError, ValueError):
                            new_widget_id = old_widget_id
                        migrated_widget_values[str(new_widget_id)] = values

                    migrated_forced_values = {
                        "extra_prefs": forced_values.get("extra_prefs", []),
                        "operator": forced_values.get("ioperator", {}),
                        "widget": migrated_widget_values,
                        "empty_params": [],
                    }
                    new_workspace.forced_values = new_workspace.forced_values.model_validate(
                        migrated_forced_values
                    )
                    await new_db_session.client.workspaces.update_one(
                        {"_id": ObjectId(new_workspace.id)},
                        {"$set": {"forced_values": new_workspace.forced_values.model_dump()}},
                    )
                except Exception as e:
                    print(f"    ⚠ Could not migrate forced values: {e}")

                # Migrate wiring configuration
                try:
                    wiring_status = json.loads(workspace['wiring_status']) if workspace['wiring_status'] else {}

                    if not 'version' in wiring_status or wiring_status['version'] != '2.0':
                        print(f"    ⚠ Unsupported wiring configuration version for workspace '{workspace['name']}', skipping wiring migration")
                    else:
                        if not 'connections' in wiring_status:
                            wiring_status['connections'] = []

                        for connection in wiring_status['connections']:
                            if connection['source']['type'] == 'widget':
                                connection['source']['id'] = iwidget_mapping.get(int(connection['source']['id'])) or connection['source']['id']
                            if connection['target']['type'] == 'widget':
                                connection['target']['id'] = iwidget_mapping.get(int(connection['target']['id'])) or connection['target']['id']

                        if not 'operators' in wiring_status:
                            wiring_status['operators'] = {}

                        for operator_id, operator in wiring_status['operators'].items():
                            _migrate_prop_value_users(operator['preferences'], user_id_mapping)
                            _migrate_prop_value_users(operator['properties'], user_id_mapping)

                        if not 'visualdescription' in wiring_status:
                            wiring_status['visualdescription'] = {}

                        if not 'behaviours' in wiring_status['visualdescription']:
                            wiring_status['visualdescription']['behaviours'] = []

                        if not 'components' in wiring_status['visualdescription']:
                            wiring_status['visualdescription']['components'] = {}

                        if not 'connections' in wiring_status['visualdescription']:
                            wiring_status['visualdescription']['connections'] = []

                        for behaviour in wiring_status['visualdescription']['behaviours']:
                            if 'widget' not in behaviour['components']:
                                behaviour['components']['widget'] = {}

                            if 'operator' not in behaviour['components']:
                                behaviour['components']['operator'] = {}

                            new_behaviour_widgets = {}

                            for widget_id, widget_data in behaviour['components']['widget'].items():
                                new_behaviour_widgets[iwidget_mapping.get(int(widget_id)) or widget_id] = widget_data

                            behaviour['components']['widget'] = new_behaviour_widgets

                        if 'operator' not in wiring_status['visualdescription']['components']:
                            wiring_status['visualdescription']['components']['operator'] = {}

                        if 'widget' not in wiring_status['visualdescription']['components']:
                            wiring_status['visualdescription']['components']['widget'] = {}

                        new_components_widgets = {}
                        for widget_id, widget_data in wiring_status['visualdescription']['components']['widget'].items():
                            new_components_widgets[iwidget_mapping.get(int(widget_id)) or widget_id] = widget_data

                        wiring_status['visualdescription']['components']['widget'] = new_components_widgets

                        for connection in wiring_status['visualdescription']['connections']:
                            sourcename_parts = connection['sourcename'].split('/')
                            if len(sourcename_parts) == 3 and sourcename_parts[0] == 'widget':
                                connection['sourcename'] = f"widget/{iwidget_mapping.get(int(sourcename_parts[1])) or sourcename_parts[1]}/{sourcename_parts[2]}"

                            targetname_parts = connection['targetname'].split('/')
                            if len(targetname_parts) == 3 and targetname_parts[0] == 'widget':
                                connection['targetname'] = f"widget/{iwidget_mapping.get(int(targetname_parts[1])) or targetname_parts[1]}/{targetname_parts[2]}"

                        await new_db_session.client.workspaces.update_one(
                            {"_id": ObjectId(new_workspace.id)},
                            {"$set": {"wiring_status": wiring_status}}
                        )
                except Exception as e:
                    print(f"    ⚠ Could not migrate wiring configuration: {e}")

                # Tab creation updates last_modified; restore the v2 timestamp once
                # the workspace has been fully reconstructed.
                new_workspace.last_modified = legacy_last_modified
                await new_db_session.client.workspaces.update_one(
                    {"_id": ObjectId(new_workspace.id)},
                    {"$set": {"last_modified": new_workspace.last_modified}},
                )

                await commit(new_db_session)
                workspace_count += 1
                print(f"  ✓ {workspace['name']}")

            except Exception as e:
                print(f"  ✗ Failed to migrate workspace '{workspace.get('name', '?')}': {e}")
                traceback.print_exc()

    return workspace_count


def setup_commands(subparsers: argparse._SubParsersAction) -> dict[str, Callable]:
    createsuperuser = subparsers.add_parser(
        "createsuperuser",
        help="Create a superuser account"
    )
    createsuperuser.add_argument(
        "--username",
        default=None,
        help="Username for the superuser (prompted if not provided)"
    )
    createsuperuser.add_argument(
        "--email",
        default=None,
        help="Email address for the superuser (optional)"
    )
    createsuperuser.add_argument(
        "--password",
        default=None,
        help="Password for the superuser (prompted if not provided)"
    )

    migrate = subparsers.add_parser(
        "migrate",
        help="Migrate data from old Wirecloud instance (Django/SQL) to new version (FastAPI/MongoDB)"
    )

    # Connection parameters
    migrate.add_argument(
        "-u", "--url",
        required=True,
        help="URL of the old Wirecloud instance (e.g., http://localhost:8000)"
    )
    migrate.add_argument(
        "--admin-user",
        required=True,
        help="Admin username for the old Wirecloud instance"
    )
    migrate.add_argument(
        "--admin-password",
        required=True,
        help="Admin password for the old Wirecloud instance"
    )

    # Database parameters
    migrate.add_argument(
        "--db-type",
        choices=['mysql', 'postgresql', 'sqlite'],
        default='mysql',
        help="Database type: mysql, postgresql, or sqlite (default: mysql)"
    )
    migrate.add_argument(
        "--db-host",
        default="localhost",
        help="Database host (default: localhost). Not used for SQLite."
    )
    migrate.add_argument(
        "--db-port",
        type=int,
        default=None,
        help="Database port (default: 3306 for MySQL, 5432 for PostgreSQL). Not used for SQLite."
    )
    migrate.add_argument(
        "--db-name",
        required=True,
        help="Database name (for SQLite, this is the path to the .db file)"
    )
    migrate.add_argument(
        "--db-user",
        default=None,
        help="Database username. Not used for SQLite."
    )
    migrate.add_argument(
        "--db-password",
        default=None,
        help="Database password. Not used for SQLite."
    )


    # Options
    migrate.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL certificate verification"
    )
    migrate.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )

    subparsers.add_parser(
        "convert_layouts",
        help="Convert workspace documents still using the old 'positions'/'layout' widget fields into "
             "the new 'layouts' format (idempotent, safe to run more than once)"
    )

    return {
        "createsuperuser": createsuperuser_cmd,
        "migrate": migrate_cmd,
        "convert_layouts": convert_layouts_cmd
    }
