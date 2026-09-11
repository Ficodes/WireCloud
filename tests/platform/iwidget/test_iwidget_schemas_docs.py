# -*- coding: utf-8 -*-

import pytest
from pydantic import ValidationError

from wirecloud.platform.iwidget import docs, schemas
from wirecloud.platform.iwidget.models import WidgetLayout, WidgetPermissions


def test_iwidget_docs_constants():
    assert isinstance(docs.get_widget_instance_collection_summary, str)
    assert isinstance(docs.create_widget_instance_collection_summary, str)
    assert isinstance(docs.update_widget_instance_collection_summary, str)
    assert isinstance(docs.get_widget_instance_entry_summary, str)
    assert isinstance(docs.update_widget_instance_properties_summary, str)
    assert isinstance(docs.widget_instance_data, list)


def test_iwidget_schemas_roundtrip():
    create = schemas.WidgetInstanceDataCreate(
        title="Widget",
        widget="acme/widget/1.0.0",
        layouts={"0": WidgetLayout(w=2, h=3)},
        permissions=WidgetPermissions(),
    )
    data = schemas.WidgetInstanceData(
        **create.model_dump(),
        id="ws-0-0",
        preferences={},
        properties={},
    )
    update = schemas.WidgetInstanceDataUpdate(
        id="ws-0-0",
        layouts={"0": schemas.WidgetLayoutUpdate(w=4), "1": None},
        move=True,
    )
    assert create.widget == "acme/widget/1.0.0"
    assert create.layouts["0"].w == 2
    assert data.id == "ws-0-0"
    assert update.move is True
    assert update.layouts["0"].w == 4
    assert update.layouts["1"] is None


def test_iwidget_schemas_screen_size_key_validation():
    # Valid decimal keys are accepted
    schemas.WidgetInstanceDataCreate(
        title="Widget", widget="acme/widget/1.0.0", layouts={"0": WidgetLayout(), "12": WidgetLayout()}
    )

    # Non-decimal keys are rejected (422 at the route layer)
    with pytest.raises(ValidationError):
        schemas.WidgetInstanceDataCreate(
            title="Widget", widget="acme/widget/1.0.0", layouts={"not-a-number": WidgetLayout()}
        )

    with pytest.raises(ValidationError):
        schemas.WidgetInstanceDataUpdate(layouts={"-1": None})
