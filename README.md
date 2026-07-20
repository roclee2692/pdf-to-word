# PDF-to-Word

**一句话：** 本地 PDF 转可编辑 Word（`.docx`），支持 **4 种模式**，兼顾**可编辑性**与**像素级校对**。

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
# 默认路径（已写入 start.sh / .env.example）：
# PDF2WORD_SOFFICE=/Applications/LibreOffice.app/Contents/MacOS/soffice
cp -n .env.example .env   # 可按需修改
```

### 2. 一键启动 GUI

```bash
./start.sh
```

或在 Finder 中双击 `start.sh`（首次若被拦截：右键 → 打开）。  
若启动失败：查看 `logs/start.log`（双击时错误也会写在这里，macOS 会弹窗提示）。

界面：拖入 PDF → 选模式 → Preflight / Convert → Open output。  
**默认模式：`positioned`（可编辑交付）。**

### 3. CLI 示例

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"

# 默认：全部页 + positioned
./scripts/cli.sh convert "NIPS-2017-attention-is-all-you-need-Paper.pdf" \
  --out workspace/jobs/demo/result.docx --dump-ir

# 指定页 / 模式 / 严格视觉门禁
./scripts/cli.sh convert input.pdf --pages 1-11 --mode editable \
  --strict-visual --out out.docx

# 批量目录
./scripts/cli.sh batch ./input_pdfs/ --out ./output_docs/ --mode positioned
```

| 常用参数 | 说明 |
| --- | --- |
| `--mode` | `positioned`（默认）/ `editable` / `hybrid` / `fidelity` |
| `--pages` | 可选；如 `1`、`1-11`、`1,3-5`；**省略 = 全文** |
| `--strict-visual` | 更严：DrawingML 文本非空检查 + 视觉 warn 视为失败 |
| `--dump-ir` | 导出中间 IR JSON |
| `--no-validate` | 跳过校验 |
| `--no-visual-diff` | 不做 LibreOffice 视觉对比 |

### 4. 跑测试

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
# Expected: Ran 44 tests ... OK (skipped=1)
```

---

## 核心模式说明（请先读）

| 模式 | 类型 | 区别 | 适用场景 |
| --- | --- | --- | --- |
| **`positioned`** | **可编辑交付（默认）** | DrawingML 文本框 / 浮动表 / 锚定图 | 原生对象 + 版式接近原稿 |
| **`editable`** | **可编辑交付** | 流式段落、真 Word 表格 | 复制改写、长文重排 |
| **`hybrid`** | **像素校对工具** | 页图垫底 + 可编辑层（vanish） | 像素优先对照，**不是**主交付 |
| **`fidelity`** | **像素证明工具** | 页图快照为主 | 外观证明，**不是**主交付 |

- **交付请用：** `positioned` 或 `editable`（原生 Word 对象）。  
- **`hybrid` / `fidelity`：** 仅作像素级证明 / 临时预览；含页图快照，**不符合「禁止图片占位」的终态编辑标准**。  
- **公式：** 简单结构化公式可写 OMML；**复杂公式会回退为可编辑文本**，不是完整原生公式对象。

---

## 验收亮点（Attention 论文 · 全 11 页）

样本：`NIPS-2017-attention-is-all-you-need-Paper.pdf`  
证据：`workspace/archive/v1.0.0-mvp-final/`

| 指标 | 结果 |
| --- | --- |
| 页数 | **11 → 11**（四种模式） |
| 文本 CER（`editable`） | **0.0002**（数字错误率 0.0） |
| `editable` mean MAD | **0.0734**（语义流模式，视觉警告不影响结构门禁） |
| `positioned` mean MAD | **0.0492**（≤ 0.055） |
| `hybrid` / `fidelity` mean MAD | **0.0200 / 0.0194**（像素工具） |
| 单测 | **44 OK**（1 skipped；GUI smoke 已通过） |

最终产物与逐模式报告归档于 `workspace/archive/v1.0.0-mvp-final/`：
`docx/`、`validation/`、`validation_report.json`、`preflight/`、`ir/`。

### GUI 操作

`./start.sh` 启动后，拖入 PDF，点击 **Preflight** 查看文档类型和降级提示，选择模式后点击 **Convert**。进度区会显示当前阶段和验证摘要（页数、MAD、CER）；完成后点击 **Open output** 直接打开 DOCX。默认使用 `positioned`。

模式选择建议：

- `positioned`：默认交付，原生 DrawingML 文本框、表格和图片对象，适合需要尽量保留版式且还要编辑的文档。
- `editable`：连续 Word 流和真表格，适合大段复制、改写和重新排版。
- `hybrid`：页图作为视觉底稿，同时保留隐藏的可编辑层，适合像素对照验收。
- `fidelity`：页图快照为主，适合归档和外观证明，不适合作为主要编辑版本。

公式说明：能稳定识别的简单公式会生成 OMML；复杂或 PDF 文本层损坏的展示公式会保留源坐标公式裁剪图，并写入隐藏文本 fallback，确保显示完整且可搜索，但暂不保证所有复杂公式都是原生可编辑 OMML。

---

## 扫描件 / 无文本层

- 预检会标记无文本层页面；外置 OCR（MinerU / PaddleOCR / Docling）不可用时 **不再崩溃**。  
- 会 **降级 native** 并打印 `WARNING`（质量有限）。  
- 需要 OCR 时：安装运行时后设 `PDF2WORD_ENABLE_EXTERNAL_PARSERS=1`。

---

## 已知限制

- 复杂嵌套公式 OMML 未全覆盖（简单 OMML + 文本 fallback）  
- 跨页表格真实拆分、嵌套表未闭环  
- 扫描件 OCR 运行时默认未齐（仅有安全降级，不是高质量识别）  
- 封面制表位引导线、Agent 修复环未做  
- `positioned` 个别页残差仍可继续压  

---

## 项目结构（简）

```text
src/pdf2word/     # 主程序
tests/
docs/             # 施工日志 / 质量报告
start.sh          # 一键 GUI（读 .env，写 logs/start.log）
scripts/setup.sh  # 环境安装
scripts/cli.sh    # CLI 包装
workspace/archive/v1.0.0-mvp-final/
```

| 文档 | 内容 |
| --- | --- |
| [docs/MVP.md](docs/MVP.md) | 已实现 / 下一步 |
| [docs/QUALITY_REPORT.md](docs/QUALITY_REPORT.md) | MAD 证据 |
| [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md) | 交付说明 |
| [docs/SETUP_LIBREOFFICE.md](docs/SETUP_LIBREOFFICE.md) | LibreOffice |
