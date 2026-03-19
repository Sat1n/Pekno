import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_app_timezone() -> ZoneInfo:
    tz_name = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def now_in_app_timezone() -> datetime:
    return datetime.now(get_app_timezone())


def now_in_app_timezone_naive() -> datetime:
    # SQLAlchemy models currently use naive DateTime columns, so we keep
    # persistence-side values naive while ensuring the underlying timezone
    # source is stable and configurable via APP_TIMEZONE.
    return now_in_app_timezone().replace(tzinfo=None)
