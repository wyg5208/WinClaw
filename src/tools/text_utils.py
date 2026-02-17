"""文本处理工具函数

提供简繁转换等功能。
"""
import logging

logger = logging.getLogger(__name__)

# OpenCC 转换器缓存
_converter = None

# 繁体字符范围（用于快速检测）
_TRADITIONAL_CHARS = set(range(0x4E00, 0x9FFF))  # CJK统一汉字范围
# 常见的繁体字特征（比全部检测更快）
_TRADITIONAL_INDICATORS = {'臺', '灣', '國', '學', '會', '館', '電話', '電腦', '軟體', '程式',
                           '這', '那', '說', '為', '與', '門', '間', '問', '關', '開', '關',
                           '長', '發', '頭', '裡', '後', '裡', '麵', '館', '車', '馬', '魚',
                           '鳥', '蟲', '龍', '龜', '齊', '齋', '賓', '歲', '幾', '況', '愛',
                           '採', '釋', '沖', '況', '遊', '隊', '墜', '母親', '復', '蓋', '響',
                           '聽', '撲', '擊', '繳', '繞', '繪', '繫', '繽', '紛', '紙', '紋',
                           '紡', '紂', '紇', '紈', '紊', '絆', '紓', '結', '絕', '絞', '絡',
                           '給', '統計', '新聞', '分钟', '鐘', '針', '銅', '銀', '錢', '鍋',
                           '鏟', '鏟', '鎮', '鏽', '鏡', '鐵', '鐶', '鐲', '鉛', '銅', '鋼',
                           '門', '關', '開', '閉', '間', '問題', '電話', '國', '美國', '電腦'}


def _get_converter():
    """获取 OpenCC 转换器（延迟加载）"""
    global _converter
    if _converter is None:
        try:
            import opencc
            # 使用繁体到简体的标准转换配置
            # T2S: 繁体转简体
            _converter = opencc.OpenCC('t2s')
        except ImportError:
            logger.warning("opencc 未安装，简繁转换功能不可用")
            return None
        except Exception as e:
            logger.warning(f"OpenCC 初始化失败: {e}")
            return None
    return _converter


def _has_traditional_chinese(text: str) -> bool:
    """快速检测是否包含繁体中文

    使用启发式方法，避免全量检测：
    - 检查是否包含常见的繁体特征词
    - 这样可以跳过大部分纯简体文本的转换
    """
    # 先用简单特征词快速检测
    for indicator in _TRADITIONAL_INDICATORS:
        if indicator in text:
            return True
    return False


def to_simplified_chinese(text: str) -> str:
    """将文本转换为简体中文（轻量级实现）

    优化策略：
    - 快速预检：先用特征词检测是否可能为繁体
    - 延迟加载：OpenCC 只在首次使用时加载
    - 短路返回：非中文文本直接返回

    Args:
        text: 输入文本（可能是繁体或简体）

    Returns:
        转换为简体中文后的文本
    """
    if not text:
        return text

    # 非中文直接返回
    if not any('\u4e00' <= char <= '\u9fff' for char in text):
        return text

    # 快速预检：检测是否可能为繁体
    if not _has_traditional_chinese(text):
        return text

    converter = _get_converter()
    if converter is None:
        return text

    try:
        result = converter.convert(text)
        return result
    except Exception as e:
        logger.warning(f"简繁转换失败: {e}")
        return text
