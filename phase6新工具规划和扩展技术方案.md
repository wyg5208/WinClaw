# Phase 6 新工具规划与扩展技术方案

> 本文档规划 WinClaw Phase 6 阶段的新工具开发，聚焦用户常用的生活和工作场景。
> ✅ 修正了多媒体捕获工具的Action列表（移除远期功能"capture_region"）
> ✅ OCR增强工具已标记为远期规划（enabled=false）

---

## 一、工具全景总览

| 类别 | 工具名称 | 优先级 | 预估工时 | 依赖技术 |
|------|----------|--------|----------|----------|
| **文档转换** | 格式转换器 (docx/pdf/json/csv/md/html) | 高 | 3天 | python-docx, reportlab, pandoc |
| **PDF处理** | PDF 工具 (合并/拆分/加密) | 高 | 2天 | PyPDF2, reportlab |
| **证件照** | 证件照制作工具 | 高 | 2天 | rembg, Pillow, opencv |
| **演示文稿** | PPT 生成器 | 高 | 3天 | python-pptx |
| **AI 写作** | 论文/文章/小说撰写 | 中 | 4天 | 大语言模型 + 文档工具 |
| **多媒体捕获** | 拍照/录音/录像工具 | 中 | 3天 | opencv, sounddevice, ffmpeg |
| **GIF制作** | GIF 制作工具 | 中 | 1天 | moviepy, Pillow |
| **语音转文字** | 语音识别工具 | 中 | 2天 | Whisper (已有) |
| **多语言翻译** | 翻译工具 | 中 | 2天 | deep_translator |
| **思维导图** | 思维导图生成 | 低 | 2天 | graphviz, markdown |
| **简历制作** | 简历生成器 | 低 | 2天 | python-docx, AI 辅助 |
| **合同模板** | 合同生成器 | 中 | 2天 | python-docx, AI 辅助 |
| **财务报告** | 财务报表生成 | 中 | 3天 | python-docx, openpyxl, AI 辅助 |
| **数据处理** | Excel 数据处理 | 中 | 3天 | pandas, openpyxl |
| **数据可视化** | 数据可视化分析 | 中 | 3天 | matplotlib, plotly, seaborn |
| **教育学习** | 学习工具集 | 高 | 8天 | 大语言模型, 语音合成 |
| **编程辅助** | 编程助手 | 高 | 5天 | 大语言模型, 代码分析 |
| **文献检索** | 学术文献检索 (OpenAlex) | 中 | 3天 | requests, openalex-api |
| **远期规划** | 屏幕录制/视频剪辑/OCR增强 | 低 | 待定 | 待技术评估 |
| **远期规划** | 屏幕录制/视频剪辑/OCR增强 | 低 | 待定 | 待技术评估 |

---

## 二、详细工具规划

### 2.1 文档格式转换工具 (FormatConverter)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/format_converter.py` |
| 类名 | `FormatConverterTool` |
| 动作数 | 30+ 个 |
| 优先级 | 高 |
| 预估工时 | 3 天 |

#### 功能清单

**Pandoc 核心转换（系统已安装）**

| 动作 | 说明 | 输入格式 | 输出格式 |
|------|------|----------|----------|
| `convert_markdown_to_docx` | Markdown 转 Word | .md | .docx |
| `convert_markdown_to_html` | Markdown 转 HTML | .md | .html |
| `convert_markdown_to_pdf` | Markdown 转 PDF | .md | .pdf |
| `convert_markdown_to_latex` | Markdown 转 LaTeX | .md | .tex |
| `convert_markdown_to_rtf` | Markdown 转 RTF | .md | .rtf |
| `convert_markdown_to_epub` | Markdown 转 EPUB | .md | .epub |
| `convert_docx_to_markdown` | Word 转 Markdown | .docx | .md |
| `convert_docx_to_html` | Word 转 HTML | .docx | .html |
| `convert_docx_to_latex` | Word 转 LaTeX | .docx | .tex |
| `convert_html_to_markdown` | HTML 转 Markdown | .html | .md |
| `convert_html_to_docx` | HTML 转 Word | .html | .docx |
| `convert_latex_to_markdown` | LaTeX 转 Markdown | .tex | .md |
| `convert_docbook_to_markdown` | DocBook 转 Markdown | .xml | .md |
| `convert_mediawiki_to_markdown` | MediaWiki 转 Markdown | .wiki | .md |

**Office 格式转换**

| 动作 | 说明 | 输入格式 | 输出格式 |
|------|------|----------|----------|
| `convert_docx_to_pdf` | Word 转 PDF | .docx | .pdf |
| `convert_pdf_to_docx` | PDF 转 Word | .pdf | .docx |
| `convert_odt_to_docx` | OpenDocument 转 Word | .odt | .docx |
| `convert_docx_to_odt` | Word 转 OpenDocument | .docx | .odt |

**数据格式转换**

