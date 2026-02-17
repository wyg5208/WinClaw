"""AI 图像生成工具 — 基于智谱 CogView-4 系列生成图像。

支持模型：
- cogview-4-250304: 最新模型，支持 HD 模式
- cogview-4: 标准模型
- cogview-3-flash: 快速模型

支持尺寸：
- 1024x1024 (默认), 768x1344, 864x1152, 1344x768, 1152x864, 1440x720, 720x1440
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 支持的尺寸白名单
VALID_SIZES = {
    "1024x1024", "768x1344", "864x1152",
    "1344x768", "1152x864", "1440x720", "720x1440"
}

# 支持的模型白名单
VALID_MODELS = ["cogview-4-250304", "cogview-4", "cogview-3-flash"]

# 支持 hd 质量的模型
HD_QUALITY_MODELS = ["cogview-4-250304"]

# Prompt 最大长度
MAX_PROMPT_LENGTH = 2000

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1  # 秒


def _validate_size(size: str) -> bool:
    """校验尺寸合法性。"""
    if size not in VALID_SIZES:
        return False
    try:
        w, h = map(int, size.split('x'))
        return 512 <= w <= 2048 and 512 <= h <= 2048 and w % 16 == 0 and h % 16 == 0
    except Exception:
        return False


class ImageGeneratorTool(BaseTool):
    """AI 图像生成工具。

    调用智谱 CogView-4 系列 API 生成图片，支持多种尺寸和质量选项。
    """

    name = "image_generator"
    emoji = "🎨"
    title = "AI绘图"
    description = "基于智谱 CogView-4 系列生成 AI 图像"
    timeout = 60  # 图像生成可能较慢（5-20秒）

    def __init__(self, api_key: str = "") -> None:
        """初始化图像生成工具。

        Args:
            api_key: 智谱 API Key，优先使用传入值，其次从环境变量 GLM_API_KEY 获取
        """
        super().__init__()
        self.api_key = api_key or os.getenv("GLM_API_KEY", "")
        # 直接使用带日期的子目录，避免重复复制
        self.output_dir = Path(__file__).parent.parent.parent / "generated" / datetime.now().strftime("%Y-%m-%d")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="generate_image",
                description=(
                    "生成 AI 图像。基于智谱 CogView-4 系列模型，支持多种尺寸和质量。"
                    "支持的尺寸: 1024x1024(默认), 768x1344, 864x1152, 1344x768, 1152x864, 1440x720, 720x1440。"
                    "支持的模型: cogview-4-250304(默认), cogview-4, cogview-3-flash。"
                    "质量选项: standard(默认), hd(仅 cogview-4-250304 支持，高清模式)。"
                ),
                parameters={
                    "prompt": {
                        "type": "string",
                        "description": "图片描述，建议详细描述场景、物体、风格等，至少10个字符",
                    },
                    "size": {
                        "type": "string",
                        "description": "图片尺寸，默认 1024x1024",
                        "enum": list(VALID_SIZES),
                    },
                    "model": {
                        "type": "string",
                        "description": "模型名称，默认 cogview-4-250304",
                        "enum": VALID_MODELS,
                    },
                    "quality": {
                        "type": "string",
                        "description": "图片质量，默认 standard（仅 cogview-4-250304 支持 hd）",
                        "enum": ["standard", "hd"],
                    },
                },
                required_params=["prompt"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "generate_image":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return self._generate_image(params)

    def _generate_image(self, params: dict[str, Any]) -> ToolResult:
        """生成图像的核心逻辑。"""
        # 1. API Key 预检
        if not self.api_key:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未配置 GLM_API_KEY，请在环境变量或设置中配置智谱API密钥",
            )

        # 2. 参数校验 - Prompt
        prompt = params.get("prompt", "").strip()
        if not prompt:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="提示词不能为空",
            )
        if len(prompt) < 10:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="提示词至少需要10个字符",
            )
        if len(prompt) > MAX_PROMPT_LENGTH:
            prompt = prompt[:MAX_PROMPT_LENGTH]  # 截断超长 prompt
            logger.warning("Prompt 长度超过 %d 字符，已截断", MAX_PROMPT_LENGTH)

        # 3. 参数校验 - 尺寸
        size = params.get("size", "1024x1024")
        if not _validate_size(size):
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的尺寸: {size}，支持 {', '.join(VALID_SIZES)}",
            )

        # 4. 参数校验 - 模型
        model = params.get("model", "cogview-4-250304")
        if model not in VALID_MODELS:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的模型: {model}，支持 {', '.join(VALID_MODELS)}",
            )

        # 5. 参数校验 - 质量
        quality = params.get("quality", "standard")
        if quality == "hd" and model not in HD_QUALITY_MODELS:
            # 非支持模型使用 hd 质量时，降级为 standard
            logger.info("模型 %s 不支持 hd 质量，已降级为 standard", model)
            quality = "standard"

        # 6. 调用智谱 API（带重试机制）
        image_url = None
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            try:
                client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://open.bigmodel.cn/api/paas/v4/",
                )

                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                )

                image_url = response.data[0].url
                break  # 成功，跳出重试循环
                
            except Exception as e:
                last_error = e
                logger.warning("第 %d/%d 次尝试失败: %s", attempt + 1, MAX_RETRIES, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                continue

        if not image_url:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"API 调用失败: {last_error}",
            )

        # 7. 下载图片到本地
        try:
            img_data = requests.get(image_url, timeout=30).content
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"图片下载失败: {e}",
            )

        # 8. 保存到 generated/ 目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"img_{timestamp}.png"
        save_path = self.output_dir / filename
        save_path.write_bytes(img_data)

        file_size = len(img_data)
        
        # 9. 生成 HTML 图片标签（用于 GUI 显示）
        import base64
        b64_img = base64.b64encode(img_data).decode("utf-8")
        html_image = (
            f'<img src="data:image/png;base64,{b64_img}" '
            f'alt="{filename}" width="{min(512, int(size.split("x")[0]) // 2)}" />'
        )
        
        logger.info(
            "图片生成成功: %s (%s, %s, %d bytes)",
            filename, model, size, file_size
        )

        # 10. 返回结果
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=(
                f"✅ 图片已生成\n"
                f"📁 文件: {filename}\n"
                f"📐 尺寸: {size}\n"
                f"🤖 模型: {model}\n"
                f"📊 大小: {file_size:,} bytes"
            ),
            data={
                "file_path": str(save_path),
                "file_name": filename,
                "image_url": image_url,
                "model": model,
                "size": size,
                "quality": quality,
                "file_size": file_size,
                "html_image": html_image,  # 用于 GUI 直接显示
                "base64_image": b64_img,  # base64 编码图片
            },
        )


# 用于测试
if __name__ == "__main__":
    import asyncio
    
    async def test():
        tool = ImageGeneratorTool()
        
        # 测试 API Key 检查
        print("=== 测试1: API Key 未配置 ===")
        result = await tool.execute("generate_image", {
            "prompt": "一只可爱的小猫"
        })
        print(result.output if result.error else result.error)
        
        # 测试空 prompt
        print("\n=== 测试2: 空 Prompt ===")
        tool.api_key = "test_key"  # 模拟有 key
        result = await tool.execute("generate_image", {
            "prompt": ""
        })
        print(result.error)
        
        # 测试无效尺寸
        print("\n=== 测试3: 无效尺寸 ===")
        result = await tool.execute("generate_image", {
            "prompt": "一只可爱的小猫坐在草地上",
            "size": "999x999"
        })
        print(result.error)
        
        # 测试无效模型
        print("\n=== 测试4: 无效模型 ===")
        result = await tool.execute("generate_image", {
            "prompt": "一只可爱的小猫坐在草地上",
            "model": "invalid_model"
        })
        print(result.error)
        
        # 测试有效参数
        print("\n=== 测试5: 有效参数(需真实API) ===")
        print("跳过实际API调用测试")
    
    asyncio.run(test())
