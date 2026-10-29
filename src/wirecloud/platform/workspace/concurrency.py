"""Conditional writes for callers performing a read/modify/write operation."""
from contextvars import ContextVar
from fastapi import HTTPException

write_preconditions = ContextVar("workspace_write_preconditions", default=None)


def conditional_query(workspace_id, query):
    conditions = write_preconditions.get()
    if conditions is not None and str(workspace_id) in conditions:
        query["last_modified"] = conditions[str(workspace_id)]
    return query


def check_write(workspace_id, result, timestamp=None, deleted=False):
    conditions = write_preconditions.get()
    if conditions is not None and str(workspace_id) in conditions:
        if (result.deleted_count if deleted else result.matched_count) != 1:
            raise HTTPException(409, "Workspace changed; read it again before editing")
        if not deleted:
            conditions[str(workspace_id)] = timestamp