| 动作 | 说明 | 输入格式 | 输出格式 |
|------|------|----------|----------|
| `convert_csv_to_json` | CSV 转 JSON | .csv | .json |
| `convert_json_to_csv` | JSON 转 CSV | .json | .csv |
| `convert_json_to_xml` | JSON 转 XML | .json | .xml |
| `convert_xml_to_json` | XML 转 JSON | .xml | .json |

**图片/音频/视频格式转换**

| 动作 | 说明 | 输入格式 | 输出格式 |
|------|------|----------|----------|
| `convert_image_format` | 图片格式转换 | png/jpg/webp/gif/bmp/tiff | png/jpg/webp |
| `convert_audio_format` | 音频格式转换 | mp3/wav/flac/aac/ogg/m4a | mp3/wav |
| `convert_video_format` | 视频格式转换 | mp4/avi/mkv/mov/wmv/flv | mp4 |

**电子书格式转换**

| 动作 | 说明 | 输入格式 | 输出格式 |
|------|------|----------|----------|
| `convert_epub_to_pdf` | EPUB 转 PDF | .epub | .pdf |
| `convert_epub_to_mobi` | EPUB 转 MOBI | .epub | .mobi |
| `convert_pdf_to_epub` | PDF 转 EPUB | .pdf | .epub |

#### Pandoc 高级特性

```bash
# Pandoc 支持的格式（部分）
# 输入: markdown, markdown_github, markdown_phpextra, markdown_strict,
#       markdown_mmd, commonmark, docbook, haddock, html, latex,
#       odt, opendocument, org, rtf, textile, native, json, yaml
#
# 输出: markdown, markdown_github, markdown_strict, commonmark,
#       docbook, docx, epub, fb2, html, html5, latex, beamer,
#       man, mediawiki, muski, odt, opendocument, org, pdf,
#       pptx, rtf, texinfo, textile, slidy, s5, dzslides, revealjs
```

#### 技术方案

```python
# 核心依赖
- pandoc: 系统已安装，强大的文档格式转换
- python-docx: Word 文档操作（Pandoc 后备）
- Pillow: 图片格式转换
- ffmpeg-python: 音视频转换
- PyPDF2: PDF 操作
- ebooklib: 电子书格式转换

# Pandoc 封装示例
def convert_with_pandoc(input_file: str, output_file: str,
                       from_format: str = None, to_format: str = None,
                       extra_args: list = None):
    """Pandoc 封装函数"""
    cmd = ['pandoc', input_file, '-o', output_file]
    if from_format:
        cmd.insert(1, f'-f{from_format}')
    if to_format:
        cmd.insert(1, f'-t{to_format}')
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(cmd, check=True)

# 常用转换示例
# Markdown → Word (带目录)
convert_with_pandoc('input.md', 'output.docx',
                   extra_args=['--toc', '--toc-depth=3'])

# Markdown → HTML (支持数学公式)
convert_with_pandoc('input.md', 'output.html',
                   extra_args=['--mathjax'])

# Word → Markdown (保留格式)
convert_with_pandoc('input.docx', 'output.md',
                   extra_args=['--wrap=preserve'])

# HTML → Word (带样式)
convert_with_pandoc('input.html', 'output.docx',
                   extra_args=['--reference-doc=template.docx'])
```

#### 数据流

```
用户请求 → 识别文件类型 → 选择转换引擎 → 执行转换 → 保存到生成空间 → 返回文件路径
```

#### 特殊处理

| 场景 | 解决方案 |
|------|----------|
| 中文乱码 | 使用 UTF-8 编码，--from=markdown+raw_tex |
| 数学公式 | --mathjax 或 --katex 参数 |
| 目录生成 | --toc --toc-depth=N 参数 |
| 样式模板 | --reference-doc=template.docx |
| PDF 中文 | 使用 XeLaTeX 引擎 + ctex 宏包 |

---

### 2.2 证件照制作工具 (IDPhoto)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/id_photo.py` |
| 类名 | `IDPhotoTool` |
| 动作数 | 5 个 |
| 优先级 | 高 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 |
|------|------|
| `make_id_photo` | 制作证件照（人像分割 + 背景替换 + 尺寸调整） |
| `change_background` | 更换背景色（蓝/白/红/渐变） |
| `resize_photo` | 调整尺寸（一寸/二寸/签证/驾照等） |
| `compress_photo` | 压缩照片（控制文件大小） |
| `add_watermark` | 添加水印（文字/图片） |

#### 常用证件照尺寸

| 类型 | 尺寸 (像素) | 用途 |
|------|-------------|------|
| 一寸 | 295×413 | 驾照、简历 |
| 二寸 | 413×579 | 签证、护照 |
| 小一寸 | 260×378 | 身份证 |
| 大一寸 | 390×567 | 护照 |

#### 技术方案

```python
# 核心依赖
- rembg: 人像分割（U2Net）
- Pillow: 图像处理
- opencv: 图像运算

# 实现流程
1. 读取输入图片
2. rembg 进行人像分割，获取 mask
3. 根据目标背景色填充背景
4. 调整到目标尺寸
5. 保存到生成空间

# 注意事项
- 分割模型首次使用需要下载（~100MB）
- 支持批量处理
```

