"""Weather 工具 — 天气查询（和风天气 API + Web 搜索降级）。

支持动作：
- get_weather: 查询城市天气信息

借鉴来源：参考项目_changoai/backend/tool_functions.py get_weather()
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests as http_requests

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class WeatherTool(BaseTool):
    """天气查询工具。

    优先使用和风天气 API（需配置 QWEATHER_API_KEY 环境变量），
    API 不可用时自动降级到 Web 搜索（复用现有 search 工具逻辑）。
    """

    name = "weather"
    emoji = "🌤️"
    title = "天气查询"
    description = "查询城市天气信息，支持实时天气和未来预报"
    timeout = 30.0

    def __init__(
        self,
        api_key: str = "",
        api_host: str = "",
        fallback_to_web: bool = True,
    ):
        self._api_key = os.getenv("QWEATHER_API_KEY", "") or api_key
        self._api_host = os.getenv("QWEATHER_API_HOST", "") or api_host or "devapi.qweather.com"
        self._fallback_to_web = fallback_to_web

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="get_weather",
                description=(
                    "查询指定城市的天气信息。支持查询今天(实时)、明天、后天的天气。"
                    "返回温度、天气状况、风力、湿度等信息。"
                ),
                parameters={
                    "city": {
                        "type": "string",
                        "description": "城市名称，如 '北京'、'上海'、'广州'",
                    },
                    "date": {
                        "type": "string",
                        "description": "日期: '今天'(默认,实时天气), '明天', '后天'",
                    },
                },
                required_params=["city"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "get_weather":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await self._get_weather(params)

    async def _get_weather(self, params: dict[str, Any]) -> ToolResult:
        city = params.get("city", "").strip()
        date = params.get("date", "今天").strip()

        if not city:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="城市名称不能为空",
            )

        # 优先尝试和风天气 API
        if self._api_key and len(self._api_key) >= 20:
            result = self._query_qweather(city, date)
            if result is not None:
                return result
            logger.warning("和风天气 API 查询失败，降级到 Web 搜索")

        # 降级到 Web 搜索
        if self._fallback_to_web:
            return self._fallback_web_search(city, date)

        return ToolResult(
            status=ToolResultStatus.ERROR,
            error="天气 API 未配置且 Web 搜索降级已关闭。请设置环境变量 QWEATHER_API_KEY。",
        )

    def _query_qweather(self, city: str, date: str) -> ToolResult | None:
        """通过和风天气 API 查询天气，失败返回 None。"""
        try:
            # 1. 城市查询 — GeoAPI 路径为 /geo/v2/city/lookup（注意 /geo 前缀）
            geo_url = f"https://{self._api_host}/geo/v2/city/lookup"
            geo_params = {"location": city, "key": self._api_key, "lang": "zh"}

            resp = self._http_get(geo_url, geo_params)
            if resp is None:
                return None

            geo_data = resp
            if geo_data.get("code") != "200" or not geo_data.get("location"):
                logger.warning("GeoAPI 返回错误码: %s", geo_data.get("code"))
                return None

            loc = geo_data["location"][0]
            location_id = loc["id"]
            city_name = loc["name"]
            adm1 = loc.get("adm1", "")

            # 2. 判断查询类型
            date_norm = date.replace("天", "").replace("日", "").strip()

            if date_norm in ("今", "现在", "当前", "今天", ""):
                return self._query_now(location_id, city_name, adm1)
            else:
                day_idx = {"明": 1, "明天": 1, "后": 2, "后天": 2}.get(date_norm, 0)
                return self._query_forecast(location_id, city_name, adm1, date, day_idx)
        except Exception as e:
            logger.warning("和风天气 API 异常: %s", e)
            return None

    def _query_now(self, location_id: str, city_name: str, adm1: str) -> ToolResult | None:
        """查询实时天气。"""
        url = f"https://{self._api_host}/v7/weather/now"
        params = {"location": location_id, "key": self._api_key, "lang": "zh"}

        data = self._http_get(url, params)
        if not data or data.get("code") != "200":
            return None

        now = data["now"]
        output = (
            f"{adm1}{city_name} 今天天气：\n"
            f"天气：{now['text']}\n"
            f"温度：{now['temp']}°C（体感 {now['feelsLike']}°C）\n"
            f"风力：{now['windDir']} {now['windScale']}级\n"
            f"湿度：{now['humidity']}%"
        )
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "city": city_name,
                "weather": now["text"],
                "temperature": int(now["temp"]),
                "feels_like": int(now["feelsLike"]),
                "wind_dir": now["windDir"],
                "wind_scale": now["windScale"],
                "humidity": int(now["humidity"]),
            },
        )

    def _query_forecast(
        self, location_id: str, city_name: str, adm1: str, date_label: str, day_idx: int
    ) -> ToolResult | None:
        """查询天气预报（7 天）。"""
        url = f"https://{self._api_host}/v7/weather/7d"
        params = {"location": location_id, "key": self._api_key, "lang": "zh"}

        data = self._http_get(url, params)
        if not data or data.get("code") != "200":
            return None

        daily = data.get("daily", [])
        if day_idx >= len(daily):
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="只能查询未来 7 天内的天气",
            )

        day = daily[day_idx]
        output = (
            f"{adm1}{city_name} {date_label}天气：\n"
            f"日期：{day['fxDate']}\n"
            f"白天：{day['textDay']}\n"
            f"夜间：{day['textNight']}\n"
            f"温度：{day['tempMin']}°C ~ {day['tempMax']}°C\n"
            f"风力：{day['windDirDay']} {day['windScaleDay']}级\n"
            f"降水：{day.get('precip', '0')}mm"
        )
        if "雨" in day["textDay"] or "雨" in day["textNight"]:
            output += "\n\n记得带伞！"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "city": city_name,
                "date": day["fxDate"],
                "weather_day": day["textDay"],
                "weather_night": day["textNight"],
                "temp_min": int(day["tempMin"]),
                "temp_max": int(day["tempMax"]),
            },
        )

    def _fallback_web_search(self, city: str, date: str) -> ToolResult:
        """降级到 Web 搜索获取天气信息。"""
        search_query = f"{city}{date}天气 温度"
        output = (
            f"天气 API 未配置或请求失败，建议使用搜索工具查询：\n"
            f"搜索关键词: {search_query}\n"
            f"请调用 search 工具的 web_search 动作来获取 {city} 的天气信息。"
        )
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "city": city,
                "date": date,
                "fallback": True,
                "search_query": search_query,
            },
        )

    @staticmethod
    def _http_get(url: str, params: dict | None = None, timeout: int = 8) -> dict | None:
        """使用 requests 发起 GET 请求，自动处理 gzip 解压。"""
        try:
            resp = http_requests.get(
                url,
                params=params,
                headers={"User-Agent": "WinClaw/1.0"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.warning("HTTP %d: %s", resp.status_code, url)
                return None
            return resp.json()
        except http_requests.Timeout:
            logger.warning("HTTP 请求超时: %s", url)
            return None
        except Exception as e:
            logger.warning("HTTP 请求失败 (%s): %s", url, e)
            return None
