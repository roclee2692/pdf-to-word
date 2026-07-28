# PDF-to-Word 下一班交接报告

## 1. 核心目标

在 macOS 本地优先完成 PDF -> 可编辑 Word 的稳定主链路：预检 -> 路由 -> Canonical IR -> DOCX 渲染 -> 结构/文本/视觉验证。输出必须诚实区分“可编辑”和“视觉保真”，不宣称所有复杂 PDF 可 100% 还原。

## 2. 当前状态

- 项目：`/Users/raelon/Documents/Projects/PDF-to-Word`
- 分支：`main`；当前 HEAD：`32e4bdd`
- 工作区：交接前为 clean；最近稳定标签：`v1.0.8-page-numbers`
- 已完成：Native pdfplumber 解析、IR 1.5、四种渲染模式、验证引擎、LibreOffice 视觉闭环、PySide6 GUI、跨平台启动脚本、Attention 论文回归链路。
- 外部仓库：Docling、MinerU、PaddleOCR 已克隆到 `third_party/`；模型/运行时依赖不完整，默认能力探测失败时降级到 native，不可假报成功。
- macOS CLI/GUI/LibreOffice 已验证；Linux/Windows 已提供启动脚本，但没有完整 CI 和真实 Office/WPS 交叉验收。
- 旧基准（v1.0.4）为 47 tests OK、Attention 全 11 页：editable CER 0.0022、mean MAD 0.0737；positioned mean MAD 0.0194；hybrid 0.0203；fidelity 0.0197。`v1.0.5` 至 `v1.0.8` 有后续改动，必须在当前 HEAD 重新跑，不得直接沿用旧指标。

## 3. 四种模式契约

| 模式 | 产品定位 | 验收重点 |
|---|---|---|
| `positioned` | 固定版视觉交付；整页源图可选中、移动 | 不空白、不模糊、页面位置和公式/表格视觉接近 PDF；不承诺逐字编辑 |
| `editable` | 原生段落、Run、Word 表格，便于复制修改 | 文本完整、字体槽/粗斜体/上下标尽量保留、表格可编辑且有完整网格 |
| `hybrid` | 可见页面快照 + 隐藏搜索层 | 视觉优先，同时保留可搜索文字；不是主要编辑模式 |
| `fidelity` | 纯页面快照归档 | 视觉证明和页面完整性；不承诺正文语义编辑 |

GUI 当前是“左 PDF / 右 DOCX 渲染图”的对比预览，不是内嵌 Word/KMOffice 编辑器。可打开生成的 DOCX 到系统默认编辑器；`positioned` 的整页图片应可选中和移动。

## 4. 必须执行的验收门禁

1. Attention 论文全 11 页，四种模式均能生成并打开，输出页数等于源页数。
2. 不允许空白页、重复叠印、页面裁切、页眉页脚/页码丢失。
3. GUI 预览源图和输出图使用高分辨率资源，不能用低 DPI 缩略图冒充验收证据。
4. `positioned` 基准 mean MAD <= 0.055；当前基线约 0.0194，但必须重新测量。
5. `editable` 文本 CER <= 0.005，数字/引用不应丢失；复杂公式至少可读，不得重叠、乱码或截断。
6. Table 2、Table 3 必须可读：列不串位、单元格可换行、横竖边框完整；固定版视觉不得因额外网格产生重影。
7. 字体需分别处理 `ascii/hAnsi/eastAsia`，检查标题、粗体、斜体、上下标和参考文献。
8. 每次改动必须有命令、产物路径、页数、CER/MAD、检查页号和已知缺陷记录；“XML 存在”不等于“视觉通过”。

## 5. 当前未闭环风险

