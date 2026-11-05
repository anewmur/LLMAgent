from pydantic import BaseModel


class Point(BaseModel):
    id: str
    x: float
    y: float
    ground: float | None = None
    axis: float | None = None   # None, если отметки нет (сценарий 3)


class Bend(BaseModel):
    at: str
    angle_deg: float


class Pipe(BaseModel):
    material: str
    sdr: float
    outer_diameter_mm: float
    wall_mm: float


class ObjectInfo(BaseModel):
    name: str
    project_code: str
    coordinate_system: str
    pipe_material: str


class Project(BaseModel):
    object: ObjectInfo
    pipe: Pipe
    points: list[Point]
    bends: list[Bend]