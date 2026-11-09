from pathlib import Path


# Ресурсы программы находятся рядом с установленными пакетами.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
FONT_PATH = PACKAGE_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
# Входные данные, ключ и результаты принадлежат текущей папке запуска.
PROJECT_ROOT = Path.cwd()