---

### 2.3 PPT 生成工具 (PPTGEN)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/ppt_generator.py` |
| 类名 | `PPTTool` |
| 动作数 | 3 个 |
| 优先级 | 高 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `generate_ppt` | AI 生成 PPT | topic, outline, style, slide_count |
| `add_slide` | 添加幻灯片 | ppt_path, title, content, layout |
| `export_pdf` | 导出 PDF | ppt_path, output_path |

#### PPT 模板风格

| 风格 | 适用场景 |
|------|----------|
| business | 商务汇报 |
| academic | 学术报告 |
| creative | 创意展示 |
| minimal | 简洁风格 |

#### 技术方案

```python
# 核心依赖
- python-pptx: PPT 生成和编辑

# 实现流程
1. 用户提供主题/大纲
2. 调用大语言模型生成详细内容
3. python-pptx 创建 PPT
4. 填充标题、内容、图片
5. 保存到生成空间

# AI 生成提示词示例
"""
请为以下主题生成 PPT 大纲：
主题：{topic}
风格：{style}
页数：{slide_count}

请返回 JSON 格式的大纲，每页包含：
- title: 标题
- content: 要点列表
- layout: 布局类型（title/content/image）
"""
```

---

### 2.4 AI 写作工具 (AIWriter)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/ai_writer.py` |
| 类名 | `AIWriterTool` |
| 动作数 | 4 个 |
| 优先级 | 中 |
| 预估工时 | 4 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `write_paper` | 论文撰写 | topic, subject, length, requirements |
| `write_article` | 文章撰写 | topic, style, length, keywords |
| `write_novel` | 小说创作 | genre, plot, characters, chapters |
| `continue_writing` | 续写内容 | text, length, style |

#### 论文结构模板

```
1. 摘要
2. 引言/研究背景
3. 相关工作
4. 方法/实验设计
5. 结果与分析
6. 讨论
7. 结论
8. 参考文献
```

#### 技术方案

```python
# 实现流程
1. 用户提供主题/要求
2. 调用大语言模型生成内容
3. 配合 doc_generator 输出为 Word/PDF
4. 保存到生成空间

# 写作风格
- 学术论文：正式、严谨、引用规范
- 文章：流畅、可读性强
- 小说：情节丰富、人物立体
```

---

### 2.5 多媒体捕获工具 (MediaCapture)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/media_capture.py` |
| 类名 | `MediaCaptureTool` |
| 动作数 | 6 个 |
| 优先级 | 中 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `take_photo` | 拍照 | device_index, save_path |
| `record_video` | 录像 | duration, save_path, device_index |
| `record_audio` | 录音 | duration, save_path, device_index |
| `list_devices` | 列出可用的摄像头/麦克风 | - |
| `preview_camera` | 摄像头预览 | device_index |
| `capture_region` | 区域截图（带摄像头） | x, y, width, height |

#### 技术方案

```python
# 核心依赖
- opencv-python (cv2): 摄像头拍照/录像
- sounddevice: 音频录制
- ffmpeg: 音视频处理

# Windows 平台
- 摄像头: 使用 DirectShow 或 MSMF
- 麦克风: 使用 WASAPI

# 实现流程
拍照:
1. 打开摄像头
2. 读取帧
3. 保存为图片
4. 关闭摄像头

录像:
1. 打开摄像头
2. 创建 VideoWriter
3. 循环录制帧
4. 停止并保存

录音:
1. 打开麦克风
2. 录制音频数据
3. 保存为 wav/mp3
```

---

### 2.6 OCR 增强工具 (OCRPlus)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/ocr_plus.py` |
| 类名 | `OCRPlusTool` |
| 动作数 | 4 个 |
| 优先级 | 低 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 |
|------|------|
| `recognize_table` | 表格识别（输出 Excel） |
| `recognize_handwriting` | 手写文字识别 |
| `recognize_id_card` | 身份证识别（提取字段） |
| `recognize_receipt` | 发票/收据识别（提取金额、日期） |

#### 技术方案

```python
# 核心依赖
- rapidocr_onnx: 已有，通用 OCR
- paddleocr: 表格识别（需要安装）
- 中国身份证识别: baidu-aip 或自建模板

# 表格识别流程
1. OCR 识别全文
2. 表格检测（EdgeFormer）
3. 表格结构识别
4. 输出为 Excel
```

---

### 2.7 PDF 处理工具 (PDFTool)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/pdf_tool.py` |
| 类名 | `PDFTool` |
| 动作数 | 6 个 |
| 优先级 | 高 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 |
|------|------|
| `merge_pdfs` | 合并多个 PDF 为一个 |
| `split_pdf` | 拆分 PDF（按页/按范围） |
| `extract_pages` | 提取指定页 |
| `compress_pdf` | 压缩 PDF |
| `add_password` | 添加密码保护 |
| `remove_password` | 移除密码保护 |

