# -*- coding: utf-8 -*-
"""标准五位 Cron 表达式解析。仅支持标准字段语法，不包含扩展字段。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CronField:
    values: frozenset[int]
    wildcard: bool


def _parse_field(expression: str, minimum: int, maximum: int, *, sunday: bool = False) -> CronField:
    expression = expression.strip()
    if not expression:
        raise ValueError("Cron 字段不能为空")

    values: set[int] = set()
    wildcard = expression == "*"
    for part in expression.split(","):
        if not part:
            raise ValueError("Cron 列表中存在空字段")
        base, slash, step_text = part.partition("/")
        if slash:
            if not step_text.isdigit() or int(step_text) <= 0:
                raise ValueError(f"无效的 Cron 步长：{part}")
            step = int(step_text)
        else:
            step = 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"无效的 Cron 范围：{part}")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Cron 范围起点大于终点：{part}")
        else:
            if not base.isdigit():
                raise ValueError(f"无效的 Cron 数值：{part}")
            start = int(base)
            end = maximum if slash else start
        if start < minimum or end > maximum:
            raise ValueError(f"Cron 数值超出范围：{part}（允许 {minimum}～{maximum}）")
        values.update(range(start, end + 1, step))

    if sunday and 7 in values:
        values.discard(7)
        values.add(0)
    if not values:
        raise ValueError("Cron 字段没有可执行的值")
    return CronField(frozenset(values), wildcard)


@dataclass(frozen=True)
class CronExpression:
    minute: CronField
    hour: CronField
    day: CronField
    month: CronField
    weekday: CronField

    @classmethod
    def parse(cls, expression: str) -> "CronExpression":
        fields = str(expression or "").split()
        if len(fields) != 5:
            raise ValueError("Cron 必须是标准五位格式：分 时 日 月 星期")
        return cls(
            _parse_field(fields[0], 0, 59),
            _parse_field(fields[1], 0, 23),
            _parse_field(fields[2], 1, 31),
            _parse_field(fields[3], 1, 12),
            _parse_field(fields[4], 0, 7, sunday=True),
        )

    def matches(self, value: datetime) -> bool:
        if value.minute not in self.minute.values:
            return False
        if value.hour not in self.hour.values:
            return False
        if value.month not in self.month.values:
            return False
        day_match = value.day in self.day.values
        # 与常见 Unix/Vixie Cron 一致：日和星期都受限时采用 OR。
        weekday = (value.weekday() + 1) % 7  # Python Monday=0，Cron Sunday=0
        weekday_match = weekday in self.weekday.values
        if not self.day.wildcard and not self.weekday.wildcard:
            return day_match or weekday_match
        return day_match and weekday_match

    def next_after(self, after: datetime) -> datetime:
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # 最多搜索 8 年，覆盖闰日等常见合法日历组合。
        limit = candidate + timedelta(days=366 * 8)
        while candidate <= limit:
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError("Cron 表达式在未来 8 年内没有可执行时间")


def validate_cron(expression: str) -> bool:
    try:
        CronExpression.parse(expression)
        return True
    except (TypeError, ValueError):
        return False
