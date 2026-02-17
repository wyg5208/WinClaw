"""文本分块策略 - 支持多种分块方式。

提供：
- 固定大小分块（带重叠）
- 段落分块
- 递归分块（保持语义完整）
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 100


@dataclass
class TextChunk:
    """文本块。"""
    text: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: Optional[dict] = None


class TextSplitter:
    """文本分块器。"""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        keep_separator: bool = True,
    ):
        """初始化分块器。

        Args:
            chunk_size: 每个块的最大字符数
            chunk_overlap: 相邻块之间的重叠字符数
            keep_separator: 是否保留分隔符
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.keep_separator = keep_separator

    def split(self, text: str, metadata: Optional[dict] = None) -> list[TextChunk]:
        """分割文本为块。

        使用递归分块策略，优先按段落分割，保持语义完整。

        Args:
            text: 输入文本
            metadata: 附加元数据

        Returns:
            文本块列表
        """
        if not text or not text.strip():
            return []

        chunks = []
        metadata = metadata or {}

        # 先尝试按段落分割
        paragraphs = self._split_by_paragraphs(text)

        current_chunk = ""
        chunk_index = 0
        start_char = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果单个段落超长，再按句子分割
            if len(para) > self.chunk_size:
                # 先保存当前累积的内容
                if current_chunk:
                    chunks.append(TextChunk(
                        text=current_chunk.strip(),
                        chunk_index=chunk_index,
                        start_char=start_char,
                        end_char=start_char + len(current_chunk),
                        metadata=metadata.copy(),
                    ))
                    chunk_index += 1
                    start_char += len(current_chunk) - self.chunk_overlap
                    current_chunk = ""

                # 对超长段落进行递归分割
                sub_chunks = self._split_long_text(para, start_char, chunk_index, metadata)
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
                start_char = chunks[-1].end_char if chunks else start_char
                continue

            # 检查添加当前段落是否会超出大小限制
            if len(current_chunk) + len(para) + 1 > self.chunk_size and current_chunk:
                # 保存当前块
                chunks.append(TextChunk(
                    text=current_chunk.strip(),
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=start_char + len(current_chunk),
                    metadata=metadata.copy(),
                ))

                # 保持重叠
                overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else current_chunk
                start_char = start_char + len(current_chunk) - len(overlap_text)
                current_chunk = overlap_text + "\n" + para
                chunk_index += 1
            else:
                # 添加到当前块
                if current_chunk:
                    current_chunk += "\n" + para
                else:
                    current_chunk = para

        # 保存最后一个块
        if current_chunk.strip():
            chunks.append(TextChunk(
                text=current_chunk.strip(),
                chunk_index=chunk_index,
                start_char=start_char,
                end_char=start_char + len(current_chunk),
                metadata=metadata.copy(),
            ))

        logger.debug(f"分块完成: 原始长度 {len(text)} → {len(chunks)} 个块")
        return chunks

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """按段落分割文本。"""
        # 多种换行符统一处理
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        
        # 按空行分割
        paragraphs = re.split(r'\n\s*\n', text)
        
        return [p.replace("\n", " ") for p in paragraphs if p.strip()]

    def _split_long_text(
        self,
        text: str,
        start_offset: int,
        start_index: int,
        metadata: dict,
    ) -> list[TextChunk]:
        """对超长文本进行递归分块。"""
        chunks = []

        # 按句子分割
        sentences = self._split_by_sentences(text)

        current_chunk = ""
        chunk_index = start_index

        for sent in sentences:
            if len(current_chunk) + len(sent) + 1 > self.chunk_size and current_chunk:
                chunks.append(TextChunk(
                    text=current_chunk.strip(),
                    chunk_index=chunk_index,
                    start_char=start_offset,
                    end_char=start_offset + len(current_chunk),
                    metadata=metadata.copy(),
                ))
                start_offset += len(current_chunk) - self.chunk_overlap
                current_chunk = current_chunk[-self.chunk_overlap:] + sent
                chunk_index += 1
            else:
                if current_chunk:
                    current_chunk += " " + sent
                else:
                    current_chunk = sent

        if current_chunk.strip():
            chunks.append(TextChunk(
                text=current_chunk.strip(),
                chunk_index=chunk_index,
                start_char=start_offset,
                end_char=start_offset + len(current_chunk),
                metadata=metadata.copy(),
            ))

        return chunks

    def _split_by_sentences(self, text: str) -> list[str]:
        """按句子分割文本。"""
        # 常见句子结束符
        sentence_end = r'[.!?。！？]+'
        
        # 按句子分割，保留分隔符
        sentences = re.split(f'({sentence_end})', text)
        
        # 重新组合句子和结束符
        result = []
        for i in range(0, len(sentences) - 1, 2):
            sent = sentences[i]
            if i + 1 < len(sentences):
                sent += sentences[i + 1]
            if sent.strip():
                result.append(sent.strip())
        
        # 处理最后一个没有结束符的句子
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            result.append(sentences[-1].strip())
        
        return result

    def split_simple(self, text: str, metadata: Optional[dict] = None) -> list[str]:
        """简单分块（仅按固定大小，不考虑语义）。

        Args:
            text: 输入文本
            metadata: 元数据

        Returns:
            文本块列表（仅文本）
        """
        chunks = self.split(text, metadata)
        return [chunk.text for chunk in chunks]


class MarkdownSplitter(TextSplitter):
    """Markdown 专用分块器，保留标题上下文。"""

    def split(self, text: str, metadata: Optional[dict] = None) -> list[TextChunk]:
        """分割 Markdown，保留标题作为上下文。"""
        if not text:
            return []

        chunks = []
        metadata = metadata or {}

        # 提取标题
        headings = self._extract_headings(text)
        current_heading = ""

        # 按段落分割
        paragraphs = self._split_by_paragraphs(text)

        current_chunk = ""
        chunk_index = 0
        start_char = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 检查是否是标题行
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', para)
            if heading_match:
                current_heading = heading_match.group(2)
                continue

            # 添加标题上下文
            chunk_text = para
            if current_heading:
                chunk_text = f"[{current_heading}]\n{para}"

            # 检查块大小
            if len(current_chunk) + len(chunk_text) + 1 > self.chunk_size and current_chunk:
                chunks.append(TextChunk(
                    text=current_chunk.strip(),
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=start_char + len(current_chunk),
                    metadata={**metadata, "heading": current_heading},
                ))
                start_char += len(current_chunk) - self.chunk_overlap
                current_chunk = chunk_text
                chunk_index += 1
            else:
                if current_chunk:
                    current_chunk += "\n" + chunk_text
                else:
                    current_chunk = chunk_text

        if current_chunk.strip():
            chunks.append(TextChunk(
                text=current_chunk.strip(),
                chunk_index=chunk_index,
                start_char=start_char,
                end_char=start_char + len(current_chunk),
                metadata={**metadata, "heading": current_heading},
            ))

        return chunks

    def _extract_headings(self, text: str) -> dict[int, str]:
        """提取所有标题。"""
        headings = {}
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE):
            level = len(match.group(1))
            headings[match.start()] = (level, match.group(2))
        return headings
