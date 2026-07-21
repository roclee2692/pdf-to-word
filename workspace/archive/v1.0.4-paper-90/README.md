# PDF-to-Word

**一句话：** 本地 PDF 转可编辑 Word（`.docx`），支持 **4 种模式**，兼顾**可编辑性**与**像素级校对**。

版本：`v1.0.4-paper-90` · Python ≥ 3.11 · 许可 Apache-2.0

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

界面：拖入 PDF → 选模式 → Preflight / Convert → 查看验证摘要 → 左右对照预览 → Open output。
**默认模式：`positioned`（固定版高保真，可选择和移动整页图片）。**

转换完成后会自动打开对照窗口：左侧是源 PDF 页面，右侧是 LibreOffice 实际渲染的 DOCX 页面，可用页码切换逐页比对，并查看页数、MAD、CER、表格/公式/图片数量和当前模式的编辑性告警。点击“在默认 Word 应用中打开”后，可在 Word、WPS 或 LibreOffice 中实际修改 DOCX；Qt 预览窗口本身是验收预览，不是内嵌 Word 编辑器。

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
# Expected: Ran 47 tests ... OK (skipped=1)
```

---

## 核心模式说明（请先读）

| 模式 | 类型 | 区别 | 适用场景 |
| --- | --- | --- | --- |
| **`positioned`** | **固定版高保真（默认）** | 可移动的整页源图，避免 Office/WPS 空白兼容问题 | 论文逐页校对、公式和表格视觉还原 |
| **`editable`** | **编辑优先** | 连续流段落、真 Word 表格、公式文字 fallback | 复制、修改、重排长文 |
| **`hybrid`** | **折中验收** | PDF 快照垫底 + 隐藏可编辑层 | 关键公式/图片保真，同时保留对象 |
| **`fidelity`** | **保真优先** | PDF 快照 + 精确竖向表格分隔线 | 视觉归档和像素证明 |

- **需要继续编辑正文：** 用 `editable`。文本、字体槽、粗体/斜体、上下标和原生表格优先，复杂公式以可编辑文字 fallback 保留。
- **需要版面最接近 PDF：** 用 `positioned`。每页是可选中、可移动的 Word 图片，公式、字体、表格和图形按源页显示；正文不能逐字编辑。
- **需要交付前对照验收：** 用 `hybrid`。页面快照负责视觉，隐藏对象层负责可检索/可替换结构；表格网格保持可见。
- **需要外观证明或归档：** 用 `fidelity`。PDF 快照负责字体、图片、公式和颜色，只叠加精确竖线增强表格可读性，不承诺正文可编辑。

---

## 验收亮点（Attention 论文 · 全 11 页）

样本：`NIPS-2017-attention-is-all-you-need-Paper.pdf`  
证据：`workspace/archive/v1.0.4-paper-90/`

| 指标 | 结果 |
| --- | --- |
| 页数 | **11 → 11**（四种模式） |
| 文本 CER（`editable`） | **0.0022**（数字错误率 0.0；公式脚本符号仍按视觉上下标表达） |
| `editable` mean MAD | **0.0737**（语义流模式，视觉警告不影响结构门禁） |
| `positioned` mean MAD | **0.0194**（固定版页图；≤ 0.055） |
| `hybrid` / `fidelity` mean MAD | **0.0203 / 0.0197**（像素工具） |
| 单测 | **47 OK**（1 skipped；GUI smoke 已通过） |

最终产物与逐模式报告归档于 `workspace/archive/v1.0.4-paper-90/`：
`docx/`、`validation/`、`validation_report.json`、`preflight/`、`ir/`。

### GUI 操作

`./start.sh` 启动后，拖入 PDF，点击 **Preflight** 查看文档类型和降级提示，选择模式后点击 **Convert**。进度区会显示当前阶段和验证摘要（页数、MAD、CER）；完成后点击 **Open output** 直接打开 DOCX。默认使用 `positioned`。

模式选择建议：

- `positioned`：默认固定版交付，整页图片可选择和移动；视觉最接近源 PDF，但文字不可逐字编辑。
- `editable`：连续 Word 流和真表格；表格补全列分隔线，公式以可编辑 run/上下标或文字 fallback 表达。
- `hybrid`：页图作为视觉底稿，隐藏对象层提供可检索结构；表格边框仍可见。
- `fidelity`：页图快照为主，公式、字体、图片和颜色最稳定；表格仅补精确竖向分隔线，适合归档，不适合作为主要编辑版本。

公式说明：`positioned/hybrid/fidelity` 由源页图保证显示；`editable` 优先保留可编辑文字和上下标，简单结构仍可写入 OMML 并附隐藏文本 fallback。复杂嵌套公式尚未承诺完整原生 OMML。

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
workspace/archive/v1.0.4-paper-90/
```

| 文档 | 内容 |
| --- | --- |
| [docs/MVP.md](docs/MVP.md) | 已实现 / 下一步 |
| [docs/QUALITY_REPORT.md](docs/QUALITY_REPORT.md) | MAD 证据 |
| [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md) | 交付说明 |
| [docs/SETUP_LIBREOFFICE.md](docs/SETUP_LIBREOFFICE.md) | LibreOffice |
