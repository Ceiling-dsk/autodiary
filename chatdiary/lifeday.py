from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import config


def life_day(ts: float, tz: str = config.TIMEZONE, start_hour: int = config.DAY_START_HOUR) -> str:
    """Unix 时间戳 → 所属生活日（YYYY-MM-DD）。"""
    local = datetime.fromtimestamp(ts, ZoneInfo(tz))
    return (local - timedelta(hours=start_hour)).date().isoformat()


def window(day: str, tz: str = config.TIMEZONE, start_hour: int = config.DAY_START_HOUR) -> tuple[datetime, datetime]:
    """生活日的 [开始, 结束) 本地时间。夏令时切换日可能是 23 或 25 小时。"""
    d = date.fromisoformat(day)
    zone = ZoneInfo(tz)
    start = datetime.combine(d, time(start_hour), zone)
    end = datetime.combine(d + timedelta(days=1), time(start_hour), zone)
    return start, end
