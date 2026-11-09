"""Параллельные контуры плана с касательными круговыми отводами."""

from dataclasses import dataclass
from math import atan2, hypot, tan, cos

from core import drawing_settings as settings


@dataclass(frozen=True)
class PipeCorner:
    """Поворот оси в координатах листа; все длины в мм листа."""

    index: int
    incoming: tuple
    outgoing: tuple
    turn: float
    tangent: float
    available: float
    rounded: bool


class PipeContours:
    """Два равноудалённых контура; непоместившийся отвод заменяется угловым стыком."""

    def __init__(self, coordinates, bend_indices, diameter):
        """Готовит повороты по координатам и наружному диаметру в мм листа."""
        self.coordinates, self.diameter = coordinates, diameter
        self.radius = settings.BEND_RADIUS_FACTOR * diameter
        self.corners = [self.corner(index, index in bend_indices)
                        for index in range(1, len(coordinates) - 1)]

    def marker_points(self):
        """Возвращает вершины, заменяя округлённые повороты серединами дуг оси."""
        points = list(self.coordinates)
        for corner in self.corners:
            if not corner.rounded:
                continue
            direction_x = corner.outgoing[0] - corner.incoming[0]
            direction_y = corner.outgoing[1] - corner.incoming[1]
            magnitude = hypot(direction_x, direction_y)
            distance = self.radius * (1 / cos(abs(corner.turn) / 2) - 1)
            vertex_x, vertex_y = points[corner.index]
            points[corner.index] = (vertex_x + distance * direction_x / magnitude,
                                    vertex_y + distance * direction_y / magnitude)
        return points

    @staticmethod
    def direction(start, end):
        """Возвращает единичное направление и длину участка."""
        delta_x, delta_y = end[0] - start[0], end[1] - start[1]
        length = hypot(delta_x, delta_y)
        return (delta_x / length, delta_y / length), length

    def corner(self, index, has_bend):
        """Рассчитывает угол и касательную, проверяя место на обоих соседних участках."""
        incoming, before = self.direction(self.coordinates[index - 1], self.coordinates[index])
        outgoing, after = self.direction(self.coordinates[index], self.coordinates[index + 1])
        cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
        dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        turn = atan2(cross, dot)
        tangent = self.radius * abs(tan(turn / 2)) if has_bend else 0
        available = min(before, after) / 2
        rounded = has_bend and abs(cross) > settings.GEOMETRY_TOLERANCE_MM and tangent <= available
        return PipeCorner(index, incoming, outgoing, turn, tangent, available, rounded)

    @staticmethod
    def shifted(point, direction, offset):
        """Сдвигает точку по левой нормали к направлению."""
        return point[0] - direction[1] * offset, point[1] + direction[0] * offset

    def corner_commands(self, corner, offset):
        """Возвращает касательные и дугу либо угловой стык одного контура."""
        vertex = self.coordinates[corner.index]
        incoming, outgoing = corner.incoming, corner.outgoing
        if corner.rounded:
            return self.arc_commands(corner, offset)
        denominator = 1 + incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        if abs(denominator) < settings.GEOMETRY_TOLERANCE_MM:
            before = self.shifted(vertex, incoming, offset)
            after = self.shifted(vertex, outgoing, offset)
            return f"L {before[0]},{before[1]} L {after[0]},{after[1]}"
        corner_x = vertex[0] - (incoming[1] + outgoing[1]) * offset / denominator
        corner_y = vertex[1] + (incoming[0] + outgoing[0]) * offset / denominator
        return f"L {corner_x},{corner_y}"

    def arc_commands(self, corner, offset):
        """Возвращает касательные точки и концентрическую круговую дугу."""
        vertex = self.coordinates[corner.index]
        incoming, outgoing = corner.incoming, corner.outgoing
        entry = (vertex[0] - incoming[0] * corner.tangent, vertex[1] - incoming[1] * corner.tangent)
        exit_point = (vertex[0] + outgoing[0] * corner.tangent, vertex[1] + outgoing[1] * corner.tangent)
        entry_x, entry_y = self.shifted(entry, incoming, offset)
        exit_x, exit_y = self.shifted(exit_point, outgoing, offset)
        sweep = int(corner.turn > 0)
        radius = self.radius - (offset if sweep else -offset)
        return f"L {entry_x},{entry_y} A {radius},{radius} 0 0 {sweep} {exit_x},{exit_y}"

    def path_data(self, offset):
        """Возвращает непрерывный SVG-путь с заданным отступом от оси, мм листа."""
        incoming = self.direction(self.coordinates[0], self.coordinates[1])[0]
        start_x, start_y = self.shifted(self.coordinates[0], incoming, offset)
        commands = [f"M {start_x},{start_y}"]
        commands.extend(self.corner_commands(corner, offset) for corner in self.corners)
        outgoing = self.direction(self.coordinates[-2], self.coordinates[-1])[0]
        end_x, end_y = self.shifted(self.coordinates[-1], outgoing, offset)
        commands.append(f"L {end_x},{end_y}")
        return " ".join(commands)
