import json
from datetime import datetime, timezone
from types import SimpleNamespace
import sqlite3

from bson import ObjectId

from wirecloud.commons import commands


def _legacy_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE auth_group (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE auth_user (
            id INTEGER PRIMARY KEY,
            password TEXT,
            last_login,
            is_superuser,
            username TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            is_staff,
            is_active,
            date_joined
        );
        CREATE TABLE auth_user_groups (id INTEGER PRIMARY KEY, user_id INTEGER, group_id INTEGER);
        CREATE TABLE django_content_type (
            id INTEGER PRIMARY KEY, app_label TEXT NOT NULL, model TEXT NOT NULL
        );
        CREATE TABLE auth_permission (
            id INTEGER PRIMARY KEY, name TEXT, content_type_id INTEGER, codename TEXT NOT NULL
        );
        CREATE TABLE auth_user_user_permissions (
            id INTEGER PRIMARY KEY, user_id INTEGER, permission_id INTEGER
        );
        CREATE TABLE auth_group_permissions (
            id INTEGER PRIMARY KEY, group_id INTEGER, permission_id INTEGER
        );
        CREATE TABLE wirecloud_organization (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, group_id INTEGER NOT NULL
        );
        CREATE TABLE wirecloud_team (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, organization_id INTEGER NOT NULL
        );
        CREATE TABLE wirecloud_team_users (
            id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, user_id INTEGER NOT NULL
        );
        CREATE TABLE wirecloud_platformpreference (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, value TEXT, user_id INTEGER NOT NULL
        );

        INSERT INTO auth_group VALUES (1, 'Acme'), (2, 'Editors');
        INSERT INTO auth_user VALUES
            (1, 'hash-a', '2024-03-01 12:30:00', 0, 'alice', 'Alice', 'Owner',
             'alice@example.com', 0, 1, 1700000000000),
            (2, 'hash-b', NULL, 0, 'bob', 'Bob', 'Member',
             'bob@example.com', 0, 1, '2024-01-02T03:04:05Z'),
            (3, '!', NULL, 0, 'acme', '', '', '', 0, 1, '2024-01-01 00:00:00');
        INSERT INTO auth_user_groups VALUES (1, 1, 2), (2, 2, 1);
        INSERT INTO wirecloud_organization VALUES (10, 3, 1);
        INSERT INTO wirecloud_team VALUES (20, 'owners', 10), (21, 'developers', 10);
        INSERT INTO wirecloud_team_users VALUES (1, 20, 1), (2, 21, 2);
        INSERT INTO wirecloud_platformpreference VALUES (1, 'theme', 'dark', 1);

        INSERT INTO django_content_type VALUES
            (1, 'auth', 'user'),
            (2, 'platform', 'workspace'),
            (3, 'custom', 'thing');
        INSERT INTO auth_permission VALUES
            (1, 'Can add user', 1, 'add_user'),
            (2, 'Can change workspace', 2, 'change_workspace'),
            (3, 'Can frobnicate thing', 3, 'frobnicate_thing');
        INSERT INTO auth_user_user_permissions VALUES (1, 1, 1), (2, 1, 3);
        INSERT INTO auth_group_permissions VALUES (1, 2, 2);
        """
    )
    return connection


async def test_migrate_users_groups_organizations_teams_and_permissions(db_session):
    await db_session.client.users.delete_many({})
    await db_session.client.groups.delete_many({})
    legacy = _legacy_database()

    try:
        user_mapping, group_mapping = await commands._migrate_users_and_groups(
            legacy, db_session, "sqlite"
        )

        assert set(user_mapping) == {1, 2}
        assert set(group_mapping) == {1, 2}
        assert await db_session.client.users.find_one({"username": "acme"}) is None

        root = await db_session.client.groups.find_one({"name": "Acme"})
        owners = await db_session.client.groups.find_one({"name": "Acme/owners"})
        developers = await db_session.client.groups.find_one({"name": "Acme/developers"})
        members = await db_session.client.groups.find_one({"name": "Acme/members"})
        editors = await db_session.client.groups.find_one({"name": "Editors"})

        assert root["is_organization"] is True
        assert root["path"] == [root["_id"]]
        assert owners["path"] == [root["_id"], owners["_id"]]
        assert developers["path"] == [root["_id"], developers["_id"]]
        assert members["path"] == [root["_id"], members["_id"]]
        assert {permission["codename"] for permission in editors["group_permissions"]} == {
            "WORKSPACE.*"
        }

        alice_id = ObjectId(user_mapping[1])
        bob_id = ObjectId(user_mapping[2])
        assert root["users"] == [alice_id]
        assert owners["users"] == [alice_id]
        assert developers["users"] == [bob_id]
        assert members["users"] == [bob_id]

        alice = await db_session.client.users.find_one({"_id": alice_id})
        bob = await db_session.client.users.find_one({"_id": bob_id})
        assert {permission["codename"] for permission in alice["user_permissions"]} >= {
            "USER.CREATE",
            "custom.frobnicate_thing",
        }
        assert editors["_id"] in alice["groups"]
        assert owners["_id"] in alice["groups"]
        assert developers["_id"] in bob["groups"]
        assert members["_id"] in bob["groups"]
        assert alice["preferences"] == [{"name": "theme", "value": "dark"}]
        assert isinstance(alice["date_joined"], datetime)
        # BSON normalizes datetimes to naive UTC on retrieval.
        assert alice["date_joined"].replace(tzinfo=timezone.utc).timestamp() == 1700000000
        assert bob["date_joined"].year == 2024

        # Re-running the migration reuses deterministic user/group identities.
        second_user_mapping, second_group_mapping = await commands._migrate_users_and_groups(
            legacy, db_session, "sqlite"
        )
        assert second_user_mapping == user_mapping
        assert second_group_mapping == group_mapping
        assert await db_session.client.users.count_documents({"username": "alice"}) == 1
        assert await db_session.client.groups.count_documents({"name": "Acme/owners"}) == 1
    finally:
        legacy.close()


def test_migration_value_normalizers():
    assert commands._as_bool(True) is True
    assert commands._as_bool("yes") is True
    assert commands._as_bool("0") is False
    assert commands._as_datetime(None) is None
    assert commands._as_datetime(1700000000000).tzinfo == timezone.utc
    assert commands._as_datetime("2024-01-02T03:04:05Z").tzinfo == timezone.utc


def test_migrate_screensizes_value():
    # Adds 'columns': 12 only to entries lacking it
    value = json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1, "name": "Default"}])
    updated = commands._migrate_screensizes_value(value)
    assert json.loads(updated) == [{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1, "name": "Default", "columns": 12}]

    # An entry that already has 'columns' is left untouched
    already = json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1, "columns": 6}])
    assert commands._migrate_screensizes_value(already) == already

    # Non-JSON / non-list values are returned unchanged
    assert commands._migrate_screensizes_value("not json") == "not json"
    assert commands._migrate_screensizes_value(json.dumps({"a": 1})) == json.dumps({"a": 1})


def test_migrate_preference_rows():
    # A 'legacy default' screenSizes value (a single [0, +inf) interval, regardless of its
    # name/id) is dropped entirely so the new responsive defaults apply
    rows = [
        {"name": "baselayout", "value": "x", "inherit": False},
        {"name": "initiallayout", "value": "y", "inherit": "true"},
        {"name": "screenSizes", "value": json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}]), "inherit": 0},
        {"name": "requireauth", "value": "false", "inherit": False},
    ]
    migrated = commands._migrate_preference_rows(rows)
    names = {p["name"] for p in migrated}
    assert names == {"requireauth"}

    require_auth_pref = next(p for p in migrated if p["name"] == "requireauth")
    assert require_auth_pref["inherit"] is False
    assert require_auth_pref["value"] == "false"

    # A real, custom multi-interval screenSizes preference is kept, with its ids untouched and
    # 'columns' added to entries lacking it
    custom_rows = [
        {
            "name": "screenSizes",
            "value": json.dumps([
                {"id": 5, "moreOrEqual": 0, "lessOrEqual": 599},
                {"id": 9, "moreOrEqual": 600, "lessOrEqual": -1, "columns": 8},
            ]),
            "inherit": False,
        },
    ]
    migrated_custom = commands._migrate_preference_rows(custom_rows)
    assert len(migrated_custom) == 1
    custom_value = json.loads(migrated_custom[0]["value"])
    assert [entry["id"] for entry in custom_value] == [5, 9]
    assert custom_value[0]["columns"] == 12
    assert custom_value[1]["columns"] == 8


def test_tab_uses_legacy_default_screen_sizes():
    legacy_default_pref = {"name": "screenSizes", "value": json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}]), "inherit": False}
    custom_pref = {"name": "screenSizes", "value": json.dumps([
        {"id": 0, "moreOrEqual": 0, "lessOrEqual": 599},
        {"id": 1, "moreOrEqual": 600, "lessOrEqual": -1},
    ]), "inherit": False}
    inherited_pref = {"name": "screenSizes", "value": json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}]), "inherit": True}

    # Tab has its own non-inherited value -> that value decides, regardless of the workspace's
    assert commands._tab_uses_legacy_default_screen_sizes([legacy_default_pref], [custom_pref]) is True
    assert commands._tab_uses_legacy_default_screen_sizes([custom_pref], [legacy_default_pref]) is False

    # Tab's own value is inherited (or absent) -> falls back to the workspace's value
    assert commands._tab_uses_legacy_default_screen_sizes([inherited_pref], [custom_pref]) is False
    assert commands._tab_uses_legacy_default_screen_sizes([], [custom_pref]) is False
    assert commands._tab_uses_legacy_default_screen_sizes([], [legacy_default_pref]) is True

    # Neither tab nor workspace has a screenSizes preference -> legacy default
    assert commands._tab_uses_legacy_default_screen_sizes([], []) is True


def test_migrate_widget_positions_to_layouts():
    positions = {
        "configurations": [
            {
                "id": 0,
                "widget": {
                    "top": 8, "left": 10, "width": 6, "height": 4,
                    "relx": True, "rely": True, "relwidth": True, "relheight": True,
                    "minimized": False, "titlevisible": True, "fulldragboard": False,
                },
            },
            {
                "id": 2,
                "widget": {
                    "top": 80, "left": 250, "width": 250, "height": 80,
                    "relx": False, "rely": False, "relwidth": False, "relheight": False,
                    "minimized": True, "titlevisible": False, "fulldragboard": True,
                },
            },
        ]
    }

    # Custom (non-legacy-default) screenSizes: original config ids are kept as layout keys
    layouts = commands._migrate_widget_positions_to_layouts(positions, legacy_default_screen_sizes=False)
    assert set(layouts) == {"0", "2"}
    assert layouts["0"]["x"] == round(10 * 12 / 20)
    assert layouts["0"]["minimized"] is False
    assert layouts["2"]["x"] is None
    assert layouts["2"]["minimized"] is True
    assert layouts["2"]["fulldragboard"] is True

    # Legacy default screenSizes: the converted (12-column-targeted) layout is remapped to the
    # id of the platform's new default desktop screen size, not the old config id
    desktop_id = str(commands.default_desktop_screen_size_id())
    legacy_layouts = commands._migrate_widget_positions_to_layouts(positions, legacy_default_screen_sizes=True)
    # Both old configurations collapse onto the single desktop-screen-size key (last one wins),
    # instead of being kept under their old (now meaningless) ids
    assert set(legacy_layouts) == {desktop_id}
    assert legacy_layouts[desktop_id]["minimized"] is True  # from the second (last) configuration

    # Missing/empty positions produce no layouts
    assert commands._migrate_widget_positions_to_layouts({}, legacy_default_screen_sizes=False) == {}
    assert commands._migrate_widget_positions_to_layouts({}, legacy_default_screen_sizes=True) == {}


def test_convert_legacy_preferences():
    rows = [
        {"name": "baselayout", "value": "x", "inherit": False},
        {"name": "screenSizes", "value": json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}]), "inherit": True},
        {"name": "public", "value": "false", "inherit": False},
    ]
    new_rows, changed = commands._convert_legacy_preferences(rows)
    assert changed is True
    assert {p["name"] for p in new_rows} == {"public"}

    unchanged_rows = [{"name": "public", "value": "false", "inherit": False}]
    result, changed2 = commands._convert_legacy_preferences(unchanged_rows)
    assert changed2 is False
    assert result == unchanged_rows

    # A real, custom multi-interval screenSizes preference is kept and gets 'columns' added
    custom_rows = [
        {"name": "screenSizes", "value": json.dumps([
            {"id": 0, "moreOrEqual": 0, "lessOrEqual": 599},
            {"id": 1, "moreOrEqual": 600, "lessOrEqual": -1},
        ]), "inherit": False},
    ]
    new_custom_rows, changed3 = commands._convert_legacy_preferences(custom_rows)
    assert changed3 is True
    assert {p["name"] for p in new_custom_rows} == {"screenSizes"}
    custom_value = json.loads(new_custom_rows[0]["value"])
    assert [entry["id"] for entry in custom_value] == [0, 1]
    assert all(entry["columns"] == 12 for entry in custom_value)


async def test_convert_layouts_cmd_migrates_and_is_idempotent(monkeypatch, db_session):
    async def _get_session():
        yield db_session

    monkeypatch.setattr(commands, "get_session", _get_session)

    workspace_id = ObjectId()
    desktop_id = str(commands.default_desktop_screen_size_id())
    doc = {
        "_id": workspace_id,
        "name": "ws",
        "preferences": [
            {"name": "baselayout", "value": "x", "inherit": False},
            # Legacy default (single [0, +inf) interval): should be dropped
            {"name": "screenSizes", "value": json.dumps([{"id": 0, "moreOrEqual": 0, "lessOrEqual": -1}]), "inherit": False},
            {"name": "public", "value": "false", "inherit": False},
        ],
        "tabs": {
            # tab-0 has no screenSizes of its own -> falls back to the workspace's (legacy
            # default) one -> its widget's converted layout is remapped to the desktop screen size
            "tab-0": {
                "id": "tab-0",
                "preferences": [
                    {"name": "initiallayout", "value": "y", "inherit": True},
                ],
                "widgets": {
                    "tab-0-0": {
                        "id": "tab-0-0",
                        "layout": 0,
                        "positions": {
                            "configurations": [
                                {
                                    "id": 0,
                                    "widget": {
                                        "top": 8, "left": 10, "width": 6, "height": 4,
                                        "relx": True, "rely": True, "relwidth": True, "relheight": True,
                                    },
                                }
                            ]
                        },
                    },
                    "tab-0-1": {
                        "id": "tab-0-1",
                        "layouts": {"0": {"x": 1, "y": 1, "w": 2, "h": 2}},
                    },
                },
            },
            # tab-1 has its own real, custom multi-interval screenSizes preference -> its widget's
            # converted layout keeps the original config id, and the preference itself is kept
            # (with 'columns' added to the entry lacking it)
            "tab-1": {
                "id": "tab-1",
                "preferences": [
                    {
                        "name": "screenSizes",
                        "value": json.dumps([
                            {"id": 3, "moreOrEqual": 0, "lessOrEqual": 767},
                            {"id": 7, "moreOrEqual": 768, "lessOrEqual": -1, "columns": 12},
                        ]),
                        "inherit": False,
                    },
                ],
                "widgets": {
                    "tab-1-0": {
                        "id": "tab-1-0",
                        "layout": 0,
                        "positions": {
                            "configurations": [
                                {
                                    "id": 7,
                                    "widget": {
                                        "top": 8, "left": 10, "width": 6, "height": 4,
                                        "relx": True, "rely": True, "relwidth": True, "relheight": True,
                                    },
                                }
                            ]
                        },
                    },
                },
            },
        },
    }
    await db_session.client.workspaces.insert_one(doc)

    try:
        await commands.convert_layouts_cmd(SimpleNamespace())

        updated = await db_session.client.workspaces.find_one({"_id": workspace_id})

        migrated_widget = updated["tabs"]["tab-0"]["widgets"]["tab-0-0"]
        assert "positions" not in migrated_widget
        assert "layout" not in migrated_widget
        assert set(migrated_widget["layouts"]) == {desktop_id}
        assert migrated_widget["layouts"][desktop_id]["x"] == round(10 * 12 / 20)

        # The already-migrated widget is left untouched
        assert updated["tabs"]["tab-0"]["widgets"]["tab-0-1"]["layouts"] == {"0": {"x": 1, "y": 1, "w": 2, "h": 2}}

        pref_names = {p["name"] for p in updated["preferences"]}
        assert "baselayout" not in pref_names
        assert "screenSizes" not in pref_names
        assert "public" in pref_names

        tab_pref_names = {p["name"] for p in updated["tabs"]["tab-0"]["preferences"]}
        assert "initiallayout" not in tab_pref_names

        # tab-1: custom screenSizes preference kept (ids untouched, 'columns' filled in)
        custom_widget = updated["tabs"]["tab-1"]["widgets"]["tab-1-0"]
        assert "positions" not in custom_widget
        assert set(custom_widget["layouts"]) == {"7"}

        tab1_screen_sizes = next(p for p in updated["tabs"]["tab-1"]["preferences"] if p["name"] == "screenSizes")
        tab1_value = json.loads(tab1_screen_sizes["value"])
        assert [entry["id"] for entry in tab1_value] == [3, 7]
        assert tab1_value[0]["columns"] == 12
        assert tab1_value[1]["columns"] == 12

        # Idempotent: running it again makes no further changes
        await commands.convert_layouts_cmd(SimpleNamespace())
        updated_again = await db_session.client.workspaces.find_one({"_id": workspace_id})
        assert updated_again == updated
    finally:
        # This test inserts a raw (schema-incomplete) document directly into the shared mock
        # 'workspaces' collection; remove it so later tests iterating that collection don't choke
        # on it.
        await db_session.client.workspaces.delete_one({"_id": workspace_id})
