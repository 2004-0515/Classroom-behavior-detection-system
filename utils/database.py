import sqlite3
from datetime import datetime
import json
from typing import List, Dict, Any
from config import Config


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 检测记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                task_type TEXT NOT NULL,
                file_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'processing',
                total_frames INTEGER DEFAULT 0,
                processed_frames INTEGER DEFAULT 0
            )
        ''')
        
        # 学生行为检测结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS student_detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                frame_number INTEGER,
                timestamp REAL,
                behavior TEXT NOT NULL,
                confidence REAL,
                track_id INTEGER,
                bbox_x1 REAL,
                bbox_y1 REAL,
                bbox_x2 REAL,
                bbox_y2 REAL,
                FOREIGN KEY (task_id) REFERENCES detection_records (task_id)
            )
        ''')
        
        # 人头行为检测结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teacher_detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                frame_number INTEGER,
                timestamp REAL,
                behavior TEXT NOT NULL,
                confidence REAL,
                track_id INTEGER,
                bbox_x1 REAL,
                bbox_y1 REAL,
                bbox_x2 REAL,
                bbox_y2 REAL,
                FOREIGN KEY (task_id) REFERENCES detection_records (task_id)
            )
        ''')
        
        # 统计摘要表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                student_behavior_stats TEXT,
                teacher_behavior_stats TEXT,
                total_detections INTEGER,
                average_confidence REAL,
                duration REAL,
                display_metrics TEXT,
                derived_metrics TEXT,
                FOREIGN KEY (task_id) REFERENCES detection_records (task_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                asset_key TEXT NOT NULL,
                asset_role TEXT NOT NULL,
                frame_number INTEGER,
                file_name TEXT,
                relative_path TEXT NOT NULL,
                media_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, asset_key),
                FOREIGN KEY (task_id) REFERENCES detection_records (task_id)
            )
        ''')

        self._ensure_column(cursor, "student_detections", "track_id", "INTEGER")
        self._ensure_column(cursor, "teacher_detections", "track_id", "INTEGER")
        self._ensure_column(cursor, "detection_summary", "display_metrics", "TEXT")
        self._ensure_column(cursor, "detection_summary", "derived_metrics", "TEXT")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_detection_records_task_created "
            "ON detection_records (task_id, created_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_student_detections_task_frame "
            "ON student_detections (task_id, frame_number)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_student_detections_task_track "
            "ON student_detections (task_id, track_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_teacher_detections_task_frame "
            "ON teacher_detections (task_id, frame_number)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_teacher_detections_task_track "
            "ON teacher_detections (task_id, track_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_assets_task_role_frame "
            "ON task_assets (task_id, asset_role, frame_number)"
        )
        
        conn.commit()
        conn.close()

    @staticmethod
    def _ensure_column(cursor, table_name: str, column_name: str, definition: str):
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing = {row[1] for row in cursor.fetchall()}
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
    
    def create_task(self, task_id: str, task_type: str, file_name: str = None) -> bool:
        """创建新的检测任务"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO detection_records (task_id, task_type, file_name, status)
                VALUES (?, ?, ?, 'processing')
            ''', (task_id, task_type, file_name))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error creating task: {e}")
            return False
        finally:
            if conn is not None:
                conn.close()
    
    def update_task_status(self, task_id: str, status: str, processed_frames: int = None, total_frames: int = None):
        """更新任务状态"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = "UPDATE detection_records SET status = ?"
        params = [status]
        
        if status in {'completed', 'failed', 'stopped_partial'}:
            sql += ", completed_at = ?"
            params.append(datetime.now().isoformat())
        
        if processed_frames is not None:
            sql += ", processed_frames = ?"
            params.append(processed_frames)
        
        if total_frames is not None:
            sql += ", total_frames = ?"
            params.append(total_frames)
        
        sql += " WHERE task_id = ?"
        params.append(task_id)
        
        cursor.execute(sql, params)
        conn.commit()
        conn.close()
    
    def save_student_detection(self, task_id: str, frame_number: int, timestamp: float,
                               behavior: str, confidence: float, bbox: List[float]):
        """保存学生行为检测结果"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO student_detections 
            (task_id, frame_number, timestamp, behavior, confidence, track_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, frame_number, timestamp, behavior, confidence, None, *bbox))
        conn.commit()
        conn.close()
    
    def save_teacher_detection(self, task_id: str, frame_number: int, timestamp: float,
                               behavior: str, confidence: float, bbox: List[float]):
        """保存人头行为检测结果"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO teacher_detections 
            (task_id, frame_number, timestamp, behavior, confidence, track_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, frame_number, timestamp, behavior, confidence, None, *bbox))
        conn.commit()
        conn.close()

    def _save_detections_bulk(self, table_name: str, task_id: str, frame_number: int, timestamp: float,
                              detections: List[Dict[str, Any]]):
        if not detections:
            return

        rows = [
            (
                task_id,
                frame_number,
                timestamp,
                item["behavior"],
                item["confidence"],
                item.get("track_id"),
                *item["bbox"],
            )
            for item in detections
        ]

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.executemany(
            f'''
                INSERT INTO {table_name}
                (task_id, frame_number, timestamp, behavior, confidence, track_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            rows,
        )
        conn.commit()
        conn.close()

    def save_student_detections_bulk(self, task_id: str, frame_number: int, timestamp: float,
                                     detections: List[Dict[str, Any]]):
        """批量保存学生行为检测结果"""
        self._save_detections_bulk("student_detections", task_id, frame_number, timestamp, detections)

    def save_teacher_detections_bulk(self, task_id: str, frame_number: int, timestamp: float,
                                     detections: List[Dict[str, Any]]):
        """批量保存人头行为检测结果"""
        self._save_detections_bulk("teacher_detections", task_id, frame_number, timestamp, detections)
    
    def save_summary(self, task_id: str, student_stats: Dict, teacher_stats: Dict,
                     total_detections: int, avg_confidence: float, duration: float,
                     display_metrics: Dict | None = None, derived_metrics: Dict | None = None):
        """保存检测摘要"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 确保统计数据是字典类型
        if not isinstance(student_stats, dict):
            student_stats = {}
        if not isinstance(teacher_stats, dict):
            teacher_stats = {}
        
        cursor.execute('''
            INSERT OR REPLACE INTO detection_summary 
            (task_id, student_behavior_stats, teacher_behavior_stats, 
             total_detections, average_confidence, duration, display_metrics, derived_metrics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, json.dumps(student_stats, ensure_ascii=False), 
              json.dumps(teacher_stats, ensure_ascii=False),
              int(total_detections) if total_detections else 0, 
              float(avg_confidence) if avg_confidence else 0.0, 
              float(duration) if duration else 0.0,
              json.dumps(display_metrics or {}, ensure_ascii=False),
              json.dumps(derived_metrics or {}, ensure_ascii=False)))
        conn.commit()
        conn.close()
    
    def get_task_info(self, task_id: str) -> Dict[str, Any]:
        """获取任务信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM detection_records WHERE task_id = ?', (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        """获取任务摘要"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 获取基本信息
        cursor.execute('SELECT * FROM detection_records WHERE task_id = ?', (task_id,))
        task_row = cursor.fetchone()
        task_info = dict(task_row) if task_row else {}
        
        # 获取摘要统计
        cursor.execute('SELECT * FROM detection_summary WHERE task_id = ?', (task_id,))
        summary_row = cursor.fetchone()
        
        if summary_row:
            summary = dict(summary_row)
            summary["student_behavior_stats"] = self._parse_json_stats(summary.get("student_behavior_stats"))
            summary["teacher_behavior_stats"] = self._parse_json_stats(summary.get("teacher_behavior_stats"))
            summary["display_metrics"] = self._parse_json_stats(summary.get("display_metrics"))
            summary["derived_metrics"] = self._parse_json_stats(summary.get("derived_metrics"))
        else:
            summary = {}
        
        conn.close()
        
        return {**task_info, **summary}
    
    def get_recent_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的任务列表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM detection_records 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def get_recent_tasks_with_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的任务列表及摘要"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
                SELECT dr.*,
                       ds.total_detections,
                       ds.average_confidence,
                       ds.duration,
                       ds.display_metrics,
                       ds.derived_metrics,
                       ds.student_behavior_stats,
                       ds.teacher_behavior_stats
                FROM detection_records dr
                LEFT JOIN detection_summary ds ON ds.task_id = dr.task_id
                ORDER BY dr.created_at DESC
                LIMIT ?
            ''',
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for row in rows:
            item = dict(row)
            item["student_behavior_stats"] = self._parse_json_stats(item.get("student_behavior_stats"))
            item["teacher_behavior_stats"] = self._parse_json_stats(item.get("teacher_behavior_stats"))
            item["display_metrics"] = self._parse_json_stats(item.get("display_metrics"))
            item["derived_metrics"] = self._parse_json_stats(item.get("derived_metrics"))
            item["total_detections"] = int(item.get("total_detections") or 0)
            item["average_confidence"] = float(item.get("average_confidence") or 0.0)
            item["duration"] = float(item.get("duration") or 0.0)
            tasks.append(item)
        return tasks

    def get_task_detections(self, task_id: str, frame_number: int = None) -> Dict[str, List[Dict[str, Any]]]:
        """获取任务检测框详情"""
        conn = self.get_connection()
        cursor = conn.cursor()

        def fetch_rows(table_name: str):
            if frame_number is None:
                cursor.execute(
                    f'''
                        SELECT frame_number, timestamp, behavior, confidence, track_id,
                               bbox_x1, bbox_y1, bbox_x2, bbox_y2
                        FROM {table_name}
                        WHERE task_id = ?
                        ORDER BY frame_number ASC, id ASC
                    ''',
                    (task_id,),
                )
            else:
                cursor.execute(
                    f'''
                        SELECT frame_number, timestamp, behavior, confidence, track_id,
                               bbox_x1, bbox_y1, bbox_x2, bbox_y2
                        FROM {table_name}
                        WHERE task_id = ? AND frame_number = ?
                        ORDER BY id ASC
                    ''',
                    (task_id, frame_number),
                )
            detection_rows = cursor.fetchall()
            items = []
            track_ranges: Dict[int, Dict[str, int]] = {}
            cursor.execute(
                f'''
                    SELECT track_id,
                           MIN(frame_number) AS first_frame,
                           MAX(frame_number) AS last_frame,
                           COUNT(*) AS hits
                    FROM {table_name}
                    WHERE task_id = ? AND track_id IS NOT NULL
                    GROUP BY track_id
                ''',
                (task_id,),
            )
            for track_row in cursor.fetchall():
                info = dict(track_row)
                if info.get("track_id") is None:
                    continue
                track_ranges[int(info["track_id"])] = {
                    "track_first_frame": int(info.get("first_frame") or 0),
                    "track_last_frame": int(info.get("last_frame") or 0),
                    "track_hits": int(info.get("hits") or 0),
                }
            for row in detection_rows:
                item = dict(row)
                item["bbox"] = [
                    float(item.pop("bbox_x1")),
                    float(item.pop("bbox_y1")),
                    float(item.pop("bbox_x2")),
                    float(item.pop("bbox_y2")),
                ]
                item["confidence"] = float(item.get("confidence") or 0.0)
                if item.get("track_id") is not None:
                    item["track_id"] = int(item["track_id"])
                    lifecycle = track_ranges.get(item["track_id"], {})
                    item.update(lifecycle)
                    if lifecycle:
                        item["track_span_frames"] = int(lifecycle["track_last_frame"] - lifecycle["track_first_frame"] + 1)
                items.append(item)
            return items

        payload = {
            "student_detections": fetch_rows("student_detections"),
            "teacher_detections": fetch_rows("teacher_detections"),
        }
        conn.close()
        return payload

    def save_task_asset(self, task_id: str, asset_role: str, relative_path: str, *,
                        media_type: str = None, frame_number: int = None, file_name: str = None):
        asset_key = f"{asset_role}:{frame_number if frame_number is not None else 'single'}"
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
                INSERT OR REPLACE INTO task_assets
                (task_id, asset_key, asset_role, frame_number, file_name, relative_path, media_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (task_id, asset_key, asset_role, frame_number, file_name, relative_path, media_type),
        )
        conn.commit()
        conn.close()

    def get_task_assets(self, task_id: str) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
                SELECT task_id, asset_role, frame_number, file_name, relative_path, media_type
                FROM task_assets
                WHERE task_id = ?
                ORDER BY
                    CASE asset_role
                        WHEN 'original' THEN 1
                        WHEN 'result' THEN 2
                        WHEN 'report' THEN 3
                        ELSE 99
                    END,
                    frame_number ASC,
                    id ASC
            ''',
            (task_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def _parse_json_stats(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

