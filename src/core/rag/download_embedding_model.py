"""下载 Embedding 模型到本地，用于离线使用。

运行此脚本后，模型将被下载到本地，之后可以完全离线运行。

使用方法:
    python -m src.core.rag.download_embedding_model
    或者
    python winclaw/src/core/rag/download_embedding_model.py
"""

import os
import shutil
from pathlib import Path


# 默认模型
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# 本地模型存储目录（放在项目的 resources 目录下）
LOCAL_MODEL_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "embedding_models"


def download_model(model_name: str = DEFAULT_MODEL, force: bool = False) -> Path:
    """下载模型到本地目录。

    Args:
        model_name: HuggingFace 模型名称
        force: 是否强制重新下载

    Returns:
        本地模型路径
    """
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import RepositoryNotFoundError

    # 将模型名转换为目录名（替换 / 为 _）
    model_dir_name = model_name.replace("/", "_")
    local_path = LOCAL_MODEL_DIR / model_dir_name

    if local_path.exists() and not force:
        print(f"✅ 模型已存在: {local_path}")
        return local_path

    print(f"📥 开始下载模型: {model_name}")
    print(f"📁 目标路径: {local_path}")

    try:
        # 下载模型到本地
        downloaded_path = snapshot_download(
            repo_id=model_name,
            local_dir=str(local_path),
            local_dir_use_symlinks=False,  # Windows 上避免符号链接问题
            resume_download=True,
        )
        print(f"✅ 模型下载完成: {downloaded_path}")
        return Path(downloaded_path)

    except RepositoryNotFoundError:
        print(f"❌ 模型不存在: {model_name}")
        raise
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        raise


def verify_model(model_path: Path) -> bool:
    """验证模型文件是否完整。

    Args:
        model_path: 模型路径

    Returns:
        是否完整
    """
    required_files = [
        "config.json",
        "pytorch_model.bin",  # 或 model.safetensors
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
        "special_tokens_map.json",
    ]

    # 检查至少存在一种模型文件
    has_model = (model_path / "pytorch_model.bin").exists() or \
                (model_path / "model.safetensors").exists()

    if not has_model:
        print(f"❌ 缺少模型权重文件")
        return False

    # 检查配置文件
    if not (model_path / "config.json").exists():
        print(f"❌ 缺少 config.json")
        return False

    # 检查 tokenizer 文件
    if not (model_path / "tokenizer.json").exists():
        print(f"⚠️ 警告: 缺少 tokenizer.json")

    print(f"✅ 模型文件验证通过")
    return True


def get_model_info(model_path: Path) -> dict:
    """获取模型信息。

    Args:
        model_path: 模型路径

    Returns:
        模型信息字典
    """
    import json

    info = {
        "path": str(model_path),
        "exists": model_path.exists(),
    }

    config_path = model_path / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            info["hidden_size"] = config.get("hidden_size")
            info["max_position_embeddings"] = config.get("max_position_embeddings")
            info["model_type"] = config.get("model_type")

    # 计算目录大小
    if model_path.exists():
        total_size = sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file())
        info["size_mb"] = round(total_size / 1024 / 1024, 2)

    return info


def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="下载 Embedding 模型到本地")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"模型名称，默认: {DEFAULT_MODEL}"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="只显示模型信息，不下载"
    )

    args = parser.parse_args()

    model_dir_name = args.model.replace("/", "_")
    local_path = LOCAL_MODEL_DIR / model_dir_name

    if args.info:
        info = get_model_info(local_path)
        print("\n📋 模型信息:")
        for key, value in info.items():
            print(f"  {key}: {value}")
        return

    # 确保目录存在
    LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 下载模型
    model_path = download_model(args.model, force=args.force)

    # 验证模型
    if verify_model(model_path):
        info = get_model_info(model_path)
        print(f"\n📋 模型信息:")
        print(f"  路径: {info['path']}")
        print(f"  大小: {info.get('size_mb', 'N/A')} MB")
        print(f"\n💡 使用方法:")
        print(f"  在 embedder.py 中设置:")
        print(f"  LOCAL_MODEL_PATH = r\"{model_path}\"")
        print(f"  或设置环境变量:")
        print(f"  set EMBEDDING_MODEL_PATH={model_path}")


if __name__ == "__main__":
    main()
