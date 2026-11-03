"""Conditional writes detect stale edits and advance successful preconditions."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from wirecloud.platform.workspace.concurrency import check_write, conditional_query, write_preconditions


def test_successful_write_updates_the_next_precondition():
    token = write_preconditions.set({"workspace": "before"})
    try:
        assert conditional_query("workspace", {"_id": "workspace"}) == {"_id": "workspace", "last_modified": "before"}
        check_write("workspace", SimpleNamespace(matched_count=1), timestamp="after")
        assert conditional_query("workspace", {}) == {"last_modified": "after"}
        assert conditional_query("other", {"_id": "other"}) == {"_id": "other"}
    finally:
        write_preconditions.reset(token)


@pytest.mark.parametrize("deleted", [False, True])
def test_stale_update_or_delete_cannot_advance_the_precondition(deleted):
    token = write_preconditions.set({"workspace": "before"})
    try:
        with pytest.raises(HTTPException) as error:
            check_write("workspace", SimpleNamespace(matched_count=0, deleted_count=0), deleted=deleted)
        assert error.value.status_code == 409
        assert write_preconditions.get() == {"workspace": "before"}
    finally:
        write_preconditions.reset(token)


def test_successful_delete_does_not_replace_the_timestamp():
    token = write_preconditions.set({"workspace": "before"})
    try:
        check_write("workspace", SimpleNamespace(deleted_count=1), deleted=True)
        assert write_preconditions.get() == {"workspace": "before"}
    finally:
        write_preconditions.reset(token)


def test_unconditional_writes_do_not_require_a_database_result():
    token = write_preconditions.set(None)
    try:
        assert conditional_query("workspace", {"_id": "workspace"}) == {"_id": "workspace"}
        check_write("workspace", None)
    finally:
        write_preconditions.reset(token)
