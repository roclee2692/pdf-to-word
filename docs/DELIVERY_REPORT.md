# PDF-to-Word 项目交付报告

| 字段 | 内容 |
| --- | --- |
| 产品名 | PDF-to-Word（包名 `pdf2word-agent`） |
| 版本 | **v1.0.0-mvp-final** |
| 交付日期 | 2026-07-20 |
| Git 标签 | `v1.0.0-mvp-final`（本次修复完成后新增最终提交） |
| 基线样本 | `NIPS-2017-attention-is-all-you-need-Paper.pdf`（11 页） |
| 许可 | Apache-2.0 |

本文合并 [MVP.md](MVP.md) 的范围说明与 [QUALITY_REPORT.md](QUALITY_REPORT.md) 的验收证据，作为对外/对内复用的完整交付说明。

---

## 1. 交付目标与原则

**目标：** 本地优先的 PDF → 可编辑 Word（`.docx`），并带工业级质量门禁。

**主链路：**

```text
预检 (Preflight) → 路由 (Router) → Canonical IR → 渲染 (DOCX) → 验证 (Validation)
```

**原则：**

1. **确定性程序**做主链路（解析、排版、写 DOCX）。  
2. **专用模型**仅做可选识别（Docling / MinerU / PaddleOCR，默认关闭）。  
3. **验证器**决定是否合格（结构 / 文本 CER / 表 / 图 / 视觉 MAD + 页数）。  
4. **Agent 修复环**刻意推迟到 IR / 渲染 / 验证稳定之后。

---

## 2. 核心能力

### 2.1 四种渲染模式（双方案）

| 方案 | 模式 | 含义 | 基线 mean MAD | 页数 | 推荐场景 |
| --- | --- | --- | ---: | ---: | --- |
| **可编辑** | `editable` | 流式段落、真表格、软分页 | **0.0734** | 11→11 | 复制改写、长文重排 |
| **可编辑 + 定位** | `positioned` | DrawingML 文本框 / 浮动表 / 锚定图 | **0.0492** | 11→11 | 原生对象 + 像素门禁 ≤0.055 |
| **高保真** | `hybrid` | 页图 behindDoc + 可编辑层（vanish） | **0.0200** | 11→11 | 像素优先，包内仍有对象 |
| **像素证明** | `fidelity` | 页图快照为主 | **0.0194** | 11→11 | 外观证明 / 归档观感 |

关键实现决策：

- LibreOffice 下使用 **DrawingML**（`wp:anchor` + `wps:txbx`），**不用** `w:framePr`（会导致页数崩溃）。  
- `editable` 采用 **连续 section + 软分页**；历史「每页硬分节」曾把 11 页撑到 21 页。  
- `positioned` 按源行拆框，IR `line_bboxes`（schema 1.5）逐行锚定；公式保留源坐标裁剪图和隐藏 fallback。

### 2.2 验证与门禁

| 门禁 | v1.0.0-mvp 结果 |
| --- | --- |
| 页数 ≈ 源页 | **11 → 11**（四模式） |
| 文本 CER（`editable`） | **0.0002**（数字错误率 0.0） |
| `positioned` mean MAD ≤ 0.055 | **0.0492** 达标 |
| `hybrid` / `fidelity` 像素 | **0.0200** / **0.0194** |
| 结构 / 表 / 图（`editable`） | pass |
| 单元 + 集成测试 | **44 OK**（1 skipped） |
| GUI 烟测（macOS Cocoa） | 预检 + 四模式 + Open output，无闪退 |

每份产物默认写入：

- `validation/validation_report.json` + `.md`  
- `validation/preflight.json`  
- 可选视觉：`validation/visual/`（需 LibreOffice）

### 2.3 已实现工程范围（摘要）

- `PdfPlumberBackend`：文本层、图片流、线/框、表几何  
- Canonical IR schema **1.5**（含 `line_bboxes`、字体槽、表合并占位、源词间距标记等）
- 原生解析 + 能力感知路由；外置引擎不可用则降级 native  
- `EditableDocxRenderer`：连续流打包、多栏折叠、图嵌入、STEM 表压缩  
- `FidelityDocxRenderer`：`positioned` / `hybrid` / `fidelity`  
- CLI：`pdf2word convert`；GUI：`pdf2word gui`（PySide6）  
- 本地 job workspace；发布证据 `workspace/archive/v1.0.0-mvp-final/`

更细的工程清单见 [MVP.md](MVP.md)；历史 MAD 迭代见 [QUALITY_REPORT.md](QUALITY_REPORT.md)。

---

