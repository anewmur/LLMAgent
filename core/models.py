from dataclasses import dataclass
from enum import Enum, IntEnum

from pydantic import BaseModel, Field

from core.settings import MIN_POINTS


UNIT_M = "м"
UNIT_MM = "мм"
UNIT_PIECE = "шт."
UNIT_DEGREE = "°"
# Место проблемы, относящейся к трубе, в ответах проверки.
PIPE_WHERE = "pipe"


class Status(str, Enum):
    """Статус операции со строковым представлением для JSON, отчётов и журнала."""
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    __str__ = str.__str__
    __repr__ = str.__repr__


class Level(str, Enum):
    """Уровень результата проверки."""
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    __str__ = str.__str__
    __repr__ = str.__repr__


class ProblemCode(str, Enum):
    """Коды ошибок исходных данных и аргументов инструментов."""
    STRUCTURE = "structure"
    RELEASE_FAILED = "release_failed"
    MISSING_AXIS = "missing_axis"
    MISSING_GROUND = "missing_ground"
    DUPLICATE_POINT = "duplicate_point"
    MISSING_BEND_POINT = "missing_bend_point"
    DUPLICATE_BEND = "duplicate_bend"
    MATERIAL_CONFLICT = "material_conflict"
    PIPE_SDR_MISMATCH = "pipe_sdr_mismatch"
    ZERO_LENGTH = "zero_length"
    END_BEND = "end_bend"
    BEND_ANGLE = "bend_angle"
    MISSING_BEND = "missing_bend"
    BEND_NOT_FOUND = "bend_not_found"
    FIELDS_REQUIRED = "fields_required"
    POINT_NOT_FOUND = "point_not_found"
    __str__ = str.__str__
    __repr__ = str.__repr__


@dataclass(frozen=True)
class Problem:
    """Ошибка исходных данных; код определяет блокируемые расчёты."""
    level: Level
    code: ProblemCode
    message: str
    where: str = ""

    @property
    def blocks_length(self):
        """Возвращает, препятствует ли проблема расчёту длины."""
        return self.code in (ProblemCode.DUPLICATE_POINT, ProblemCode.ZERO_LENGTH)

    @property
    def blocks_quantities(self):
        """Возвращает, препятствует ли проблема расчёту количеств."""
        return self.code in (
            ProblemCode.MISSING_BEND_POINT, ProblemCode.DUPLICATE_BEND,
            ProblemCode.MATERIAL_CONFLICT, ProblemCode.END_BEND, ProblemCode.BEND_ANGLE,
            ProblemCode.PIPE_SDR_MISMATCH, ProblemCode.MISSING_BEND,
        )

    def to_dict(self):
        """Возвращает прежние поля ответа инструмента; внутренний код в JSON не выводится."""
        return {"level": self.level, "where": self.where, "message": self.message,
                "blocks_length": self.blocks_length, "blocks_quantities": self.blocks_quantities}


@dataclass(frozen=True)
class CheckResult:
    """Результат проверки готового комплекта."""
    name: str
    status: Status
    message: str
    reference: str = ""

    def to_dict(self):
        """Возвращает прежний формат проверки для ответа инструмента и отчёта."""
        return {"id": self.name, "passed": self.status == Status.OK, "detail": self.message,
                "level": Level(self.status)}


class DocumentId(str, Enum):
    """Идентификаторы чертежей комплекта из конфигурации."""
    GENERAL = "general"
    PLAN = "plan"
    PROFILE = "profile"
    SPECIFICATION = "specification"
    __str__ = str.__str__
    __repr__ = str.__repr__


class SpecificationColumn(IntEnum):
    """Индексы граф спецификации с нулевым отсчётом."""
    POSITION = 0
    NAME = 1
    DOCUMENT = 2
    PRODUCT_CODE = 3
    SUPPLIER = 4
    UNIT = 5
    QUANTITY = 6
    MASS = 7
    NOTE = 8


class PointField(Enum):
    X = ("x", "x", "X", UNIT_M)
    Y = ("y", "y", "Y", UNIT_M)
    AXIS = ("axis", "axis", "отметка оси трубы", UNIT_M)
    GROUND = ("ground", "ground", "отметка земли", UNIT_M)

    def __init__(self, argument, attribute, label, unit):
        self.argument = argument
        self.attribute = attribute
        self.label = label
        self.unit = unit


