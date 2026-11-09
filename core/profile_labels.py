"""Габариты уже нарисованных подписей профиля для размещения и проверок."""

from dataclasses import dataclass
import re

from config import drawing_settings as settings
from core.label_geometry import text_bounds


NS = {"s": "http://www.w3.org/2000/svg"}


@dataclass(frozen=True)
class ProfileLabel:
    """Прямоугольник подписи и её клетки в координатах листа, мм."""

    text: str
    bounds: tuple
    cell: tuple | None
    region: str


def translation(element):
    """Возвращает смещение translate элемента или нулевое смещение."""
    match = re.search(r"translate\(([^)]+)\)", element.get("transform", ""))
    return tuple(map(float, re.split(r"[ ,]+", match.group(1).strip()))) if match else (0, 0)


class ProfileLabels:
    """Читает текст, переносы и поворот −90° из готового SVG профиля."""

    def __init__(self, root):
        """Собирает подписи таблицы, глубин, масштабов, полки и учебного заголовка."""
        self.items = []
        for group_id in ("profile-grid", "profile-projections"):
            group = root.find(f".//s:g[@id='{group_id}']", NS)
            if group is not None:
                self.walk(group, (0, 0), settings.DEFAULT_FONT_SIZE_MM, group_id)
        shelf = root.find(".//s:g[@data-kind='pipe-label']", NS)
        if shelf is not None:
            bounds = tuple(map(float, shelf.get("data-bounds").split()))
            self.items.append(ProfileLabel("Полка трубы", bounds, None, "above"))
        for element in root.findall("s:text", NS):
            if element.text == settings.TRAINING_LABEL:
                self.append_text(element, (0, 0), float(element.get("font-size")), "above")

    def walk(self, element, offset, font_size, region, anchor="start"):
        """Обходит группу с наследованием шрифта и смещения её начала."""
        font_size = float(element.get("font-size", font_size))
        anchor = element.get("text-anchor", anchor)
        if element.tag == f'{{{NS["s"]}}}text':
            self.append_text(element, offset, font_size, region, anchor)
            return
        delta_x, delta_y = translation(element)
        offset = offset[0] + delta_x, offset[1] + delta_y
        for child in element:
            self.walk(child, offset, font_size, region, anchor)

    def append_text(self, element, offset, font_size, region, anchor="start"):
        """Добавляет каждую строку подписи с фактическими координатами и клеткой."""
        cell = element.get("data-cell")
        if cell:
            left, top, right, bottom = map(float, cell.split())
            cell = left + offset[0], top + offset[1], right + offset[0], bottom + offset[1]
        baseline = float(element.get("y", 0))
        fragments = list(element) or [element]
        for fragment in fragments:
            baseline = float(fragment.get("y", baseline)) + float(fragment.get("dy", 0))
            left = float(fragment.get("x", element.get("x", 0)))
            text = fragment.text or ""
            bounds = text_bounds(text, left, baseline, font_size, element.get("text-anchor", anchor))
            bounds = self.on_sheet(bounds, element, offset)
            area = "table" if region == "profile-grid" and baseline >= 0 else "above"
            self.items.append(ProfileLabel(text, bounds, cell, area))

    @staticmethod
    def on_sheet(bounds, element, offset):
        """Переносит прямоугольник из локальных координат текста на лист."""
        left, top, right, bottom = bounds
        if "rotate(-90)" in element.get("transform", ""):
            left, top, right, bottom = top, -right, bottom, -left
        delta_x, delta_y = translation(element)
        return (left + delta_x + offset[0], top + delta_y + offset[1],
                right + delta_x + offset[0], bottom + delta_y + offset[1])