#### 技术方案

```python
# 核心依赖
- PyPDF2: PDF 读取、合并、拆分
- reportlab: PDF 生成
- pypdfcrypt: PDF 加密解密
```

---

### 2.8 屏幕录制工具 (ScreenRecorder)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/screen_recorder.py` |
| 类名 | `ScreenRecorderTool` |
| 动作数 | 4 个 |
| 优先级 | 中 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `start_recording` | 开始录制屏幕 | output_path, fps, quality |
| `stop_recording` | 停止录制 | - |
| `record_region` | 录制指定区域 | x, y, width, height |
| `record_window` | 录制指定窗口 | window_title |

#### 技术方案

```python
# 核心依赖
- mss: 屏幕截图
- ffmpeg-python: 视频编码
- pillow: 图像处理

# Windows 平台
- 使用 MSS 截取屏幕
- 使用 ffmpeg 编码为视频
- 支持全屏/区域/窗口录制
```

---

### 2.9 视频剪辑工具 (VideoEditor)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/video_editor.py` |
| 类名 | `VideoEditorTool` |
| 动作数 | 6 个 |
| 优先级 | 中 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 |
|------|------|
| `trim_video` | 裁剪视频（指定起止时间） |
| `merge_videos` | 合并多个视频 |
| `add_subtitle` | 添加字幕文件 |
| `extract_audio` | 提取音频 |
| `add_watermark` | 添加水印 |
| `change_speed` | 调整播放速度 |

#### 技术方案

```python
# 核心依赖
- moviepy: 视频剪辑
- ffmpeg-python: 底层视频处理

# 实现流程
1. 裁剪: 指定 start_time, end_time
2. 合并: 多个视频按顺序拼接
3. 字幕: 加载 SRT/VTT 字幕文件
4. 水印: 添加文字或图片水印
```

---

### 2.10 GIF 制作工具 (GifMaker)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/gif_maker.py` |
| 类名 | `GifMakerTool` |
| 动作数 | 3 个 |
| 优先级 | 中 |
| 预估工时 | 1 天 |

#### 功能清单

| 动作 | 说明 |
|------|------|
| `video_to_gif` | 视频转 GIF |
| `images_to_gif` | 图片序列转 GIF |
| `capture_region_to_gif` | 屏幕区域录制为 GIF |

#### 技术方案

```python
# 核心依赖
- moviepy: 视频转 GIF
- Pillow: 图片序列处理

# 参数
- fps: 帧率（默认 10）
- width: 输出宽度（自动等比缩放）
- duration: 时长限制
```

---

### 2.11 语音转文字工具 (SpeechToText)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/speech_to_text.py` |
| 类名 | `SpeechToTextTool` |
| 动作数 | 3 个 |
| 优先级 | 中 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `transcribe_audio` | 音频转文字 | audio_path, language |
| `transcribe_realtime` | 实时语音识别 | duration, language |
| `transcribe_with_timestamps` | 带时间戳转写 | audio_path |

#### 技术方案

```python
# 核心依赖
- whisper (已有): 离线语音识别
- faster-whisper: 高性能版本（可选）

# 支持语言
- 自动检测语言
- 支持中文、英文、日文等

# 会议场景
- 识别说话人（需要 pyannote.audio）
- 生成会议纪要（调用 LLM）
```

---

### 2.12 翻译工具 (Translator)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/translator.py` |
| 类名 | `TranslatorTool` |
| 动作数 | 4 个 |
| 优先级 | 中 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `translate_text` | 文本翻译 | text, source_lang, target_lang |
| `translate_file` | 文件翻译 | file_path, source_lang, target_lang |
| `batch_translate` | 批量翻译 | texts, source_lang, target_lang |
| `detect_language` | 语言检测 | text |

#### 支持语言

```
中文、英文、日文、韩文、法文、德文、西班牙文、俄文、阿拉伯文等 100+ 语言
```

#### 技术方案

```python
# 核心依赖
- deep_translator: 多翻译引擎聚合
- googletrans (备选): Google 翻译

# 翻译引擎
- Google Translate（默认）
- DeepL（可选）
- 百度翻译（可选）

# 实现流程
1. 检测源语言（可选）
2. 调用翻译 API
3. 返回翻译结果
```

---

### 2.13 思维导图工具 (MindMap)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/mind_map.py` |
| 类名 | `MindMapTool` |
| 动作数 | 3 个 |
| 优先级 | 低 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `generate_mindmap` | AI 生成思维导图 | topic, depth, branches |
| `export_image` | 导出为图片 | mindmap_data, format |
| `export_markdown` | 导出为 Markdown | mindmap_data |

#### 技术方案

```python
# 核心依赖
- graphviz: 图形渲染
- markdown: Markdown 导出

# AI 生成流程
1. 用户提供主题
2. 调用 LLM 生成导图结构（JSON）
3. 转换为 graphviz 语法
4. 渲染为 PNG/SVG

# 导图结构示例
{
  "root": "主题",
  "branches": [
    {"label": "分支1", "children": [...]},
    {"label": "分支2", "children": [...]}
  ]
}
```

