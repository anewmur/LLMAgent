"""Общие формулировки для листа общих данных и отчёта о проверках."""

from core import drawing_settings as settings


COORDINATE_SYSTEM_NOTE = (
    "Система координат условная, единицы — метры. Ось X направлена вправо, ось Y — вверх листа."
)
COORDINATE_ORIENTATION_NOTE = "Ориентация системы относительно сторон света исходными данными не задана."
NETWORK_AND_GROUND_ASSUMPTION = (
    f"{settings.NETWORK_CODE} назначено условно. Отметка земли принята проектной. Натурная поверхность не задана."
)
BEND_MATERIAL_ASSUMPTION = "Материал и SDR отводов приняты как у трубы."
PROFILE_INSULATION_ASSUMPTION = (
    "Для учебного профиля принято отсутствие изоляции; основание не задано."
)
MISSING_LEVELS_ASSUMPTION = "Пропуски отметок не интерполируются."

SHARED_ASSUMPTIONS = (
    COORDINATE_SYSTEM_NOTE,
    NETWORK_AND_GROUND_ASSUMPTION,
    BEND_MATERIAL_ASSUMPTION,
    PROFILE_INSULATION_ASSUMPTION,
    MISSING_LEVELS_ASSUMPTION,
)

MISSING_DATA_NOTES = (
    "Не заданы организация, исполнители, подписи и даты в основной надписи.",
    "Не заданы поставщик, код продукции и масса единицы в спецификации.",
    "Не заданы натурная поверхность, основание, геология и УГВ.",
)
MISSING_PIPE_STANDARD_NOTE = "Не задан стандарт или ТУ на трубу; графа документа оставлена пустой."
MISSING_BEND_STANDARD_NOTE = f"{BEND_MATERIAL_ASSUMPTION} Документ на отводы не задан."
