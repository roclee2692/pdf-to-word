# PDF-to-Word

**一句话：** 本地 PDF 转可编辑 Word（`.docx`），支持 **4 种模式**，兼顾**可编辑性**与**高保真**像素还原。

版本：`v1.0.0-mvp` · Python ≥ 3.11 · 许可 Apache-2.0

---

## 快速开始

### 1. 安装依赖

```bash
cd PDF-to-Word
./scripts/setup.sh
# 等价：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-gui.txt && .venv/bin/pip install -e .
```

视觉校验（页数 / MAD）需要 LibreOffice：

```bash
brew install --cask libreoffice
# 默认路径（已写入 start.sh）：
# /Applications/LibreOffice.app/Contents/MacOS/soffice
```

### 2. 一键启动 GUI

```bash
./start.sh
```

或在 Finder 中双击 `start.sh`（首次若被拦截：右键 → 打开）。

界面：拖入 PDF → 选模式 → Preflight / Convert → Open output。

### 3. CLI 示例

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
PYTHONPATH=src .venv/bin/python -m pdf2word convert \
  "NIPS-2017-attention-is-all-you-need-Paper.pdf" \
  --pages 1-11 \
  --mode positioned \
  --out workspace/jobs/demo/result.docx \
  --dump-ir
```

也可用：`./scripts/cli.sh convert input.pdf --pages 1-3 --mode editable --out out.docx`

| 常用参数 | 说明 |
| --- | --- |
| `--mode` | `editable` / `positioned` / `hybrid` / `fidelity` |
| `--pages` | 页码，如 `1` 或 `1-11` 或 `1,3-5` |
| `--dump-ir` | 导出中间 IR JSON |
| `--no-validate` | 跳过校验 |
| `--no-visual-diff` | 不做 LibreOffice 视觉对比 |

### 4. 跑测试

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
# 期望：38 OK（1 skipped）
```

---

## 核心模式说明

| 模式 | 区别 | 适用场景 |
| --- | --- | --- |
| **`editable`** | 流式段落、真 Word 表格，可正常改字重排 | 复制编辑、长文修改 |
| **`positioned`** | DrawingML 文本框 / 浮动表 / 锚定图，按 PDF 坐标放 | 既要可编辑对象，又要版式接近原稿 |
| **`hybrid`** | 页图垫底 + 包内可编辑层（文字默认 vanish） | 像素优先，仍保留对象 |
| **`fidelity`** | 以页图快照为主 | 外观证明 / 高保真对照 |

- **可编辑方案：** `editable`、`positioned`  
- **高保真方案：** `hybrid`、`fidelity`  

---

## 验收亮点（Attention 论文 · 全 11 页）

样本：`NIPS-2017-attention-is-all-you-need-Paper.pdf`  
证据目录：`workspace/archive/v1.0.0-mvp/`

| 指标 | 结果 |
| --- | --- |
| 页数 | **11 → 11**（四种模式） |
| 文本 CER（`editable`） | **0.0** |
| `positioned` mean MAD | **≈ 0.049**（门禁 ≤ 0.055；发布跑 0.0492 / GUI 烟测 0.0493） |
| `hybrid` / `fidelity` mean MAD | **0.0198 / 0.0194** |
| `editable` mean MAD | **≈ 0.072**（语义流式，允许视觉 warn） |
| 单测 | **38 OK**（1 skipped） |

---

## 已知限制

当前 MVP **尚未**覆盖（避免预期不符）：

- 复杂嵌套公式的完整 OMML 还原（现为简单结构化 + 文本 fallback）  
- 跨页表格的真实拆分与连续表头重建  
- 扫描件 / 低质量 PDF 的 OCR 主路径（PaddleOCR 等运行时未齐）  
- Agent 自动修复环  
- pure `positioned` 个别页残差仍可继续压（如第 2 页）  

原生文本层 PDF 为主路径；外置解析默认关闭（`PDF2WORD_ENABLE_EXTERNAL_PARSERS=1` 才尝试）。

---

## 项目结构（简）

```text
src/pdf2word/     # 主程序
tests/            # 单测 / 集成测
docs/             # 内部施工日志与质量报告（见下）
start.sh          # 一键 GUI
scripts/setup.sh  # 环境安装
workspace/archive/v1.0.0-mvp/   # MVP 最终产物（docx + 校验 + 日志）
```

## 内部文档（施工日志，保留复盘用）

| 文件 | 内容 |
| --- | --- |
| [docs/MVP.md](docs/MVP.md) | 已实现范围 / 下一步 |
| [docs/QUALITY_REPORT.md](docs/QUALITY_REPORT.md) | MAD、页数迭代证据 |
| [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md) | 完整交付说明 |
| [docs/SETUP_LIBREOFFICE.md](docs/SETUP_LIBREOFFICE.md) | LibreOffice 安装 |

---

## 备份与版本

- Git 标签：`v1.0.0-mvp`  
- 本地验收包：`workspace/archive/v1.0.0-mvp/`  
- 压缩备份（与代码仓库分开保存）：`pdf2word-v1.0.0-mvp-archive.zip`  

```bash
# 推远程（配置 origin 后）
git push -u origin main
git push origin v1.0.0-mvp
```
