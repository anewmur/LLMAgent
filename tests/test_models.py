import json

from core.models import DocumentId, Level, Project, Status


def test_with_point_returns_changed_copy_or_none(route_data):
    project = Project.model_validate(route_data)
    before = project.model_dump()

    data = project.with_point("P3", x=125, axis=None)

    assert data["points"][3]["x"] == 125
    assert data["points"][3]["axis"] is None
    assert project.with_point("missing", x=125) is None
    assert project.model_dump() == before


def test_bend_names_follow_route_order(route_data):
    route_data["bends"].reverse()
    project = Project.model_validate(route_data)

    assert project.bend_names() == {"P2": "УП1", "P3": "УП2"}


def test_with_pipe_copies_fields_and_synchronizes_material(route_data):
    route_data["pipe"]["material"] = "ПЭ 80"
    project = Project.model_validate(route_data)
    original = project.model_dump()

    data = project.with_pipe(material="ПЭ 100", outer_diameter_mm=160,
                             wall_mm=9.5, sdr=17, standard="ТУ TEST")

    assert data["pipe"] == {"material": "ПЭ 100", "outer_diameter_mm": 160,
                            "wall_mm": 9.5, "sdr": 17, "standard": "ТУ TEST"}
    assert data["object"]["pipe_material"] == "ПЭ 100"
    assert project.with_pipe(material="ПЭ 80")["object"]["pipe_material"] == "ПЭ 80"
    assert project.model_dump() == original
    updated = Project.model_validate(data)
    assert updated.with_pipe(material="ПЭ 100", standard="ТУ TEST") is None
    assert updated.with_pipe() is None
    assert updated.with_pipe(standard=None)["pipe"]["standard"] is None


def test_enums_keep_plain_strings_in_json_and_log():
    response = {"status": Status.WARNING, "checks": [{"level": Level.ERROR}], "document": DocumentId.PROFILE}

    assert json.dumps(response) == '{"status": "warning", "checks": [{"level": "error"}], "document": "profile"}'
    assert str(response) == "{'status': 'warning', 'checks': [{'level': 'error'}], 'document': 'profile'}"
    assert f"{Status.OK}: {DocumentId.PLAN}.svg" == "ok: plan.svg"