---

### 2.14 简历制作工具 (ResumeBuilder)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/resume_builder.py` |
| 类名 | `ResumeBuilderTool` |
| 动作数 | 3 个 |
| 优先级 | 低 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `generate_resume` | AI 生成简历 | personal_info, job_target, experience |
| `optimize_resume` | AI 优化简历 | resume_text, job_description |
| `export_pdf` | 导出 PDF | resume_data, template |

#### 简历模板

| 模板 | 适用场景 |
|------|----------|
| modern | 现代简约 |
| professional | 商务专业 |
| creative | 创意设计 |
| academic | 学术简历 |

#### 技术方案

```python
# 核心依赖
- python-docx: Word 简历生成
- reportlab: PDF 导出

# AI 优化
1. 分析岗位描述
2. 提取关键词
3. 优化简历内容
4. 给出建议
```

---

### 2.15 文献检索工具 (LiteratureSearch)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/literature_search.py` |
| 类名 | `LiteratureSearchTool` |
| 动作数 | 4 个 |
| 优先级 | 中 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `search_papers` | 搜索学术论文 | query, max_results, year_from |
| `get_paper_details` | 获取论文详情 | paper_id |
| `download_pdf` | 下载论文 PDF | paper_id, save_path |
| `get_citations` | 获取引用关系 | paper_id |

#### OpenAlex API

```python
# API 文档: https://api.openalex.org/
# 基础 URL: https://api.openalex.org/works

# 搜索论文
GET https://api.openalex.org/works?search={query}&per_page={max_results}

# 获取论文详情
GET https://api.openalex.org/works/{paper_id}

# 响应字段
- id: 论文 ID
- title: 标题
- authors: 作者列表
- abstract: 摘要
- publication_year: 发表年份
- cited_by_count: 引用数
- open_access_pdf: PDF 链接
- doi: DOI
```

#### 技术方案

```python
# 核心依赖
- requests: HTTP 请求

# 实现流程
1. 构建 OpenAlex API 请求
2. 解析响应数据
3. 格式化显示结果
4. 支持下载 PDF（通过 DOI 或 open_access 链接）

# 特色功能
- 按引用数排序
- 按年份筛选
- 全文搜索
- AI 摘要生成（调用 LLM）
```

---

### 2.16 合同模板工具 (ContractGenerator)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/contract_generator.py` |
| 类名 | `ContractGeneratorTool` |
| 动作数 | 4 个 |
| 优先级 | 中 |
| 预估工时 | 2 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `generate_contract` | AI 生成合同 | contract_type, parties, terms |
| `preview_contract` | 预览合同内容 | contract_data |
| `export_docx` | 导出 Word | contract_data |
| `export_pdf` | 导出 PDF | contract_data |

#### 合同类型模板

| 类型 | 适用场景 |
|------|----------|
| 劳动合同 | 雇佣关系 |
| 房屋租赁合同 | 租房 |
| 买卖合同 | 商品交易 |
| 服务合同 | 提供服务 |
| 合作协议 | 商业合作 |
| 保密协议 | 商业机密 |

#### 技术方案

```python
# 核心依赖
- python-docx: Word 合同生成
- reportlab: PDF 导出

# AI 生成流程
1. 用户提供合同类型和关键信息
2. 调用 LLM 生成合同内容
3. 填充到合同模板
4. 用户预览后可编辑
5. 导出 Word/PDF

# 合同要素
- 甲方/乙方信息
- 合同金额
- 履行期限
- 违约条款
- 争议解决
```

---

### 2.17 财务报告工具 (FinancialReport)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/financial_report.py` |
| 类名 | `FinancialReportTool` |
| 动作数 | 5 个 |
| 优先级 | 中 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `generate_report` | AI 生成财务报告 | report_type, data_source |
| `generate_balance_sheet` | 生成资产负债表 | account_data |
| `generate_income_statement` | 生成利润表 | revenue_expense_data |
| `generate_cash_flow` | 生成现金流量表 | cash_data |
| `export_excel` | 导出 Excel | report_data |

#### 报告类型

| 类型 | 说明 |
|------|------|
| 月度报表 | 月度收支汇总 |
| 季度报表 | 季度财务分析 |
| 年度报表 | 年度财务报告 |
| 专项报告 | 特定项目分析 |

#### 技术方案

```python
# 核心依赖
- pandas: 数据处理
- openpyxl: Excel 操作
- python-docx: Word 报告生成
- matplotlib: 图表生成

# 实现流程
1. 读取记账数据（从 finance 工具获取）
2. 生成各类财务报表
3. 调用 LLM 生成分析文字
4. 整合为完整报告
5. 导出 Excel/Word/PDF

# AI 分析
- 收入成本分析
- 利润趋势分析
- 现金流分析
- 同比环比分析
```

---