## 3. 验收亮点（可对外展示）

基线论文全 11 页，LibreOffice 视觉闭环：

| Mode | Pages | mean MAD | Overall |
| --- | ---: | ---: | --- |
| **editable** | 11 → 11 | **0.0734** | PASS（CER 0.0002；visual warn） |
| **positioned** | 11 → 11 | **0.0492** | PASS（≤0.055） |
| **hybrid** | 11 → 11 | **0.0200** | PASS |
| **fidelity** | 11 → 11 | **0.0194** | PASS |

**一句话：** 语义编辑与像素证明两条产品线均已用同一套验证器证明可用。

发布归档内容：

```text
workspace/archive/v1.0.0-mvp-final/
  docx/{editable,positioned,hybrid,fidelity}.docx
  validation/*.validation_report.{json,md}
  validation/preflight.json
  logs/*.cli.log
  RELEASE_METRICS.json
  README.md
```

---

## 4. 复现与交付包

### 4.1 环境一键复现

```bash
cd PDF-to-Word
./scripts/setup.sh       # venv + 锁定依赖 + GUI
cp .env.example .env     # 配置 LibreOffice 路径
./start.sh               # 桌面 GUI 演示
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

锁定依赖见根目录 `requirements.txt`、`requirements-gui.txt`、`pyproject.toml`（版本 **1.0.0**）。

### 4.2 常用命令

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"  # 或写入 .env

./scripts/cli.sh convert sample.pdf --pages 1-3 --mode editable --out out.docx
./scripts/cli.sh convert sample.pdf --pages 1-11 --mode hybrid --out out.docx --dump-ir
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

### 4.3 备份位置（本机打包）

| 产物 | 路径 |
| --- | --- |
| 验收归档 tar | `dist/releases/pdf2word-v1.0.0-mvp-archive.tar.gz` |
| 交付包 tar | `dist/releases/pdf2word-v1.0.0-mvp-package.tar.gz` |
| Git 离线 bundle | `dist/releases/pdf2word-v1.0.0-mvp.gitbundle` |
| Documents 备份 | `~/Documents/backups/PDF-to-Word/` |
| Desktop 备份 | `~/Desktop/PDF-to-Word-v1.0.0-mvp-backup/` |

从 bundle 恢复：

```bash
git clone pdf2word-v1.0.0-mvp.gitbundle PDF-to-Word
cd PDF-to-Word && git checkout v1.0.0-mvp
```

### 4.4 推送到远程（需自行配置 URL）

当前仓库可能尚无 `origin`。有 GitHub/GitLab 地址后：

```bash
git remote add origin <YOUR_REPO_URL>
git push -u origin main
git push origin v1.0.0-mvp
```

---

## 5. 明确未交付 / 半交付

| 项 | 状态 |
| --- | --- |
| Agent 修复环、IR patch 存储 | 未做 |
| Docling 模型缓存 / MinerU·PaddleOCR 可执行运行时 | 克隆可探测，运行时依赖/模型未齐 |
| 扫描件 OCR、跨页表真实拆分 | 未做 |
| 复杂嵌套公式全量 OMML | 简单结构化 + 文本/OMML fallback |
| pure positioned 单页残差（如第 2 页 ~0.064） | 均值已达标，单页可继续压 |
| hybrid 可见文字 + 快照级 MAD | 需额外分层策略 |
| 跨平台桌面打包 | 仅 macOS Cocoa 烟测 |

---

## 6. 建议的后续优先级

1. **远程备份：** 建 Git 远程并 `push` 标签 `v1.0.0-mvp`；网盘再存一份 `dist/releases/*`。  
2. **positioned 余量：** 第 2 页字距/字模，进一步压 MAD。  
3. **外置解析：** Docling 模型 → MinerU / PaddleOCR（paddlex 等）。  
4. **公式与扫描件：** OMML 边角、OCR 兜底。  
5. **跨页表：** 重复表头 + 真实拆分。  
6. **Agent：** 先 IR patch/revision，再 repair loop。

---

## 7. 交接一句话

主链路已从「文本落 Word」做到 **可验证的工业门禁**（页数、CER、MAD）：`editable` 管语义，`positioned` 管纯原生对象像素（≈0.049），`hybrid`/`fidelity` 管像素证明（≈0.02）。外置 OCR/解析与 Agent 尚未闭环；环境依赖 LibreOffice + `PDF2WORD_SOFFICE`（可用 `.env` / `./start.sh`）；回归样本为 Attention 11 页论文；版本以 Git 标签 **`v1.0.0-mvp`** 冻结。