- 复杂/嵌套/多行公式的可编辑 OMML 仍不等价于 PDF；可采用公式图片或文本 fallback，但必须标注能力边界。
- 扫描件没有文本层时，若 OCR 运行时/模型不可用，只能可靠保留页面图，不能承诺单元格级可编辑恢复。
- 跨页表、嵌套表、复杂合并单元格仍需专项测试。
- 字体替换、Word/WPS/KMOffice 的 DrawingML 兼容性仍需真实目标软件验收。
- 最新 `workspace/archive/v1.0.8-page-numbers/` 目前主要归档 DOCX；较完整的 validation/IR/preflight 证据在 `workspace/archive/v1.0.4-paper-90/`。文档中的版本和指标存在需统一之处。

## 6. 复测命令

```bash
cd /Users/raelon/Documents/Projects/PDF-to-Word
./scripts/cli.sh convert NIPS-2017-attention-is-all-you-need-Paper.pdf --mode editable --out workspace/jobs/current/editable.docx --dump-ir
./scripts/cli.sh convert NIPS-2017-attention-is-all-you-need-Paper.pdf --mode positioned --out workspace/jobs/current/positioned.docx
./scripts/cli.sh convert NIPS-2017-attention-is-all-you-need-Paper.pdf --mode hybrid --out workspace/jobs/current/hybrid.docx
./scripts/cli.sh convert NIPS-2017-attention-is-all-you-need-Paper.pdf --mode fidelity --out workspace/jobs/current/fidelity.docx
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
./start.sh
```

GUI 验收顺序：拖入 PDF -> 预检 -> 选择四种模式逐一转换 -> 查看页数/CER/MAD -> 检查左右预览 -> 打开 DOCX -> 在目标编辑器验证文本、图片选中移动和表格可读性。

## 7. 下一班模型可直接使用的提示词

```text
你接手的是 /Users/raelon/Documents/Projects/PDF-to-Word。目标是把 Attention Is All You Need 全 11 页做成可交付的 PDF->DOCX 工具：positioned 负责视觉保真，editable 负责文本/表格编辑，hybrid/fidelity 负责视觉证明。先读取 README、docs/QUALITY_REPORT.md、docs/PLATFORM.md、git status/log 和当前代码，保留用户已有修改；不要凭旧报告宣布完成。

硬性约束：
1. 每轮先提出一个可验证假设，只改最小范围；先 focused test，再 full unittest，再跑 Attention 四模式端到端。
2. 用 LibreOffice 将 DOCX 渲染为 PDF/PNG，至少检查第 1、7、8、9 页原图与结果图；必须记录页数、CER、数字错误、mean/max MAD 和产物绝对路径。
3. 任何空白页、模糊预览、公式重叠/缺失、Table 2/3 列错位、竖线缺失、文本截断、页码丢失都算失败；不能用“DOCX XML 有内容”替代视觉检查。
4. 保持模式契约：不要为了 editable 去破坏 positioned；不要为 fidelity/hybrid 叠加会产生重影的表格网格；扫描件无 OCR 能力时必须明确降级。
5. 先解决当前 HEAD 的可复现基线和文档指标不一致，再优化公式、字体、表格和目标编辑器兼容性；不要先做 Agent 或大规模重构。
6. 每轮结束更新质量报告，写明通过项、失败项、证据命令和下一假设；只有验收门禁全部通过才可标记完成。

首轮任务：重新跑当前 HEAD 的完整 E2E 和 GUI smoke，核对四个 DOCX 是否都非空且可打开，重新生成 validation_report/PNG 证据，并把结果写回归档；如失败，先定位失败模式和最小修复点。
``` 

## 8. 交接结论

项目已经超过“纯文本落 Word”的 MVP：固定版视觉链路和 GUI 可用性已有可验证基础；但还不是复杂学术 PDF 的行业极限，也不能声称所有公式、扫描件和跨页表都能完美编辑。下一班的第一目标是用当前 HEAD 重建可信证据，再以“每轮可测量、可回归、可回滚”的方式把 Attention 论文稳定推进到 90% 视觉还原和可接受的 editable 质量。
