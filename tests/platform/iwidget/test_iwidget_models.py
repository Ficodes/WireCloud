# -*- coding: utf-8 -*-

from types import SimpleNamespace

from bson import ObjectId

from wirecloud.platform.iwidget import models


def test_widget_models_serialization():
    layout = models.WidgetLayout()
    assert layout.model_dump() == {
        "x": None,
        "y": None,
        "w": 1,
        "h": 1,
        "minimized": False,
        "titlevisible": True,
        "fulldragboard": False,
        "visible": True,
        "dock": None,
        "dock_mode": "overlay",
        "dock_open": True,
    }

    layout = models.WidgetLayout(x=2, y=3, w=6, h=4, minimized=True, titlevisible=False,
                                 fulldragboard=True, visible=False, dock="left", dock_mode="push", dock_open=False)
    assert layout.model_dump() == {
        "x": 2,
        "y": 3,
        "w": 6,
        "h": 4,
        "minimized": True,
        "titlevisible": False,
        "fulldragboard": True,
        "visible": False,
        "dock": "left",
        "dock_mode": "push",
        "dock_open": False,
    }

    instance = models.WidgetInstance(id="ws-0-0", layouts={"0": models.WidgetLayout(w=2, h=3)})
    assert instance.layouts["0"].w == 2
    assert instance.layouts["0"].h == 3

    perms = models.WidgetPermissions(
        editor=models.WidgetPermissionsConfig(move=True, close=None),
        viewer=models.WidgetPermissionsConfig(move=False, rename=None),
    )
    serialized = perms.model_dump()
    assert serialized["editor"] == {"move": True}
    assert serialized["viewer"] == {"move": False}


async def test_widget_instance_set_variable_value(monkeypatch, db_session):
    instance = models.WidgetInstance(id="ws-0-0", resource=ObjectId())
    user = SimpleNamespace(id="u1")

    class _VarDef:
        def __init__(self, secure=False, var_type="text"):
            self.secure = secure
            self.type = var_type

    class _ResourceInfo:
        variables = SimpleNamespace(
            all={
                "secure_var": _VarDef(secure=True, var_type="text"),
                "bool_var": _VarDef(secure=False, var_type="boolean"),
                "num_var": _VarDef(secure=False, var_type="number"),
                "text_var": _VarDef(secure=False, var_type="text"),
            }
        )

    monkeypatch.setattr(models, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _resource())
    monkeypatch.setattr("wirecloud.platform.workspace.utils.encrypt_value", lambda value: f"enc:{value}")

    async def _resource():
        return SimpleNamespace(get_processed_info=lambda **_kwargs: _ResourceInfo())

    await instance.set_variable_value(db_session, "secure_var", "secret", user)
    assert instance.variables["secure_var"].users["u1"] == "enc:secret"

    await instance.set_variable_value(db_session, "bool_var", "true", user)
    assert instance.variables["bool_var"].users["u1"] is True
    await instance.set_variable_value(db_session, "bool_var", 0, user)
    assert instance.variables["bool_var"].users["u1"] is False

    await instance.set_variable_value(db_session, "num_var", "3.5", user)
    assert instance.variables["num_var"].users["u1"] == 3.5

    await instance.set_variable_value(db_session, "text_var", "abc", user)
    assert instance.variables["text_var"].users["u1"] == "abc"

    instance.variables["text_var"] = {"users": {"u1": "x"}}
    await instance.set_variable_value(db_session, "text_var", "def", user)
    assert instance.variables["text_var"]["users"]["u1"] == "def"

    monkeypatch.setattr(models, "get_catalogue_resource_by_id", lambda *_args, **_kwargs: _none())

    async def _none():
        return None

    try:
        await instance.set_variable_value(db_session, "text_var", "x", user)
    except ValueError as exc:
        assert "Widget not found" in str(exc)
