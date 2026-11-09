from collections import Counter

from config import drawing_settings as settings
from core.models import DocumentId
from core.sheet import Sheet


class DocumentSet:
    """Состав выпуска и нумерация по каждому обозначению документа."""

    def __init__(self, project, config):
        self.items = [dict(item) for item in config["documents"] if item["id"] != "report"]
        counts = Counter(item["suffix"] for item in self.items)
        positions = Counter()
        for item in self.items:
            item["id"] = DocumentId(item["id"])
            item["title"] = item["title"].replace("{network_code}", settings.NETWORK_CODE)
            item["short_title"] = item.get("short_title", item["title"])
            item["paper"] = Sheet.paper
            suffix = item["suffix"]
            positions[suffix] += 1
            item["designation"] = project.object.project_code + suffix
            item["number"] = positions[suffix] if counts[suffix] > 1 else ""
            item["total"] = counts[suffix] if positions[suffix] == 1 else ""

    def get(self, document_id):
        return next(item for item in self.items if item["id"] == document_id)