class PipeField(Enum):
    """Поля трубы: аргументы правки, подписи, единицы и JSON-типы."""

    MATERIAL = ("material", "material", "Материал трубы", "", "string")
    OUTER_DIAMETER_MM = ("outer_diameter", "outer_diameter_mm", "Наружный диаметр трубы", UNIT_MM, "number")
    WALL_MM = ("wall_thickness", "wall_mm", "Толщина стенки трубы", UNIT_MM, "number")
    SDR = ("sdr", "sdr", "SDR", "", "number")
    STANDARD = ("standard", "standard", "Стандарт/ТУ на трубу", "", "string")

    def __init__(self, argument, attribute, label, unit, json_type):
        """Сохраняет имя поля, оформление изменения и JSON-тип."""
        self.argument = argument
        self.attribute = attribute
        self.label, self.unit = label, unit
        self.json_type = json_type


@dataclass
class Change:
    name: str
    before: float | str | None
    after: float | str | None
    unit: str = UNIT_M


@dataclass
class ChangeSet:
    title: str
    values: list[Change]
    sheets: list[str]


class Point(BaseModel):
    id: str
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    ground: float | None = Field(default=None, allow_inf_nan=False)
    axis: float | None = Field(default=None, allow_inf_nan=False)


class Bend(BaseModel):
    at: str
    angle_deg: float = Field(gt=0, le=180, allow_inf_nan=False)


class Pipe(BaseModel):
    material: str
    sdr: float = Field(gt=0, allow_inf_nan=False)
    outer_diameter_mm: float = Field(gt=0, allow_inf_nan=False)
    wall_mm: float = Field(gt=0, allow_inf_nan=False)
    standard: str | None = None
    insulation: str | None = None


class ObjectInfo(BaseModel):
    name: str
    project_code: str
    coordinate_system: str
    pipe_material: str


class Project(BaseModel):
    object: ObjectInfo
    pipe: Pipe
    points: list[Point] = Field(min_length=MIN_POINTS)
    bends: list[Bend]

    def bend_names(self) -> dict:
        """Возвращает номера УП в порядке точек трассы, независимо от порядка отводов."""
        bend_ids = {bend.at for bend in self.bends}
        point_ids = [point.id for point in self.points if point.id in bend_ids]
        return {point_id: f"УП{index}" for index, point_id in enumerate(point_ids, 1)}

    def with_point(self, name, bends=(), **fields) -> dict | None:
        """Копия проекта с правкой точки и установкой всех переданных отводов."""
        data = self.model_dump()
        for point in data["points"]:
            if point["id"] == name:
                point.update(fields)
                for bend in bends:
                    self.set_bend(data, bend["at"], bend["angle_deg"])
                return data
        return None

    @staticmethod
    def set_bend(data, at, angle_deg):
        """Добавляет отвод в копию данных или заменяет угол существующего."""
        for bend in data["bends"]:
            if bend["at"] == at:
                bend["angle_deg"] = angle_deg
                return
        data["bends"].append({"at": at, "angle_deg": angle_deg})

    def with_added_point(self, after, point, bend_angle=None) -> dict | None:
        """Возвращает копию с точкой после after и необязательным отводом в ней."""
        data = self.model_dump()
        for index, existing in enumerate(data["points"]):
            if existing["id"] == after:
                data["points"].insert(index + 1, dict(point))
                if bend_angle is not None:
                    self.set_bend(data, point["id"], bend_angle)
                return data
        return None

    def without_point(self, name) -> dict | None:
        """Возвращает копию без точки и отвода в ней либо None, если точки нет."""
        if not any(point.id == name for point in self.points):
            return None
        data = self.model_dump()
        data["points"] = [point for point in data["points"] if point["id"] != name]
        data["bends"] = [bend for bend in data["bends"] if bend["at"] != name]
        return data

    def with_bend(self, at, angle_deg) -> dict | None:
        """Возвращает копию с установленным отводом; согласованность проверяет валидатор."""
        if not any(point.id == at for point in self.points):
            return None
        data = self.model_dump()
        self.set_bend(data, at, angle_deg)
        return data

    def without_bend(self, at) -> dict | None:
        """Возвращает копию без отвода в точке либо None, если отвода нет."""
        if not any(bend.at == at for bend in self.bends):
            return None
        data = self.model_dump()
        data["bends"] = [bend for bend in data["bends"] if bend["at"] != at]
        return data

    def with_pipe(self, **fields) -> dict | None:
        """Возвращает копию с правкой трубы и согласованным материалом либо None без изменений."""
        data = self.model_dump()
        data["pipe"].update(fields)
        material = PipeField.MATERIAL.attribute
        if material in fields:
            data["object"]["pipe_material"] = fields[material]
        if data["pipe"] == self.pipe.model_dump() and data["object"]["pipe_material"] == self.object.pipe_material:
            return None
        return data
