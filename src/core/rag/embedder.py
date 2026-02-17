"""本地向量嵌入器 - 基于 sentence-transformers。

使用本地 Embedding 模型生成向量，支持离线使用。
默认模型: sentence-transformers/all-MiniLM-L6-v2 (384维，免费开源)

离线模式说明：
1. 先运行 download_embedding_model.py 下载模型到本地
2. 设置环境变量 EMBEDDING_MODEL_PATH 指向本地模型路径
3. 设置环境变量 TRANSFORMERS_OFFLINE=1 强制离线模式（可选）
"""

import logging
import os
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# 默认模型
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# 模型缓存目录
MODEL_CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")

# 本地模型目录（项目内置）
LOCAL_MODEL_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "embedding_models"

# 从环境变量获取本地模型路径（优先级最高）
EMBEDDING_MODEL_PATH = os.environ.get("EMBEDDING_MODEL_PATH", "")

# 是否强制离线模式（从环境变量读取，默认 True 以避免网络请求）
FORCE_OFFLINE = os.environ.get("TRANSFORMERS_OFFLINE", "1").lower() in ("1", "true", "yes")


class Embedder:
    """本地向量嵌入器。"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_folder: Optional[str] = None,
        device: Optional[str] = None,
        local_model_path: Optional[Union[str, Path]] = None,
        offline_mode: Optional[bool] = None,
    ):
        """初始化嵌入器。

        Args:
            model_name: HuggingFace 模型名称，默认 all-MiniLM-L6-v2
            cache_folder: 模型缓存目录，默认 ~/.cache/huggingface/hub
            device: 运行设备，默认自动选择 (cuda/cpu)
            local_model_path: 本地模型路径（优先级：参数 > 环境变量 > 自动检测）
            offline_mode: 是否强制离线模式（默认从环境变量读取）
        """
        self.model_name = model_name
        self.cache_folder = cache_folder or MODEL_CACHE_DIR
        self.device = device
        self._model = None
        self._embedding_function = None

        # 确定本地模型路径
        self._local_model_path = self._resolve_local_model_path(local_model_path)

        # 确定离线模式
        self._offline_mode = offline_mode if offline_mode is not None else FORCE_OFFLINE

    def _resolve_local_model_path(self, local_model_path: Optional[Union[str, Path]]) -> Optional[Path]:
        """解析本地模型路径。

        优先级：
        1. 构造函数参数 local_model_path
        2. 环境变量 EMBEDDING_MODEL_PATH
        3. 项目内置目录 resources/embedding_models/{model_name}
        4. 返回 None（使用 HuggingFace 在线模式）

        Returns:
            本地模型路径或 None
        """
        # 优先使用参数
        if local_model_path:
            path = Path(local_model_path)
            if path.exists():
                logger.info(f"📌 使用参数指定的本地模型: {path}")
                return path
            else:
                logger.warning(f"⚠️ 参数指定的路径不存在: {path}")

        # 其次使用环境变量
        if EMBEDDING_MODEL_PATH:
            path = Path(EMBEDDING_MODEL_PATH)
            if path.exists():
                logger.info(f"📌 使用环境变量指定的本地模型: {path}")
                return path
            else:
                logger.warning(f"⚠️ 环境变量指定的路径不存在: {path}")

        # 最后检查项目内置目录
        model_dir_name = self.model_name.replace("/", "_")
        builtin_path = LOCAL_MODEL_DIR / model_dir_name
        if builtin_path.exists():
            logger.info(f"📌 使用项目内置模型: {builtin_path}")
            return builtin_path

        # 没有找到本地模型，将使用在线模式
        logger.info(f"📌 未找到本地模型，将使用在线模式: {self.model_name}")
        return None

    @property
    def model(self):
        """延迟加载模型。"""
        if self._model is None:
            self._load_model()
        return self._model

    def _load_model(self) -> None:
        """加载 sentence-transformers 模型。

        优先使用本地模型，避免网络请求。
        """
        try:
            from sentence_transformers import SentenceTransformer

            # 设置离线模式环境变量（如果启用）
            if self._offline_mode:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_OFFLINE"] = "1"
                logger.info("🔒 离线模式已启用")

            # 创建缓存目录
            os.makedirs(self.cache_folder, exist_ok=True)

            # 确定要加载的模型路径
            if self._local_model_path:
                # 使用本地模型路径
                model_path = str(self._local_model_path)
                logger.info(f"📥 加载本地 Embedding 模型: {model_path}")
            else:
                # 使用模型名称（可能在线下载）
                model_path = self.model_name
                logger.info(f"📥 加载 Embedding 模型: {model_path}")

            # 加载模型
            self._model = SentenceTransformer(
                model_path,
                cache_folder=self.cache_folder,
                device=self.device,
            )
            logger.info(f"✅ Embedding 模型加载成功 (维度: {self._model.get_sentence_embedding_dimension()})")

        except ImportError:
            logger.error("❌ sentence-transformers 未安装，请运行: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"❌ 加载 Embedding 模型失败: {e}")
            logger.error("💡 提示: 如果网络不可用，请先运行 download_embedding_model.py 下载模型到本地")
            raise

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """将文本列表转换为向量。

        Args:
            texts: 文本列表
            batch_size: 批处理大小

        Returns:
            向量列表
        """
        if not texts:
            return []

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=len(texts) > 100,
                convert_to_numpy=True,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"❌ 向量化失败: {e}")
            raise

    def embed_single(self, text: str) -> list[float]:
        """将单个文本转换为向量。

        Args:
            text: 输入文本

        Returns:
            向量
        """
        embeddings = self.embed([text])
        return embeddings[0] if embeddings else []

    def get_dimension(self) -> int:
        """获取向量维度。"""
        return self.model.get_sentence_embedding_dimension()

    def is_ready(self) -> bool:
        """检查模型是否已加载。"""
        return self._model is not None


# 全局单例
_default_embedder: Optional[Embedder] = None


def get_embedder(
    model_name: str = DEFAULT_MODEL,
    cache_folder: Optional[str] = None,
    device: Optional[str] = None,
    local_model_path: Optional[Union[str, Path]] = None,
    offline_mode: Optional[bool] = None,
) -> Embedder:
    """获取全局嵌入器实例（单例模式）。

    Args:
        model_name: 模型名称
        cache_folder: 缓存目录
        device: 设备
        local_model_path: 本地模型路径
        offline_mode: 是否强制离线模式

    Returns:
        Embedder 实例
    """
    global _default_embedder

    if _default_embedder is None:
        _default_embedder = Embedder(
            model_name=model_name,
            cache_folder=cache_folder,
            device=device,
            local_model_path=local_model_path,
            offline_mode=offline_mode,
        )

    return _default_embedder


def reset_embedder() -> None:
    """重置全局嵌入器（用于测试或更换模型）。"""
    global _default_embedder
    _default_embedder = None
