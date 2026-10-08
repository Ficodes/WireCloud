# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from types import SimpleNamespace

from wirecloud.platform import search


class _FakeIndices:
    def __init__(self, exists_value=True):
        self.exists_value = exists_value
        self.deleted = []
        self.created = []

    async def exists(self, index):
        return self.exists_value

    async def delete(self, index):
        self.deleted.append(index)

    async def create(self, index, body):
        self.created.append((index, body))


class _FakeES:
    def __init__(self, exists_value=True):
        self.indices = _FakeIndices(exists_value=exists_value)
        self.index_calls = []
        self.delete_calls = []
        self.update_calls = []
        self.exists_calls = []

    async def index(self, index, id, document):
        self.index_calls.append((index, id, document))

    async def delete(self, index, id):
        self.delete_calls.append((index, id))

    async def exists(self, index, id):
        self.exists_calls.append((index, id))
        return True

    async def update(self, index, id, doc):
        self.update_calls.append((index, id, doc))


def _workspace(last_modified=None):
    return SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        name="home",
        title="Home",
        description="Desc",
        longdescription="Long Desc",
        public=True,
        requireauth=False,
        searchable=True,
        last_modified=last_modified,
        creation_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        creator="507f1f77bcf86cd799439012",
        users=[SimpleNamespace(id="u1"), SimpleNamespace(id="u2")],
        groups=[SimpleNamespace(id="g1")],
        is_shared=lambda: True,
    )


async def test_clean_prepare_and_add_delete_index(monkeypatch):
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    cleaned = search.clean_workspace_out(
        {
            "_source": {
                "name": "w1",
                "title": "Title",
                "description": "D",
                "longdescription": "LD",
                "public": True,
                "requireauth": False,
                "last_modified": ts,
                "owner": "alice",
                "shared": True,
            }
        }
    )
    assert cleaned.name == "w1"
    assert cleaned.owner == "alice"

    prepared = search.prepare_workspace_for_indexing(_workspace(last_modified=None), "alice")
    assert prepared.owner == "alice"
    assert prepared.last_modified == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert prepared.users == ["u1", "u2"]
    assert prepared.groups == ["g1"]

    es = _FakeES()
    monkeypatch.setattr("wirecloud.commons.search.es_client", es)
    await search.add_workspace_to_index(SimpleNamespace(username="alice"), _workspace())
    await search.delete_workspace_from_index(_workspace())
    assert es.index_calls[0][0] == search.WORKSPACES_INDEX
    assert es.delete_calls[0][0] == search.WORKSPACES_INDEX


async def test_search_workspaces_builds_expected_body(monkeypatch, db_session):
    captured = {}

    async def _build_search_response(index, body, pagenum, max_results, clean):
        captured["index"] = index
        captured["body"] = body
        captured["pagenum"] = pagenum
        captured["max_results"] = max_results
        captured["clean"] = clean
        return {"ok": True}

    monkeypatch.setattr("wirecloud.commons.search.build_search_response", _build_search_response)
    monkeypatch.setattr(search, "get_all_user_groups", lambda _db, _user: _groups())

    async def _groups():
        return [SimpleNamespace(id="g1"), SimpleNamespace(id="g2")]

    class _User:
        id = "u1"
        groups = ["x"]

        def has_perm(self, codename):
            return codename == "WORKSPACE.VIEW"

    global_user = _User()
    ok = await search.search_workspaces(db_session, global_user, "wire", 2, 10, order_by=("name", "-owner"))
    assert ok == {"ok": True}
    assert captured["index"] == search.WORKSPACES_INDEX
    assert captured["body"]["sort"] == [{"name.keyword": {"order": "asc"}, "owner.keyword": {"order": "desc"}}]
    assert "should" not in captured["body"]["query"]["bool"]

    class _RestrictedUser(_User):
        def has_perm(self, _codename):
            return False

    restricted_user = _RestrictedUser()
    await search.search_workspaces(db_session, restricted_user, "name:home", 1, 5, order_by=None)
    bool_query = captured["body"]["query"]["bool"]
    assert bool_query["must"][0]["query_string"]["query"] == "name:home"
    assert bool_query["minimum_should_match"] == 1
    assert {"term": {"users": "u1"}} in bool_query["should"]
    assert {"terms": {"groups": ["g1", "g2"]}} in bool_query["should"]

    await search.search_workspaces(db_session, None, "", 1, 5, order_by=None)
    public_bool = captured["body"]["query"]["bool"]
    assert public_bool["must"] == []
    assert public_bool["should"] == [{"term": {"public": True}}]

    class _RestrictedUserNoGroups(_User):
        groups = []

        def has_perm(self, _codename):
            return False

    await search.search_workspaces(db_session, _RestrictedUserNoGroups(), "home", 1, 5, order_by=None)
    bool_no_groups = captured["body"]["query"]["bool"]
    assert {"term": {"users": "u1"}} in bool_no_groups["should"]
    assert not any("groups" in clause.get("terms", {}) for clause in bool_no_groups["should"])


async def test_rebuild_and_update_workspace_index_paths(monkeypatch, db_session):
    es = _FakeES(exists_value=True)
    monkeypatch.setattr("wirecloud.commons.search.es_client", es)

    async def _all_workspaces(_db):
        return [_workspace()]

    async def _username_by_id(_db, _creator):
        return "alice"

    bulk_calls = {}

    async def _bulk(_es, actions):
        bulk_calls["actions"] = actions

    monkeypatch.setattr("wirecloud.platform.workspace.crud.get_all_workspaces", _all_workspaces)
    monkeypatch.setattr(search, "get_username_by_id", _username_by_id)
    monkeypatch.setattr(search, "async_bulk", _bulk)

    await search.rebuild_workspace_index(db_session)
    assert search.WORKSPACES_INDEX in es.indices.deleted
    assert es.indices.created[0][0] == search.WORKSPACES_INDEX
    assert bulk_calls["actions"][0]["_source"]["owner"] == "alice"

    await search.update_workspace_in_index(db_session, _workspace())
    assert es.exists_calls[0] == (search.WORKSPACES_INDEX, "507f1f77bcf86cd799439011")
    assert es.index_calls[0][0] == search.WORKSPACES_INDEX
    assert es.update_calls == []

    class _NoDocES(_FakeES):
        async def exists(self, index, id):
            self.exists_calls.append((index, id))
            return False

    es2 = _NoDocES(exists_value=False)
    monkeypatch.setattr("wirecloud.commons.search.es_client", es2)
    monkeypatch.setattr("wirecloud.platform.workspace.crud.get_all_workspaces", _all_workspaces)
    await search.rebuild_workspace_index(db_session)
    assert es2.indices.deleted == []

    await search.update_workspace_in_index(db_session, _workspace())
    assert es2.index_calls == []
    assert es2.update_calls == []
