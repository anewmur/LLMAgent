import csv
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.calculations import calculate_point_levels, calculate_route_geometry
from core.formatting import format_number, format_station
from core.sheet import Sheet


NS = {"s": "http://www.w3.org/2000/svg"}


class PackageChecks:
    """Прямые проверки готовых файлов: при первом расхождении — причина ошибки."""

    def __init__(self, project, documents, folder):
        self.project, self.documents, self.folder = project, documents, Path(folder)
        self.geometry = calculate_route_geometry(project.points)
        self.levels = calculate_point_levels(project.points, project.pipe.outer_diameter_mm)
        self.stations = [0] + [s["cumsum_dist_m"] for s in self.geometry["sections"]]
        self.results, self.roots = [], {}

    def add(self, name, passed, detail):
        self.results.append({"id": name, "passed": passed, "detail": detail})

    def check_sheets(self):
        for doc in self.documents.items:
            stem = "specification" if doc["id"] == "spec" else doc["id"]
            root = ET.parse(self.folder / f"{stem}.svg").getroot()
            self.roots[doc["id"]] = root
            self.check_sheet_geometry(doc, root)
            self.check_sheet_text(doc, root)

    def check_sheet_geometry(self, doc, root):
        name = "sheet_" + doc["id"]
        width, height = Sheet.width, Sheet.height
        if root.get("viewBox") != f"0 0 {width} {height}":
            self.add(name, False, "Неверный размер SVG-листа.")
            return
        frame = root.find("s:g/s:rect[@id='frame']", NS)
        if [float(frame.get(k)) for k in ["x", "y", "width", "height"]] != [20, 5, width-25, height-10]:
            self.add(name, False, "Поля рамки не соответствуют 20/5 мм.")
            return
        stamp = root.find("s:g/s:rect[@id='title-block']", NS)
        if [float(stamp.get(k)) for k in ["x", "y", "width", "height"]] != [width-190, height-60, 185, 55]:
            self.add(name, False, "Неверный размер или положение штампа 185×55 мм.")
            return
        self.add(name, True, "Размер листа, рамка и штамп верны.")

    def check_sheet_text(self, doc, root):
        name = "stamp_" + doc["id"]
        text = "".join("".join(root.itertext()).split())
        for value in [doc["designation"], doc["title"], "УЧЕБНЫЙ КОМПЛЕКТ", "Формат " + doc["paper"]]:
            if "".join(value.split()) not in text:
                self.add(name, False, "В листе отсутствует реквизит: " + value)
                return
        for x, expected in [("157.5", doc["number"]), ("175", doc["total"])]:
            cell = root.find(f".//s:text[@x='{x}'][@y='36.5']", NS)
            if (cell.text or "") != str(expected):
                self.add(name, False, "Номер листа или число листов не совпадает с составом выпуска.")
                return
        self.add(name, True, "Реквизиты и нумерация совпадают с составом выпуска.")

    def check_plan_geometry(self):
        line = self.roots["plan"].find(".//s:polyline[@id='route-line']", NS)
        xy = [tuple(map(float, p.split(","))) for p in line.get("points").split()]
        if len(xy) != len(self.project.points):
            self.add("plan_geometry", False, "Количество точек плана не совпадает с исходными данными.")
            return
        for i, section in enumerate(self.geometry["sections"]):
            a, b = xy[i:i+2]
            if not math.isclose(math.dist(a, b), section["length_m"], abs_tol=1e-7):
                self.add("plan_geometry", False, "Длина участка плана неверна при масштабе 1:1000.")
                return
            start, end = self.project.points[i:i+2]
            if not math.isclose(b[0]-a[0], end.x-start.x, abs_tol=1e-7):
                self.add("plan_geometry", False, "Неверное направление или расстояние по X на плане.")
                return
            if not math.isclose(b[1]-a[1], start.y-end.y, abs_tol=1e-7):
                self.add("plan_geometry", False, "Неверное направление или расстояние по Y на плане.")
                return
        self.add("plan_geometry", True, "Геометрия плана соответствует координатам и масштабу 1:1000.")

    def check_plan_labels(self):
        root = self.roots["plan"]
        line = root.find(".//s:polyline[@id='route-line']", NS)
        if line.get("stroke-dasharray") != "6 2" or root.find("s:g[@id='plan-legend']", NS) is None:
            self.add("plan_labels", False, "Отсутствует легенда или штриховая линия трубы.")
            return
        stations = root.findall(".//s:text[@data-kind='station']", NS)
        if [e.text for e in stations] != [format_station(s) for s in self.stations]:
            self.add("plan_labels", False, "Пикетаж плана не совпадает с расчётом.")
            return
        lengths = root.findall(".//s:text[@data-kind='length']", NS)
        if [e.text for e in lengths] != [format_number(s["length_m"]) for s in self.geometry["sections"]]:
            self.add("plan_labels", False, "Подписи длин участков плана не совпадают с расчётом.")
            return
        self.add("plan_labels", True, "Пикеты, длины, легенда и линия трубы присутствуют.")

    def check_plan_coordinates(self):
        labels = self.roots["plan"].findall(".//s:text[@data-kind='coordinates']", NS)
        expected = [(p.id, f"X={format_number(p.x)}, Y={format_number(p.y)}") for p in self.project.points]
        if [(e.get("data-point-id"), e.text) for e in labels] != expected:
            self.add("coordinates", False, "Координаты у точек плана не совпадают с исходными данными.")
            return
        self.add("coordinates", True, "У каждой точки плана подписаны её исходные X и Y.")

    def check_profile_values(self):
        root = self.roots["profile"]
        expected = {"bottom-level": [format_number(p["bottom_m"]) for p in self.levels],
                    "ground-level": [format_number(p.ground) for p in self.project.points],
                    "station": [format_station(s) for s in self.stations],
                    "slope": [format_number(s["slope_per_mille"]) for s in self.geometry["sections"]],
                    "distance": [format_number(s["length_m"]) for s in self.geometry["sections"]]}
        for kind, values in expected.items():
            found = root.findall(f".//s:text[@data-kind='{kind}']", NS)
            if [e.text for e in found] != values:
                self.add("profile_values", False, "Значения профиля не совпадают с расчётом: " + kind)
                return
        depths = {p["point_id"]: format_number(p["depth_to_bottom_m"]) for p in self.levels}
        for element in root.findall(".//s:text[@data-kind='depth']", NS):
            if element.text != depths[element.get("data-point-id")]:
                self.add("profile_values", False, "Глубина на профиле не совпадает с расчётом.")
                return
        self.add("profile_values", True, "Отметки, глубины, уклоны, расстояния и пикеты совпадают с расчётом.")

    def profile_points(self, values, left, baseline, datum):
        xy, commands, connected = [], [], False
        for station, value in zip(self.stations, values):
            if value is None:
                connected = False
                continue
            xy.append((left + 76 + station * 0.5, baseline - (value-datum)*10))
            commands.append("L" if connected else "M")
            connected = True
        return xy, commands

    def check_profile_line(self, line_id, values):
        root = self.roots["profile"]
        group = root.find("s:g[@id='profile-geometry']", NS)
        grid = root.find("s:g[@id='profile-grid']", NS)
        left, baseline = map(float, re.findall(r'-?\d+(?:\.\d+)?', grid.get("transform")))
        expected, commands = self.profile_points(values, left, baseline, float(group.get("data-datum-m")))
        tokens = group.find(f"s:path[@id='{line_id}']", NS).get("d").split()
        actual = [tuple(map(float, item.split(","))) for item in tokens[1::2]]
        if tokens[::2] != commands or len(actual) != len(expected):
            self.add(line_id, False, "Неверное число точек или разрывы линии профиля.")
            return
        if not all(math.dist(a, b) < 1e-7 for a, b in zip(actual, expected)):
            self.add(line_id, False, "Положение линии профиля не совпадает с отметками и пикетами.")
            return
        self.add(line_id, True, "Линия профиля соответствует отметкам; пропуски не соединены.")

    def check_profile_geometry(self):
        group = self.roots["profile"].find("s:g[@id='profile-geometry']", NS)
        if group.get("data-horizontal-scale") != "2000" or group.get("data-vertical-scale") != "100":
            self.add("profile_scale", False, "Масштабы профиля отличаются от 1:2000 и 1:100.")
            return
        self.add("profile_scale", True, "Масштабы профиля 1:2000 и 1:100.")
        self.check_profile_line("ground-line", [p.ground for p in self.project.points])
        self.check_profile_line("pipe-bottom-line", [p["bottom_m"] for p in self.levels])
        top = group.find("s:path[@id='pipe-top-line']", NS)
        diameter = self.project.pipe.outer_diameter_mm
        if diameter / 100 >= 2:
            self.check_profile_line("pipe-top-line", [None if p["bottom_m"] is None else
                                    p["bottom_m"] + diameter / 1000 for p in self.levels])
        elif top is not None:
            self.add("pipe-top-line", False, "При диаметре менее 2 мм в масштабе должен быть один контур.")

    def check_spec_rows(self, rows):
        for i, row in enumerate(rows, 1):
            group = self.roots["spec"].find(f".//s:g[@id='spec-row-{i}']", NS)
            text = " ".join(" ".join(group.itertext()).split())
            if not all(value in text for value in row if value):
                self.add("spec_rows", False, f"Строка {i} спецификации различается в CSV и SVG.")
                return
        self.add("spec_rows", True, "Строки CSV и SVG спецификации совпадают.")

    def check_quantities(self):
        with (self.folder / "specification.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))[1:]
        pipes = [r for r in rows if r[5] == "м"]
        bends = [r for r in rows if r[5] == "шт."]
        if len(pipes) != 1 or pipes[0][6] != format_number(self.geometry["length_m"]):
            self.add("quantities", False, "Количество трубы не равно расчётной длине трассы.")
            return
        if sum(int(row[6]) for row in bends) != len(self.project.bends):
            self.add("quantities", False, "Количество отводов не совпадает с исходными данными.")
            return
        if not math.isclose(sum(s["length_m"] for s in self.geometry["sections"]), self.geometry["length_m"]):
            self.add("quantities", False, "Сумма неокруглённых участков не равна длине трассы.")
            return
        self.add("quantities", True, "Количество трубы и отводов совпадает с расчётом.")
        self.check_spec_rows(rows)

    def check_general(self):
        root = self.roots["general"]
        register = root.find(".//s:g[@id='drawing-register']", NS)
        text = "".join("".join(register.itertext()).split())
        for doc in self.documents.items:
            if doc["suffix"] == "-НВ" and "".join(doc["title"].split()) not in text:
                self.add("general", False, "В ведомости отсутствует лист: " + doc["title"])
                return
        references = root.find(".//s:g[@id='reference-register']", NS)
        if self.documents.get("spec")["designation"] not in "".join(references.itertext()):
            self.add("general", False, "Спецификация не записана в прилагаемые документы.")
            return
        self.add("general", True, "Ведомости содержат фактические листы НВ и отдельную СО.")

    def pdf_values(self, document_id):
        if document_id == "spec":
            return [format_number(self.geometry["length_m"])]
        if document_id == "general":
            return [doc["title"] for doc in self.documents.items if doc["suffix"] == "-НВ"]
        values = [format_station(s) for s in self.stations]
        values += [format_number(s["length_m"]) for s in self.geometry["sections"]]
        if document_id == "profile":
            values += [format_number(p["bottom_m"]) for p in self.levels if p["bottom_m"] is not None]
            values += [format_number(s["slope_per_mille"]) for s in self.geometry["sections"] if s["slope_per_mille"] is not None]
        if document_id == "plan":
            values += [f"X={format_number(p.x)}, Y={format_number(p.y)}" for p in self.project.points]
        return values

    def check_pdf_font(self, doc, page, text):
        name = "font_" + doc["id"]
        if "⌀" not in text:
            self.add(name, False, "В PDF отсутствует знак диаметра.")
            return
        fonts = page["/Resources"]["/Font"].values()
        if not any("DejaVuSans" in str(font.get_object().get("/BaseFont")) for font in fonts):
            self.add(name, False, "В PDF не встроен DejaVu Sans для знака диаметра.")
            return
        self.add(name, True, "Знак диаметра и шрифт DejaVu Sans присутствуют в PDF.")

    def check_pdf_page(self, doc):
        name = "pdf_" + doc["id"]
        stem = "specification" if doc["id"] == "spec" else doc["id"]
        reader = PdfReader(self.folder / "pdf" / f"{stem}.pdf")
        if len(reader.pages) != 1:
            self.add(name, False, "В PDF листа должно быть ровно по одной странице.")
            return
        page = reader.pages[0]
        width, height = Sheet.width, Sheet.height
        if abs(float(page.mediabox.width)*25.4/72-width) >= 0.02 or abs(float(page.mediabox.height)*25.4/72-height) >= 0.02:
            self.add(name, False, "Размер страницы PDF не совпадает с форматом листа.")
            return
        text = page.extract_text()
        if doc["designation"] not in text or "УЧЕБНЫЙ КОМПЛЕКТ" not in text:
            self.add(name, False, "В PDF отсутствует обозначение или учебная надпись.")
            return
        compact = "".join(text.split())
        for value in self.pdf_values(doc["id"]):
            if "".join(value.split()) not in compact:
                self.add(name, False, "В PDF отсутствует значение: " + value)
                return
        self.add(name, True, "PDF открывается, размер страницы и значения верны.")
        if doc["id"] in ["plan", "profile"]:
            self.check_pdf_font(doc, page, text)

    def check_pdf(self):
        for doc in self.documents.items:
            self.check_pdf_page(doc)
        if len(PdfReader(self.folder / "pdf" / "package.pdf").pages) != len(self.documents.items):
            self.add("merged_pdf", False, "Неверное число страниц: package.pdf")
            return
        self.add("merged_pdf", True, "Количество страниц package.pdf совпадает с составом выпуска.")

    def run(self):
        for check in [self.check_sheets, self.check_plan_geometry, self.check_plan_labels,
                      self.check_plan_coordinates, self.check_profile_values, self.check_profile_geometry,
                      self.check_quantities, self.check_general, self.check_pdf]:
            try:
                check()
            except (OSError, ValueError, AttributeError, IndexError, KeyError, ET.ParseError, PdfReadError) as error:
                self.add(check.__name__, False, str(error))
        return self.results
