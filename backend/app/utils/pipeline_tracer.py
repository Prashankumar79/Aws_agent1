"""
================================================================================
  backend/app/utils/pipeline_tracer.py  —  PIPELINE TRACING UTILITY
================================================================================

PURPOSE:
  Centralized logging utility for pipeline execution with structured logging,
  timing information, and context size tracking.

FEATURES:
  - Trace ID generation for each pipeline run
  - Structured logging with timestamps
  - Context size tracking (character counts, estimated tokens)
  - Performance metrics (start/end timestamps, duration)
  - Export trace logs to JSON for analysis

CONNECTIONS TO OTHER FILES:
  • All agent nodes → use this utility for consistent logging
  • jobs.py → can export trace logs for debugging
================================================================================
"""
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineTracer:
    """Centralized pipeline execution tracer with structured logging."""

    def __init__(self, job_id: str, log_dir: str = "./logs"):
        """
        Initialize tracer for a specific pipeline job.
        
        Args:
            job_id: Unique job identifier
            log_dir: Directory to save trace logs
        """
        self.job_id = job_id
        self.trace_id = str(uuid.uuid4())
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.trace_data = {
            "trace_id": self.trace_id,
            "job_id": job_id,
            "start_time": datetime.utcnow().isoformat(),
            "stages": [],
            "summary": {}
        }
        
        self.current_stage = None
        self.stage_start_time = None

    def start_stage(self, stage_name: str, input_data: Optional[Dict] = None):
        """
        Start tracking a new pipeline stage.
        
        Args:
            stage_name: Name of the pipeline stage
            input_data: Input data for this stage (for size tracking)
        """
        self.current_stage = stage_name
        self.stage_start_time = time.time()
        
        stage_data = {
            "stage": stage_name,
            "start_time": datetime.utcnow().isoformat(),
            "input_size": self._calculate_size(input_data) if input_data else 0,
            "input_keys": list(input_data.keys()) if input_data else []
        }
        
        logger.info(f"[TRACE:{self.trace_id}] STARTING STAGE: {stage_name} | input_size={stage_data['input_size']}")
        
    def end_stage(self, output_data: Optional[Dict] = None, error: Optional[str] = None):
        """
        End tracking the current pipeline stage.
        
        Args:
            output_data: Output data from this stage
            error: Error message if stage failed
        """
        if not self.current_stage or not self.stage_start_time:
            logger.warning(f"[TRACE:{self.trace_id}] end_stage called without start_stage")
            return
        
        duration = time.time() - self.stage_start_time
        stage_data = {
            "stage": self.current_stage,
            "end_time": datetime.utcnow().isoformat(),
            "duration_seconds": duration,
            "output_size": self._calculate_size(output_data) if output_data else 0,
            "output_keys": list(output_data.keys()) if output_data else [],
            "error": error,
            "success": error is None
        }
        
        self.trace_data["stages"].append(stage_data)
        
        status = "COMPLETED" if error is None else "FAILED"
        logger.info(f"[TRACE:{self.trace_id}] STAGE {status}: {self.current_stage} | duration={duration:.2f}s | output_size={stage_data['output_size']}")
        
        self.current_stage = None
        self.stage_start_time = None

    def log_compression(self, before_size: int, after_size: int, stage: str = "compression"):
        """
        Log compression metrics.
        
        Args:
            before_size: Size before compression
            after_size: Size after compression
            stage: Name of compression stage
        """
        ratio = before_size / after_size if after_size > 0 else 0
        reduction = (1 - after_size / before_size) * 100 if before_size > 0 else 0
        
        logger.info(f"[TRACE:{self.trace_id}] COMPRESSION {stage}: before={before_size}, after={after_size}, ratio={ratio:.2f}x, reduction={reduction:.1f}%")
        
        self.trace_data["summary"][f"{stage}_compression"] = {
            "before_size": before_size,
            "after_size": after_size,
            "ratio": ratio,
            "reduction_percent": reduction
        }

    def log_context_size(self, context_name: str, context_data: Dict):
        """
        Log context size metrics.
        
        Args:
            context_name: Name of the context (e.g., "fused_context", "master_context")
            context_data: Context data dictionary
        """
        size = self._calculate_size(context_data)
        estimated_tokens = size // 4  # Rough estimate: 1 token ≈ 4 characters
        
        logger.info(f"[TRACE:{self.trace_id}] CONTEXT {context_name}: size={size} chars, est_tokens={estimated_tokens}")
        
        self.trace_data["summary"][f"{context_name}_size"] = {
            "characters": size,
            "estimated_tokens": estimated_tokens
        }

    def finalize(self):
        """Finalize the trace and save to disk."""
        self.trace_data["end_time"] = datetime.utcnow().isoformat()
        
        # Calculate total duration
        total_duration = 0
        for stage in self.trace_data["stages"]:
            total_duration += stage.get("duration_seconds", 0)
        self.trace_data["summary"]["total_duration_seconds"] = total_duration
        
        # Calculate success rate
        successful_stages = sum(1 for s in self.trace_data["stages"] if s.get("success", False))
        total_stages = len(self.trace_data["stages"])
        self.trace_data["summary"]["success_rate"] = successful_stages / total_stages if total_stages > 0 else 0
        
        # Save to file
        trace_file = self.log_dir / f"trace_{self.job_id}_{self.trace_id}.json"
        with open(trace_file, 'w') as f:
            json.dump(self.trace_data, f, indent=2, default=str)
        
        logger.info(f"[TRACE:{self.trace_id}] Trace saved to: {trace_file}")
        logger.info(f"[TRACE:{self.trace_id}] SUMMARY: duration={total_duration:.2f}s, stages={total_stages}, success_rate={self.trace_data['summary']['success_rate']:.2%}")
        
        return trace_file

    def _calculate_size(self, data: Any) -> int:
        """Calculate size of data in characters."""
        if data is None:
            return 0
        return len(str(data))


# Global tracer instance (per job)
_tracers: Dict[str, PipelineTracer] = {}


def get_tracer(job_id: str, log_dir: str = "./logs") -> PipelineTracer:
    """Get or create a tracer for the given job_id."""
    if job_id not in _tracers:
        _tracers[job_id] = PipelineTracer(job_id, log_dir)
    return _tracers[job_id]


def finalize_tracer(job_id: str):
    """Finalize and save the tracer for the given job_id."""
    if job_id in _tracers:
        _tracers[job_id].finalize()
        del _tracers[job_id]