### 2.18 数据处理工具 (DataProcessor)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/data_processor.py` |
| 类名 | `DataProcessorTool` |
| 动作数 | 8 个 |
| 优先级 | 中 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `read_excel` | 读取 Excel | file_path, sheet_name |
| `filter_data` | 数据筛选 | data, conditions |
| `sort_data` | 数据排序 | data, column, order |
| `aggregate_data` | 数据聚合 | data, group_by, agg_func |
| `merge_data` | 数据合并 | data1, data2, how |
| `pivot_table` | 透视表 | data, index, columns, values |
| `clean_data` | 数据清洗 | data, operations |
| `export_data` | 导出数据 | data, format |

#### 支持格式

```
Excel (.xlsx, .xls), CSV, JSON, HTML
```

#### 技术方案

```python
# 核心依赖
- pandas: 数据处理
- openpyxl: Excel 读写

# 数据清洗操作
- 去除重复行
- 填充缺失值
- 数据类型转换
- 异常值处理
- 字符串清洗

# 聚合函数
- sum, mean, count, min, max
- 自定义函数
```

---

### 2.19 数据可视化工具 (DataVisualization)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/data_visualization.py` |
| 类名 | `DataVisualizationTool` |
| 动作数 | 6 个 |
| 优先级 | 中 |
| 预估工时 | 3 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `plot_bar` | 柱状图 | data, x, y, title |
| `plot_line` | 折线图 | data, x, y, title |
| `plot_pie` | 饼图 | data, values, labels |
| `plot_scatter` | 散点图 | data, x, y, title |
| `plot_heatmap` | 热力图 | data, title |
| `generate_dashboard` | AI 生成仪表盘 | data, analysis_type |

#### 图表类型

| 图表 | 适用场景 |
|------|----------|
| 柱状图 | 分类对比 |
| 折线图 | 趋势变化 |
| 饼图 | 占比分析 |
| 散点图 | 相关性分析 |
| 热力图 | 密度/相关性 |
| 箱线图 | 分布分析 |

#### 技术方案

```python
# 核心依赖
- matplotlib: 基础图表
- plotly: 交互式图表
- seaborn: 统计图表

# AI 分析流程
1. 分析数据结构
2. 选择合适的图表类型
3. 自动设置颜色、标签
4. 生成分析建议

# 输出格式
- PNG: 静态图片
- HTML: 交互式网页

---

### 2.20 教育学习工具集 (EducationTool)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/education_tool.py` |
| 类名 | `EducationTool` |
| 动作数 | 12 个 |
| 优先级 | 高 |
| 预估工时 | 8 天 |

#### 功能清单

| 动作 | 说明 |
|------|------|
| `english_dialogue` | 英语场景对话练习 |
| `answer_question` | 拍题解答（拍照识别题目并解答） |
| `wrong_questions` | 错题本管理 |
| `add_wrong_question` | 添加错题 |
| `query_wrong_questions` | 查询错题 |
| `practice_wrong_questions` | 错题复习 |
| `word_learning` | 英语单词学习 |
| `quiz_words` | 单词测验 |
| `history_knowledge` | 历史知识问答 |
| `generate_quiz` | 生成练习题 |
| `explain_concept` | 概念讲解 |
| `learning_progress` | 学习进度统计 |

#### 英语场景对话

```python
# 场景类型
- 日常对话 (shopping, restaurant, travel, etc.)
- 商务英语 (meeting, presentation, negotiation)
- 面试英语 (job interview)
- 学术英语 (presentation, discussion)

# 功能
- AI 扮演对话角色
- 实时语音对话
- 语法纠正
- 表达建议
- 场景评分
```

#### 拍题解答

```python
# 实现流程
1. 用户拍照上传题目
2. OCR 识别题目内容
3. 调用 LLM 解答
4. 返回详细解题步骤
5. 相似题目推荐

# 支持题型
- 数学计算/证明
- 物理/化学
- 英语语法
- 语文阅读
```

#### 错题本

```python
# 数据结构
- 题目内容
- 正确答案
- 解题步骤
- 知识点标签
- 错误原因
- 添加日期
- 掌握程度

# 学习模式
- 间隔重复复习
- 按知识点复习
- 错题重做
- 错题统计
```

#### 英语单词学习

```python
# 功能
- 单词卡片
- 每日背单词
- 记忆曲线复习
- 单词测验
- 发音练习

# 数据来源
- 常用词汇书 (CET-4, CET-6, TOEFL, IELTS)
- 用户自定义词库
- 阅读中积累
```

#### 历史知识

```python
# 知识领域
- 中国历史
- 世界历史
- 历史人物
- 历史事件
- 历史年表

# 功能
- 知识问答
- 时间线梳理
- 历史事件讲解
- 历史人物介绍
```

#### 技术方案

```python
# 核心依赖
- 大语言模型: 问答和讲解
- Whisper: 语音识别（英语对话）
- pyttsx3: 语音合成（发音练习）
- sqlite3: 错题本存储
- rapidocr: 题目识别

# 数据存储
- SQLite: 错题本、单词本
- 生成空间: 学习资料
```

