from pathlib import Path

from core.calculations import (INPUT_PATH, calculate_material_quantities, calculate_pipe_levels,
                               calculate_route_geometry, calculate_route_length, load_project)
from core.profile_style import ProfileStyle
from core.release import OUTPUT_DIR, create_package
from core.validate import problem, validate_input


class RouteSession:
    """Текущий проект и только успешно выпущенные изменения этой сессии."""

    def __init__(self, input_file=INPUT_PATH, output_dir=OUTPUT_DIR):
        self.project, self.problems = load_project(input_file)
        if self.project is None:
            raise ValueError("; ".join(p["message"] for p in self.problems))
        self.output_dir = Path(output_dir)
        self.changes, self.tool_log = [], []
        self.font_size = 3.5

    def calculate_route_length(self):
        return calculate_route_length(self.project)

    def calculate_pipe_levels(self):
        return calculate_pipe_levels(self.project)

    def calculate_material_quantities(self):
        return calculate_material_quantities(self.project)

    def release(self):
        return create_package(self.project, self.output_dir, self.changes, self.font_size)

    @staticmethod
    def add_value(values, name, before, after, unit="м"):
        if before != after:
            values.append({"name": name, "before": before, "after": after, "unit": unit})

    def point_values(self, before, after):
        values = []
        for field, label in [("x", "X"), ("y", "Y"), ("axis", "отметка оси трубы")]:
            self.add_value(values, f"{before.id}, {label}", getattr(before, field), getattr(after, field))
        return values

    def section_values(self, before, after):
        values = []
        for old, new in zip(before["sections"], after["sections"]):
            name = f'Участок {old["start_id"]}–{old["end_id"]}'
            self.add_value(values, name + ", длина", old["length_m"], new["length_m"])
            self.add_value(values, name + ", уклон", old["slope_per_mille"], new["slope_per_mille"], "‰")
        return values

    def point_change(self, project, name):
        old = next(p for p in self.project.points if p.id == name)
        new = next(p for p in project.points if p.id == name)
        values = self.point_values(old, new)
        before, after = calculate_route_geometry(self.project.points), calculate_route_geometry(project.points)
        sections = self.section_values(before, after)
        length_changed = before["length_m"] != after["length_m"]
        sheets = ["Общие данные"] if length_changed else []
        if old.x != new.x or old.y != new.y:
            sheets.append("План")
        if sections:
            sheets.append("Профиль")
        self.add_value(values, "Общая длина трассы", before["length_m"], after["length_m"])
        self.add_value(values, "Количество трубы", before["length_m"], after["length_m"])
        if length_changed:
            sheets.append("Спецификация")
        return {"title": f"Изменение точки {name}", "values": values + sections, "sheets": sheets}

    def apply(self, project, change, font_size):
        result = create_package(project, self.output_dir, self.changes + [change], font_size)
        if result["status"] != "ok":
            return result
        self.project, self.font_size = project, font_size
        self.problems = result["problems"]
        self.changes.append(change)
        return {"status": "ok", "changes": change, "pdf": result["pdf"]}

    def update_point(self, name, **values):
        """Непереданные поля прежние; явный None проверяется как удаление."""
        fields = {"x": "x", "y": "y", "z": "axis"}
        if not values or not set(values).issubset(fields):
            return {"status": "error", "problems": [problem("error", name, "Укажите изменяемые x, y или z.")]}
        data = self.project.model_dump()
        point = next((p for p in data["points"] if p["id"] == name), None)
        if point is None:
            return {"status": "error", "problems": [problem("error", name, "Точка не найдена.")]}
        for field, value in values.items():
            point[fields[field]] = value
        project, problems = validate_input(data)
        if project is None or any(p["level"] == "error" for p in problems):
            return {"status": "error", "problems": problems}
        change = self.point_change(project, name)
        if not change["values"]:
            return {"status": "ok", "message": "Значения точки не изменились."}
        return self.apply(project, change, self.font_size)

    def change_profile_font(self, direction):
        size = ProfileStyle.font_step(self.font_size, direction)
        if size == self.font_size:
            return {"status": "ok", "message": "Достигнута граница ряда размеров шрифта."}
        values = []
        self.add_value(values, "Базовый шрифт профиля", self.font_size, size, "мм")
        change = {"title": "Изменение шрифта профиля", "values": values, "sheets": ["Профиль"]}
        return self.apply(self.project, change, size)
