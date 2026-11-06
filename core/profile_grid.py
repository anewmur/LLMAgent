from pathlib import Path
from string import Template
from xml.sax.saxutils import escape, quoteattr

from core.formatting import format_number, format_station


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "profile_grid.svg"
# Центры и границы строк соответствуют SVG-макету сетки.
SIDEBAR_WIDTH = 70
POINT_ORIGIN = SIDEBAR_WIDTH + 6
LABEL_OFFSET = 1.5
BOTTOM_LEVEL_Y = 7.5
GROUND_LEVEL_Y = 22.5
NATURAL_GROUND_Y = 37.5
SLOPE_VALUE_Y = 81
SLOPE_ROW_TOP = 77
SLOPE_ROW_BOTTOM = 99
SLOPE_LINE_Y = (SLOPE_ROW_TOP + SLOPE_ROW_BOTTOM) / 2
SECTION_LENGTH_Y = 96
DISTANCE_Y = 107
POINT_NAME_Y = 121
STATION_Y = 141
LEVEL_ROWS_BOTTOM = 45
DISTANCE_ROW_TOP = 99
GRID_HEIGHT = 151


class ProfileGrid:
    """Сетка формы 2 и привязки значений к тем же пикетам, что у профиля."""

    def __init__(self, drawing):
        self.drawing = drawing
        self.project = drawing.project
        self.x = [POINT_ORIGIN + s * drawing.mm_per_meter_x for s in drawing.stations]
        bend_ids = {bend.at for bend in self.project.bends}
        ids = [p.id for p in self.project.points if p.id in bend_ids]
        self.bend_names = {pid: f"УП{i}" for i, pid in enumerate(ids, 1)}

    def vertical_text(self, value, x, y, kind, point_id):
        return (
            f'<text data-kind="{kind}" data-point-id={quoteattr(point_id)} '
            f'transform="translate({x - LABEL_OFFSET} {y}) rotate(-90)" text-anchor="middle">'
            f'{escape(str(value))}</text>'
        )

    def draw_values(self):
        elements = []
        for i, point in enumerate(self.project.points):
            name = point.id
            if point.id in self.bend_names:
                name += " / " + self.bend_names[point.id]
            values = [
                (format_number(self.drawing.bottom_levels[i]), BOTTOM_LEVEL_Y, "bottom-level"),
                (format_number(point.ground), GROUND_LEVEL_Y, "ground-level"),
                ("—", NATURAL_GROUND_Y, "natural-ground"), (name, POINT_NAME_Y, "point-name"),
                (format_station(self.drawing.stations[i]), STATION_Y, "station"),
            ]
            for value, y, kind in values:
                elements.append(self.vertical_text(value, self.x[i], y, kind, point.id))
            elements.append(f'<path d="M {self.x[i]},0 V {LEVEL_ROWS_BOTTOM} '
                            f'M {self.x[i]},{DISTANCE_ROW_TOP} V {GRID_HEIGHT}" '
                            'fill="none" stroke="black" stroke-width="0.35"/>')
        return "\n".join(elements)

    def draw_slope(self, start, end, slope):
        if slope is None:
            return ""
        start_y = end_y = SLOPE_LINE_Y
        if slope > 0:
            start_y, end_y = SLOPE_ROW_BOTTOM, SLOPE_ROW_TOP
        elif slope < 0:
            start_y, end_y = SLOPE_ROW_TOP, SLOPE_ROW_BOTTOM
        return (f'<path data-kind="slope-line" d="M {start},{start_y} L {end},{end_y}" '
                'fill="none" stroke="black" stroke-width="0.35"/>')

    def draw_sections(self):
        elements = []
        for i, section in enumerate(self.drawing.sections):
            start, end = self.x[i:i + 2]
            middle = (start + end) / 2
            slope = section["slope_per_mille"]
            if i:
                elements.append(f'<line data-kind="slope-divider" x1="{start}" x2="{start}" '
                                f'y1="{SLOPE_ROW_TOP}" y2="{SLOPE_ROW_BOTTOM}" '
                                'stroke="black" stroke-width="0.35"/>')
            elements.append(self.draw_slope(start, end, slope))
            for value, y, kind in [(format_number(slope), SLOPE_VALUE_Y, "slope"),
                                   (format_number(section["length_m"]), SECTION_LENGTH_Y, "slope-length"),
                                   (format_number(section["length_m"]), DISTANCE_Y, "distance")]:
                elements.append(f'<text data-kind="{kind}" data-start-id={quoteattr(section["start_id"])} '
                                f'data-end-id={quoteattr(section["end_id"])} x="{middle}" y="{y}" '
                                f'text-anchor="middle">{value}</text>')
        return "\n".join(elements)

    def pipe_labels(self):
        pipe = self.project.pipe
        size = f"{pipe.outer_diameter_mm:g}×{pipe.wall_mm:g}".replace(".", ",")
        sdr = f"{pipe.sdr:g}".replace(".", ",")
        return {"pipe_name": escape(f"В1 — Труба {pipe.material}"),
                "pipe_size": escape(f"SDR {sdr} ⌀{size}")}

    def draw_projections(self):
        d = self.drawing
        elements = [f'<g id="profile-projections" font-family="Arial, sans-serif" font-size="{d.style.base_size}">']
        for i, (point, station) in enumerate(zip(self.project.points, d.stations)):
            level = point.ground if point.ground is not None else d.bottom_levels[i]
            if level is None:
                continue
            x = d.origin_x + station * d.mm_per_meter_x
            y = d.datum_y - (level - d.datum_level) * d.mm_per_meter_y
            elements.append(f'<path data-point-id={quoteattr(point.id)} d="M {x},{y} V {d.datum_y}" '
                            'stroke="black" stroke-width="0.35"/>')
            depth = d.levels[i]["depth_to_bottom_m"]
            elements.append(f'<text data-kind="depth" data-point-id={quoteattr(point.id)} '
                            f'transform="translate({x - LABEL_OFFSET} {y - 7}) rotate(-90)" text-anchor="middle">'
                            f'{format_number(depth)}</text>')
        elements.append('</g>')
        return "\n".join(elements)

    def render(self):
        d = self.drawing
        if any(b - a < 8 for a, b in zip(self.x, self.x[1:])):
            raise ValueError("Точки профиля ближе 8 мм на листе: нужен более крупный масштаб.")
        grid = Template(TEMPLATE_PATH.read_text(encoding="utf-8")).safe_substitute(
            left=d.origin_x - POINT_ORIGIN, top=d.datum_y, width=self.x[-1] + 2,
            middle=(POINT_ORIGIN + self.x[-1]) / 2,
            values=self.draw_values(), sections=self.draw_sections(), **self.pipe_labels(),
            horizontal_scale=d.horizontal_scale, vertical_scale=d.vertical_scale,
            datum=format_number(d.datum_level), font_size=d.style.base_size, title_size=d.style.title_size,
        )
        return self.draw_projections() + "\n" + grid