---

### 2.21 编程辅助工具 (CodeAssistant)

#### 概述

| 属性 | 值 |
|------|-----|
| 文件 | `src/tools/code_assistant.py` |
| 类名 | `CodeAssistantTool` |
| 动作数 | 10 个 |
| 优先级 | 高 |
| 预估工时 | 5 天 |

#### 功能清单

| 动作 | 说明 | 参数 |
|------|------|------|
| `explain_code` | 代码解释 | code, language |
| `write_code` | 代码编写 | description, language, requirements |
| `debug_code` | 代码调试 | code, error_message |
| `refactor_code` | 代码重构 | code, target_style |
| `write_tests` | 编写测试 | code, test_framework |
| `generate_docs` | 生成文档 | code, format |
| `review_code` | 代码审查 | code, language |
| `explain_error` | 错误解释 | error_message, language |
| `convert_code` | 代码转换 | code, from_lang, to_lang |
| `optimize_code` | 代码优化 | code, language |

#### 编程语言支持

| 语言 | 支持 |
|------|------|
| Python | ✅ 完整支持 |
| JavaScript/TypeScript | ✅ 完整支持 |
| Java | ✅ 基础支持 |
| C/C++ | ✅ 基础支持 |
| Go | ✅ 基础支持 |
| Rust | ✅ 基础支持 |
| 其他 | 调用 LLM |

#### 功能示例

```python
# 代码解释
用户: "解释这段 Python 代码"
AI: 逐行解释代码功能和逻辑

# 代码编写
用户: "写一个快速排序算法"
AI: 生成完整的 Python 实现

# 代码调试
用户: "这段代码报错了"
AI: 分析错误原因并提供修复方案

# 代码重构
用户: "把这段命令式代码改成函数式"
AI: 提供重构后的代码

# 代码审查
用户: "审查这段代码"
AI: 指出潜在问题和优化建议
```

#### 技术方案

```python
# 核心依赖
- 大语言模型: 代码理解和生成
- pygments: 代码高亮
- ast: Python 代码分析
- eslint-analyzer: JS 代码分析（可选）

# 实现流程
1. 用户输入代码或描述
2. 预处理代码（格式化、高亮）
3. 调用 LLM 处理
4. 返回结果（代码/解释/建议）

# 特色功能
- 代码高亮渲染
- 语法错误检测
- 性能建议
- 安全漏洞检测
```

---

## 三、工具配置更新

### 3.1 tools.json 新增配置

```json
"format_converter": {
  "enabled": true,
  "module": "src.tools.format_converter",
  "class": "FormatConverterTool",
  "display": {
    "name": "格式转换",
    "emoji": "🔄",
    "description": "文档、图片、音频、视频格式转换",
    "category": "utility"
  },
  "config": {},
  "security": {
    "risk_level": "low",
    "require_confirmation": false
  },
  "actions": ["convert_docx_to_pdf", "convert_pdf_to_docx", "convert_markdown_to_docx", "convert_markdown_to_html", "convert_csv_to_json", "convert_json_to_csv", "convert_image_format", "convert_audio_format", "convert_video_format"]
},
"id_photo": {
  "enabled": true,
  "module": "src.tools.id_photo",
  "class": "IDPhotoTool",
  "display": {
    "name": "证件照",
    "emoji": "📷",
    "description": "制作证件照、更换背景、调整尺寸",
    "category": "visual"
  },
  "config": {},
  "security": {
    "risk_level": "low",
    "require_confirmation": false
  },
  "actions": ["make_id_photo", "change_background", "resize_photo", "compress_photo", "add_watermark"]
},
"ppt_generator": {
  "enabled": true,
  "module": "src.tools.ppt_generator",
  "class": "PPTTool",
  "display": {
    "name": "PPT生成",
    "emoji": "📊",
    "description": "AI 生成演示文稿 PPT",
    "category": "generation"
  },
  "config": {},
  "security": {
    "risk_level": "low",
    "require_confirmation": false
  },
  "actions": ["generate_ppt", "add_slide", "export_pdf"]
},
"ai_writer": {
  "enabled": true,
  "module": "src.tools.ai_writer",
  "class": "AIWriterTool",
  "display": {
    "name": "AI写作",
    "emoji": "✍️",
    "description": "论文、文章、小说等 AI 写作辅助",
    "category": "generation"
  },
  "config": {},
  "security": {
    "risk_level": "low",
    "require_confirmation": false
  },
  "actions": ["write_paper", "write_article", "write_novel", "continue_writing"]
},
"media_capture": {
  "enabled": true,
  "module": "src.tools.media_capture",
  "class": "MediaCaptureTool",
  "display": {
    "name": "多媒体捕获",
    "emoji": "🎬",
    "description": "拍照、录像、录音",
    "category": "multimedia"
  },
  "config": {},
  "security": {
    "risk_level": "low",
    "require_confirmation": false
  },
  "actions": ["take_photo", "record_video", "record_audio", "list_devices", "preview_camera"]
},
"ocr_plus": {
  "enabled": false,
  "module": "src.tools.ocr_plus",
  "class": "OCRPlusTool",
  "display": {
    "name": "OCR增强",
    "emoji": "🔍",
    "description": "表格识别、手写识别、证件识别（远期规划）",
    "category": "multimedia"
  },
  "config": {},
  "security": {
    "risk_level": "low",
    "require_confirmation": false
  },
  "actions": ["recognize_table", "recognize_handwriting", "recognize_id_card", "recognize_receipt"]
}
```

