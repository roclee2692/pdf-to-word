# 平台支持说明

## 当前状态（v1.0.8）

| 平台 | 核心转换 CLI | GUI | 视觉校验 (LibreOffice) | 说明 |
| --- | --- | --- | --- | --- |
| **macOS** | ✅ 完整验证 | ✅ `./start.sh` | ✅ 已验证 | 主开发 / 验收环境 |
| **Linux** | ✅ 应可用 | ✅ PySide6 + `start.sh` | ✅ 需装 LibreOffice | 路径自动探测；未做完整 CI |
| **Windows** | ✅ 应可用 | ✅ `start.bat` + PySide6 | ✅ 需装 LibreOffice | 新增启动脚本；未做完整 UI 回归 |

核心转换链路（pdfplumber / python-docx / Pillow）是**跨平台 Python**，不依赖 macOS。  
GUI 使用 **PySide6**（跨平台）。  
差异主要在：**LibreOffice 安装路径**、**venv 路径**（Unix `.venv/bin` vs Windows `.venv\Scripts`）、**双击启动体验**。

## 各平台快速开始

### macOS（已充分验证）

```bash
./scripts/setup.sh
./start.sh
```

### Linux

```bash
sudo apt install libreoffice   # 或发行版等价包
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-gui.txt
.venv/bin/pip install -e .
export PDF2WORD_SOFFICE=$(command -v soffice || command -v libreoffice)
./start.sh
# 或
PYTHONPATH=src .venv/bin/python -m pdf2word convert sample.pdf --out out.docx
```

### Windows

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-gui.txt
.venv\Scripts\pip install -e .
start.bat
```

或 PowerShell：

```powershell
$env:PYTHONPATH="src"
.venv\Scripts\python -m pdf2word convert sample.pdf --out out.docx
```

## 评测仓库建议

上传前不要包含：

- `_recycle_bin/`
- `.venv/`
- `workspace/jobs/`
- `third_party/{docling,MinerU,PaddleOCR}/`（可选引擎克隆，体积 ~1GB+）
- `logs/`、`dist/`、本地 `.env`

保留：

- `src/` `tests/` `docs/` `scripts/`
- `requirements*.txt` `pyproject.toml` `README.md`
- `workspace/archive/v1.0.8-page-numbers/`（可选：最新验收产物）
- 样本 `NIPS-2017-attention-is-all-you-need-Paper.pdf`
