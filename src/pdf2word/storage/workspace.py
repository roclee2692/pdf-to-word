from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class JobWorkspace:
    job_id: str
    root: Path
    input_dir: Path
    parser_outputs_dir: Path
    ir_dir: Path
    output_dir: Path
    validation_dir: Path
    traces_dir: Path


class WorkspaceStore:
    def __init__(self, root: str | Path = "workspace"):
        self.root = Path(root)

    def create_job(self) -> JobWorkspace:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        job_id = f"{timestamp}_{uuid4().hex[:8]}"
        job_root = self.root / "jobs" / job_id
        workspace = JobWorkspace(
            job_id=job_id,
            root=job_root,
            input_dir=job_root / "input",
            parser_outputs_dir=job_root / "parser_outputs",
            ir_dir=job_root / "ir",
            output_dir=job_root / "output",
            validation_dir=job_root / "validation",
            traces_dir=job_root / "traces",
        )
        for directory in (
            workspace.input_dir,
            workspace.parser_outputs_dir,
            workspace.ir_dir,
            workspace.output_dir,
            workspace.validation_dir,
            workspace.traces_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return workspace

