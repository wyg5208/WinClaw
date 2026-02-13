"""DateTime 工具 — 获取当前日期时间，支持多种格式输出。

支持动作：
- get_datetime: 获取当前日期时间（多种格式）

借鉴来源：参考项目_changoai/backend/tool_functions.py get_datetime()
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 常用时区偏移（避免依赖 pytz）
_TIMEZONE_OFFSETS: dict[str, int] = {
    "Asia/Shanghai": 8,
    "Asia/Tokyo": 9,
    "Asia/Seoul": 9,
    "America/New_York": -5,
    "America/Los_Angeles": -8,
    "Europe/London": 0,
    "Europe/Berlin": 1,
    "UTC": 0,
}

_WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


class DateTimeTool(BaseTool):
    """日期时间工具。

    获取当前日期时间，支持多种格式输出：
    full / date / time / datetime_cn / weekday / timestamp / all
    """

    name = "datetime_tool"
    emoji = "🕐"
    title = "日期时间"
    description = "获取当前日期时间，支持多种格式和时区"

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="get_datetime",
                description=(
                    "获取当前日期时间。format_type 可选值: "
                    "'full'(完整日期时间), 'date'(仅日期), 'time'(仅时间), "
                    "'datetime_cn'(中文格式), 'weekday'(星期几), "
                    "'timestamp'(时间戳), 'all'(所有格式)"
                ),
                parameters={
                    "format_type": {
                        "type": "string",
                        "description": "输出格式: full/date/time/datetime_cn/weekday/timestamp/all",
                        "enum": ["full", "date", "time", "datetime_cn", "weekday", "timestamp", "all"],
                    },
                    "timezone": {
                        "type": "string",
                        "description": "时区，如 'Asia/Shanghai'(默认)、'UTC'、'America/New_York' 等",
                    },
                },
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "get_datetime":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return self._get_datetime(params)

    def _get_datetime(self, params: dict[str, Any]) -> ToolResult:
        format_type = params.get("format_type", "full").strip()
        tz_name = params.get("timezone", "Asia/Shanghai").strip()

        # 获取指定时区的当前时间
        offset_hours = _TIMEZONE_OFFSETS.get(tz_name, 8)  # 默认东八区
        tz = timezone(timedelta(hours=offset_hours))
        now = datetime.now(tz)

        weekday_cn = _WEEKDAY_CN[now.weekday()]

        try:
            if format_type == "full":
                result_str = now.strftime("%Y-%m-%d %H:%M:%S")
                output = f"当前时间: {result_str}"
                data = {"datetime": result_str, "timezone": tz_name}

            elif format_type == "date":
                result_str = now.strftime("%Y-%m-%d")
                output = f"今天日期: {result_str}"
                data = {"date": result_str}

            elif format_type == "time":
                result_str = now.strftime("%H:%M:%S")
                output = f"当前时间: {result_str}"
                data = {"time": result_str}

            elif format_type == "datetime_cn":
                result_str = (
                    f"{now.year}年{now.month}月{now.day}日 "
                    f"{now.hour}时{now.minute}分 星期{weekday_cn}"
                )
                output = result_str
                data = {"datetime_cn": result_str}

            elif format_type == "weekday":
                weekday_en = calendar.day_name[now.weekday()]
                output = f"今天是星期{weekday_cn} ({weekday_en})"
                data = {"weekday_cn": f"星期{weekday_cn}", "weekday_en": weekday_en}

            elif format_type == "timestamp":
                ts = int(now.timestamp())
                output = f"时间戳: {ts}"
                data = {"timestamp": ts}

            elif format_type == "all":
                full = now.strftime("%Y-%m-%d %H:%M:%S")
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M:%S")
                cn = (
                    f"{now.year}年{now.month}月{now.day}日 "
                    f"{now.hour}时{now.minute}分"
                )
                ts = int(now.timestamp())
                weekday_en = calendar.day_name[now.weekday()]

                output = (
                    f"当前日期时间\n"
                    f"完整格式: {full}\n"
                    f"日期: {date_str}\n"
                    f"时间: {time_str}\n"
                    f"星期: 星期{weekday_cn} ({weekday_en})\n"
                    f"中文: {cn}\n"
                    f"时间戳: {ts}\n"
                    f"时区: {tz_name}"
                )
                data = {
                    "full": full,
                    "date": date_str,
                    "time": time_str,
                    "weekday_cn": f"星期{weekday_cn}",
                    "weekday_en": weekday_en,
                    "datetime_cn": cn,
                    "timestamp": ts,
                    "timezone": tz_name,
                }
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"不支持的格式类型: {format_type}。可选: full/date/time/datetime_cn/weekday/timestamp/all",
                )

            logger.info("获取日期时间: format=%s, tz=%s", format_type, tz_name)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                data=data,
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"获取日期时间失败: {e}",
            )
