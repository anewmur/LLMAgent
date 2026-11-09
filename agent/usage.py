from dataclasses import dataclass
from datetime import datetime, timezone

from agent import settings
from core.formatting import format_number


def utc_now():
    """Возвращает текущее время ответа API в UTC."""
    return datetime.now(timezone.utc)


@dataclass
class TokenUsage:
    """Сумма токенов API и оценка их стоимости по выбранному тарифу."""

    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, usage, timestamp=None):
        """Добавляет usage ответа API; без разбивки весь вход считается без кэша."""
        if usage is None:
            return
        hit = getattr(usage, "prompt_cache_hit_tokens", None)
        miss = getattr(usage, "prompt_cache_miss_tokens", None)
        if hit is None or miss is None:
            hit, miss = 0, getattr(usage, "prompt_tokens", 0) or 0
        self.prompt_cache_hit_tokens += hit
        self.prompt_cache_miss_tokens += miss
        output = getattr(usage, "completion_tokens", 0) or 0
        self.completion_tokens += output
        timestamp = timestamp or utc_now()
        self.cost_usd += self.response_cost(hit, miss, output, timestamp)

    @staticmethod
    def response_cost(hit, miss, output, timestamp):
        """Считает стоимость одного ответа по его времени UTC, без учёта праздников."""
        peak = timestamp.weekday() in settings.PEAK_WEEKDAYS and any(
            start <= timestamp.hour < end for start, end in settings.PEAK_HOURS_UTC)
        hit_price = settings.PRICE_INPUT_CACHE_HIT_PER_M if peak else settings.PRICE_INPUT_CACHE_HIT_OFF_PEAK_PER_M
        miss_price = settings.PRICE_INPUT_CACHE_MISS_PER_M if peak else settings.PRICE_INPUT_CACHE_MISS_OFF_PEAK_PER_M
        output_price = settings.PRICE_OUTPUT_PER_M if peak else settings.PRICE_OUTPUT_OFF_PEAK_PER_M
        return (hit * hit_price + miss * miss_price + output * output_price) / settings.TOKENS_PER_PRICE_UNIT

    def summary(self, template, elapsed, **values):
        """Форматирует итог с общими единицами и точностью вывода."""
        return template.format(elapsed=format_number(elapsed),
                               input_tokens=format_number(self.prompt_cache_hit_tokens + self.prompt_cache_miss_tokens, 0),
                               cache_tokens=format_number(self.prompt_cache_hit_tokens, 0),
                               output_tokens=format_number(self.completion_tokens, 0),
                               cost=format_number(self.cost_usd, 6), **values)
