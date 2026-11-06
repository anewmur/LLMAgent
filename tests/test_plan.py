import json
from xml.etree import ElementTree as ET

from core.plan import create_plan


def test_plan_geometry_scale_direction_and_fit(route_data, tmp_path):
    expected = [(77.5, 171), (137.5, 171), (197.5, 171), (197.5, 91), (277.5, 91), (357.5, 91)]
    ns = {"s": "http://www.w3.org/2000/svg"}

    # \u041f\u0435\u0440\u0435\u043d\u043e\u0441 \u0432\u0441\u0435\u0439 \u0442\u0440\u0430\u0441\u0441\u044b \u0432 \u0434\u0440\u0443\u0433\u0443\u044e \u0441\u0438\u0441\u0442\u0435\u043c\u0443 \u043a\u043e\u043e\u0440\u0434\u0438\u043d\u0430\u0442 \u043d\u0435 \u043c\u0435\u043d\u044f\u0435\u0442 \u0435\u0451 \u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044e \u043d\u0430 \u043b\u0438\u0441\u0442\u0435.
    for i, (dx, dy) in enumerate([(0, 0), (1000, -500)]):
        data = json.loads(json.dumps(route_data))
        data["object"].update(project_code="OTHER-03", name="\u0414\u0440\u0443\u0433\u043e\u0439 \u043e\u0431\u044a\u0435\u043a\u0442")
        for point in data["points"]:
            point["x"] += dx
            point["y"] += dy
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(data), encoding="utf-8")
        output_file = tmp_path / f"plan_{i}.svg"

        result = create_plan(input_file, output_file)

        assert result["status"] == "ok"
        assert result["scale"] == 1000
        root = ET.parse(output_file).getroot()
        assert root.get("viewBox") == "0 0 420 297"
        geometry = root.find("s:g[@id='route-geometry']", ns)
        points = geometry.findall("s:circle", ns)
        assert [p.get("data-point-id") for p in points] == ["P0", "P1", "P2", "P3", "P4", "P5"]
        coordinates = [(float(p.get("cx")), float(p.get("cy"))) for p in points]
        assert coordinates == expected
        x_values = [x for x, y in coordinates]
        y_values = [y for x, y in coordinates]
        assert (min(x_values) + max(x_values)) / 2 == (30 + 405) / 2
        assert (min(y_values) + max(y_values)) / 2 == (35 + 227) / 2
        line = geometry.find("s:polyline", ns)
        line_points = [tuple(map(float, pair.split(","))) for pair in line.get("points").split()]
        assert line_points == coordinates
        assert coordinates[1][0] - coordinates[0][0] == 60  # 60 \u043c = 60 \u043c\u043c \u043f\u0440\u0438 1:1000.
        assert coordinates[3][1] < coordinates[2][1]  # \u0411\u043e\u043b\u044c\u0448\u0438\u0435 Y \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u044b \u0432\u0432\u0435\u0440\u0445.
        assert not geometry.findall("s:text", ns)  # \u041f\u043e\u0434\u043f\u0438\u0441\u0438 \u043d\u0430\u0445\u043e\u0434\u044f\u0442\u0441\u044f \u0432 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e\u0439 \u0433\u0440\u0443\u043f\u043f\u0435.
        text = " ".join(root.itertext())
        assert "OTHER-03-\u041d\u0412" in text
        assert "\u0414\u0440\u0443\u0433\u043e\u0439 \u043e\u0431\u044a\u0435\u043a\u0442" in text
        assert "1:1000" in text

    # \u0411\u043e\u043b\u044c\u0448\u0430\u044f \u0442\u0440\u0430\u0441\u0441\u0430 \u043d\u0435 \u0434\u043e\u043b\u0436\u043d\u0430 \u043c\u043e\u043b\u0447\u0430 \u043e\u0431\u0440\u0435\u0437\u0430\u0442\u044c\u0441\u044f \u0438\u043b\u0438 \u043c\u0435\u043d\u044f\u0442\u044c \u043c\u0430\u0441\u0448\u0442\u0430\u0431.
    data["points"][-1]["x"] += 1000
    input_file.write_text(json.dumps(data), encoding="utf-8")
    output_file = tmp_path / "too_large.svg"
    result = create_plan(input_file, output_file)
    assert result["status"] == "error"
    assert "\u043d\u0435 \u043f\u043e\u043c\u0435\u0449\u0430\u0435\u0442\u0441\u044f" in result["message"]
    assert not output_file.exists()


def test_plan_labels_follow_calculated_lengths_and_stations(route_data, tmp_path):
    ns = {"s": "http://www.w3.org/2000/svg"}
    for p5_x, last_length, last_station in [(280, "80,00", "\u041f\u041a 3+60,00"), (300, "100,00", "\u041f\u041a 3+80,00")]:
        data = json.loads(json.dumps(route_data))
        data["points"][-1]["x"] = p5_x
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(data), encoding="utf-8")
        output_file = tmp_path / "plan.svg"

        result = create_plan(input_file, output_file)

        assert result["status"] == "ok"
        root = ET.parse(output_file).getroot()
        labels = root.find("s:g[@id='route-labels']", ns)
        names = labels.findall("s:text[@data-kind='point-name']", ns)
        assert [(e.get("data-point-id"), e.text) for e in names] == [
            (f"P{i}", f"P{i}") for i in range(6)
        ]
        stations = labels.findall("s:text[@data-kind='station']", ns)
        assert [e.text for e in stations] == [
            "\u041f\u041a 0+00,00", "\u041f\u041a 0+60,00", "\u041f\u041a 1+20,00",
            "\u041f\u041a 2+00,00", "\u041f\u041a 2+80,00", last_station,
        ]
        lengths = labels.findall("s:text[@data-kind='length']", ns)
        assert [e.text for e in lengths] == ["60,00", "60,00", "80,00", "80,00", last_length]
        assert [(e.get("data-start-id"), e.get("data-end-id")) for e in lengths] == [
            (f"P{i}", f"P{i + 1}") for i in range(5)
        ]
        points = root.findall("s:g[@id='route-geometry']/s:circle", ns)
        for point, name, station in zip(points, names, stations):
            assert float(name.get("y")) < float(station.get("y")) < float(point.get("cy"))
        assert float(lengths[0].get("y")) > float(points[0].get("cy"))
        assert float(lengths[2].get("x")) > float(points[2].get("cx"))
