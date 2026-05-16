import json
import os
import secrets
from pathlib import Path

# 基础路径
BASE_DIR = Path(__file__).resolve().parent


def _load_or_create_runtime_secret(secret_path: Path) -> str:
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_path.exists():
        try:
            payload = json.loads(secret_path.read_text(encoding="utf-8"))
            value = payload.get("secret_key")
            if value:
                return value
        except Exception:
            pass

    value = secrets.token_urlsafe(48)
    secret_path.write_text(json.dumps({"secret_key": value}, ensure_ascii=False, indent=2), encoding="utf-8")
    return value

# Flask配置
class Config:
    RUNTIME_SECRET_PATH = Path(os.environ.get('RUNTIME_SECRET_PATH') or BASE_DIR / 'data' / 'runtime_secrets.json')
    SECRET_KEY = os.environ.get('SECRET_KEY') or _load_or_create_runtime_secret(RUNTIME_SECRET_PATH)
    SESSION_COOKIE_NAME = 'classroom_behavior_session'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    JSON_AS_ASCII = False
    TEMPLATES_AUTO_RELOAD = True
    YOLO_CONFIG_DIR = os.environ.get('YOLO_CONFIG_DIR') or str(BASE_DIR / 'data' / 'yolo_config')
    
    # 文件上传配置
    UPLOAD_FOLDER = Path(os.environ.get('UPLOAD_FOLDER') or BASE_DIR / 'uploads')
    OUTPUT_FOLDER = Path(os.environ.get('OUTPUT_FOLDER') or BASE_DIR / 'outputs')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'mp4', 'avi', 'mov', 'mkv'}
    
    # 模型配置
    MODEL_FOLDER = BASE_DIR / 'models'
    STUDENT_MODEL_PATH = os.environ.get('STUDENT_MODEL_PATH') or str(MODEL_FOLDER / 'behavior.pt')
    TEACHER_MODEL_PATH = os.environ.get('TEACHER_MODEL_PATH') or str(MODEL_FOLDER / 'head.pt')
    
    # 数据库配置
    DATABASE_PATH = Path(os.environ.get('DATABASE_PATH') or BASE_DIR / 'data' / 'detections.db')
    USER_CONFIG_PATH = Path(os.environ.get('USER_CONFIG_PATH') or BASE_DIR / 'data' / 'user_config.json')
    ADMIN_CONFIG_PATH = Path(os.environ.get('ADMIN_CONFIG_PATH') or BASE_DIR / 'data' / 'admin_config.json')
    DEFAULT_ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or None
    DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or None
    
    # YOLO默认参数
    DEFAULT_CONF_THRESHOLD = 0.25
    DEFAULT_IOU_THRESHOLD = 0.45
    DEFAULT_IMG_SIZE = 640
    
    # 视频处理配置
    VIDEO_FRAME_SKIP = 2  # 每隔N帧处理一次，提高性能
    MAX_FPS = 30
    HISTORY_RECENT_LIMIT = 18
    HISTORY_POLL_INTERVAL_MS = 10000
    TASK_POLL_INTERVAL_MS = 2500
    PREVIEW_QUEUE_SIZE = 48
    REPORT_REUSE_ENABLED = True
    VIDEO_STOP_STATUS = "stopped_partial"
    
    # ==========================================
    # 注意：行为类别现在会自动从模型中读取！
    # 以下是示例配置，仅用于参考
    # ==========================================
    
    # 学生行为类别示例（实际类别由模型决定）
    STUDENT_BEHAVIORS_EXAMPLE = [
        '举手', '听讲', '看书', '写字', '讨论', 
        '睡觉', '玩手机', '东张西望', '趴桌子'
    ]
    
    # 人头行为类别示例（实际类别由模型决定）
    TEACHER_BEHAVIORS_EXAMPLE = [
        '讲课', '板书', '提问', '巡视', 
        '演示', '互动', '观察学生'
    ]

# 创建必要的文件夹
def create_directories():
    dirs = [
        Config.UPLOAD_FOLDER,
        Config.OUTPUT_FOLDER,
        Config.MODEL_FOLDER,
        Config.DATABASE_PATH.parent,
        Path(Config.YOLO_CONFIG_DIR)
    ]
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)