### 3.2 新增依赖

| 依赖 | 用途 | 阶段 |
|------|------|------|
| `python-pptx` | PPT 生成 | 必须 |
| `rembg` | 人像分割 | 必须 |
| `opencv-python` | 摄像头拍照/录像 | 必须 |
| `sounddevice` | 录音 | 必须 |
| `ffmpeg-python` | 音视频转换 | 必须 |
| `moviepy` | GIF制作 | 必须 |
| `comtypes` | Word 转 PDF | Windows |
| `deep-translator` | 多语言翻译 | 必须 |
| `graphviz` | 思维导图渲染 | 必须 |
| `PyPDF2` | PDF 处理 | 必须 |
| `requests` | HTTP 请求（文献检索） | 必须 |
| `pandas` | 数据处理 | 必须 |
| `openpyxl` | Excel 操作 | 必须 |
| `matplotlib` | 图表生成 | 必须 |
| `plotly` | 交互式图表 | 必须 |
| `seaborn` | 统计图表 | 可选 |
| `pygments` | 代码高亮 | 必须 |
| `mss` | 屏幕录制 | **远期规划** |
| `paddleocr` | OCR增强 | **远期规划** |

---

## 四、实施计划

### 批次划分（不含远期规划）

| 批次 | 工具 | 预估工时 | 优先级 |
|------|------|----------|--------|
| Phase 6-A | 格式转换器 + PDF 工具 | 5 天 | 高 |
| Phase 6-B | 证件照制作 | 2 天 | 高 |
| Phase 6-C | PPT 生成器 | 3 天 | 高 |
| Phase 6-D | AI 写作 + 简历制作 | 6 天 | 中 |
| Phase 6-E | 多媒体捕获 | 3 天 | 中 |
| Phase 6-F | GIF 制作 | 1 天 | 中 |
| Phase 6-G | 语音转文字 + 翻译 | 4 天 | 中 |
| Phase 6-H | 思维导图 | 2 天 | 低 |
| Phase 6-I | 文献检索 (OpenAlex) | 3 天 | 中 |
| Phase 6-J | 合同模板 | 2 天 | 中 |
| Phase 6-K | 财务报告 | 3 天 | 中 |
| Phase 6-L | 数据处理 + 数据可视化 | 6 天 | 中 |
| Phase 6-M | 教育学习工具集 | 8 天 | 高 |
| Phase 6-N | 编程辅助工具 | 5 天 | 高 |

**总计**：约 54 天（比原方案减少10天）

### 远期规划工具（待技术评估）

| 工具 | 预估工时 | 技术难点 | 暂缓原因 |
|------|----------|----------|----------|
| 屏幕录制 | 2-3 天 | Windows API 调用复杂，跨平台兼容性差 | 技术门槛高，优先级低 |
| 视频剪辑 | 3-4 天 | 依赖 ffmpeg 安装，跨平台问题 | 依赖复杂，可替代方案多 |
| OCR 增强 | 2-3 天 | paddleocr 安装困难，模型体积大 | 现有 rapidocr 已满足基础需求 |

---

## 五、功能需求清单

以下功能需求已完成规划：

- [x] 格式转换（30+种，基于pandoc）
- [x] PDF 处理（合并/拆分/加密）
- [x] 证件照制作（人像分割+背景替换）
- [x] PPT 生成（AI生成演示文稿）
- [x] AI 写作（论文/文章/小说）
- [x] 多媒体捕获（拍照/录像/录音）
- [x] GIF 制作
- [x] 语音转文字（会议录音转文字）
- [x] 多语言翻译（100+语言）
- [x] 思维导图生成
- [x] 简历制作
- [x] 文献检索（基于OpenAlex）
- [x] 合同模板
- [x] 财务报告
- [x] 数据探索和处理（Excel）
- [x] 数据可视化分析
- [x] 英语场景对话练习
- [x] 拍题解答
- [x] 错题本
- [x] 英语单词学习
- [x] 历史知识问答
- [x] 编程辅助（代码解释/编写/调试/优化）

### 远期规划（暂不纳入当前开发议程）

- [ ] 屏幕录制（技术复杂度高，跨平台兼容问题）
- [ ] 视频剪辑（依赖ffmpeg，安装复杂）
- [ ] OCR增强（paddleocr安装门槛高）

### 待补充需求

- [ ] 其他需求...

---

> 本文档将根据用户反馈持续更新完善。
