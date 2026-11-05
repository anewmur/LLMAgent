from pydantic import BaseModel, Field

class Point(BaseModel):
    id: str
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    ground: float | None = None
    axis: float | None = None


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
    points: list[Point] = Field(min_length=2)
    bends: list[Bend]