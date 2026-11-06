from pydantic import BaseModel, Field

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
    sdr: float
    outer_diameter_mm: float = Field(gt=0, allow_inf_nan=False)
    wall_mm: float
    standard: str | None = None


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
