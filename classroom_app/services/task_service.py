from __future__ import annotations

from pathlib import Path

from classroom_app.core.errors import TaskExecutionError
from config import Config
from utils.database import Database


class TaskService:
    def __init__(self):
        self.db = Database()

    def create_task(self, task_id, task_type, file_name=None):
        if not self.db.create_task(task_id, task_type, file_name):
            raise TaskExecutionError("创建任务失败，请稍后重试", code="task_create_failed", status=500)
        return True

    def update_status(self, task_id, status, processed_frames=None, total_frames=None):
        self.db.update_task_status(task_id, status, processed_frames, total_frames)

    def save_student_detection(self, *args, **kwargs):
        self.db.save_student_detection(*args, **kwargs)

    def save_teacher_detection(self, *args, **kwargs):
        self.db.save_teacher_detection(*args, **kwargs)

    def save_student_detections_bulk(self, *args, **kwargs):
        self.db.save_student_detections_bulk(*args, **kwargs)

    def save_teacher_detections_bulk(self, *args, **kwargs):
        self.db.save_teacher_detections_bulk(*args, **kwargs)

    def save_summary(self, *args, **kwargs):
        if kwargs:
            task_id = args[0] if args else kwargs.get("task_id")
            self.db.save_summary(
                task_id,
                kwargs.get("student_behavior_stats", {}),
                kwargs.get("teacher_behavior_stats", {}),
                kwargs.get("total_detections", 0),
                kwargs.get("average_confidence", 0.0),
                kwargs.get("duration", 0.0),
                display_metrics=kwargs.get("display_metrics", {}),
                derived_metrics=kwargs.get("derived_metrics", {}),
            )
            return
        self.db.save_summary(*args)

    def get_task(self, task_id):
        return self.db.get_task_info(task_id)

    def get_summary(self, task_id):
        return self.db.get_task_summary(task_id)

    def get_recent_tasks(self, limit=20, include_summary=True):
        if include_summary:
            return self.db.get_recent_tasks_with_summary(limit)
        return self.db.get_recent_tasks(limit)

    def get_task_detections(self, task_id, frame_number=None):
        return self.db.get_task_detections(task_id, frame_number)

    def save_task_asset(self, *args, **kwargs):
        self.db.save_task_asset(*args, **kwargs)

    def get_task_assets(self, task_id):
        return self.db.get_task_assets(task_id)

    def build_result_urls(self, task_id, file_name, task_type):
        urls = {"original": None, "result": None, "report": f"/api/tasks/{task_id}/report", "results": []}
        indexed_assets = self.get_task_assets(task_id)
        if indexed_assets:
            return self._build_urls_from_assets(indexed_assets, urls)
        if not file_name:
            return urls

        original_matches = self._find_files(Config.UPLOAD_FOLDER, task_id, file_name)
        if original_matches:
            urls["original"] = f"/uploads/{original_matches[0]}"

        if task_type == "image":
            result_matches = self._find_files(Config.OUTPUT_FOLDER, f"result_{task_id}", file_name)
            if result_matches:
                urls["result"] = f"/outputs/{result_matches[0]}"
        elif task_type == "video":
            result_matches = self._find_files(Config.OUTPUT_FOLDER, f"result_{task_id}", file_name)
            if result_matches:
                urls["result"] = f"/outputs/{result_matches[0]}"
        elif task_type == "webcam":
            result_matches = self._find_files(Config.OUTPUT_FOLDER, f"result_{task_id}", file_name)
            if result_matches:
                urls["result"] = f"/outputs/{result_matches[0]}"
        elif task_type == "batch":
            result_matches = self._find_files(Config.OUTPUT_FOLDER, f"result_{task_id}", "")
            original_files = self._find_files(Config.UPLOAD_FOLDER, task_id, "")
            original_by_index = {self._extract_batch_index(name, task_id, False): name for name in original_files}
            urls["results"] = []
            for name in result_matches:
                batch_index = self._extract_batch_index(name, task_id, True)
                urls["results"].append(
                    {
                        "original": f"/uploads/{original_by_index[batch_index]}" if batch_index in original_by_index else None,
                        "result": f"/outputs/{name}",
                        "filename": self._extract_batch_filename(name, task_id, True),
                        "frame_number": batch_index,
                    }
                )
            urls["results"].sort(key=lambda item: item.get("frame_number", 0))
            if urls["results"]:
                urls["original"] = urls["results"][0]["original"]
                urls["result"] = urls["results"][0]["result"]
        return urls

    def _build_urls_from_assets(self, indexed_assets, urls):
        originals = {}
        results = {}
        report_url = urls["report"]
        for asset in indexed_assets:
            relative_path = asset.get("relative_path")
            if not relative_path:
                continue
            role = asset.get("asset_role")
            frame_number = asset.get("frame_number")
            file_label = asset.get("file_name")
            if role == "original":
                url = f"/uploads/{relative_path}"
                if frame_number is None:
                    urls["original"] = url
                else:
                    originals[frame_number] = {"original": url, "filename": file_label, "frame_number": frame_number}
            elif role == "result":
                url = f"/outputs/{relative_path}"
                if frame_number is None:
                    urls["result"] = url
                else:
                    results[frame_number] = {"result": url, "filename": file_label, "frame_number": frame_number}
            elif role == "report":
                report_url = f"/outputs/{relative_path}"

        if originals or results:
            frame_numbers = sorted(set(originals.keys()) | set(results.keys()))
            urls["results"] = []
            for frame_number in frame_numbers:
                urls["results"].append(
                    {
                        "original": originals.get(frame_number, {}).get("original"),
                        "result": results.get(frame_number, {}).get("result"),
                        "filename": (
                            results.get(frame_number, {}).get("filename")
                            or originals.get(frame_number, {}).get("filename")
                        ),
                        "frame_number": frame_number,
                    }
                )
            if urls["results"]:
                urls["original"] = urls["results"][0]["original"] or urls["original"]
                urls["result"] = urls["results"][0]["result"] or urls["result"]

        urls["report"] = report_url
        return urls

    @staticmethod
    def _find_files(folder: Path, prefix: str, file_name: str):
        folder = Path(folder)
        candidates = sorted(folder.glob(f"{prefix}*"))
        if candidates:
            return [item.name for item in candidates]
        clean_name = Path(file_name).name
        for candidate in folder.glob(f"*{clean_name}*"):
            return [candidate.name]
        return []

    @staticmethod
    def _extract_batch_index(file_name: str, task_id: str, result_file: bool) -> int:
        parts = Path(file_name).name.split("_")
        offset = 2 if result_file else 1
        try:
            if len(parts) > offset and parts[offset - 1] == task_id:
                return int(parts[offset])
        except (TypeError, ValueError):
            pass
        return 0

    @staticmethod
    def _extract_batch_filename(file_name: str, task_id: str, result_file: bool) -> str:
        parts = Path(file_name).name.split("_")
        offset = 3 if result_file else 2
        if result_file and len(parts) > 3 and parts[1] == task_id:
            return "_".join(parts[3:])
        if not result_file and len(parts) > 2 and parts[0] == task_id:
            return "_".join(parts[2:])
        return Path(file_name).name
