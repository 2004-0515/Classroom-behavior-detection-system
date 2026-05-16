import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


class UserConfig:
    """用户配置管理类"""
    
    def __init__(self, config_path: str = None):
        """
        初始化用户配置
        
        Args:
            config_path: 配置文件路径，默认为 data/user_config.json
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'data' / 'user_config.json'
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'version': '1.2.0',
            'first_run': True,
            'last_models': {
                'student': None,
                'teacher': None
            },
            'detection_params': {
                'confidence': 0.25,
                'iou': 0.45,
                'frame_skip': 2
            },
            'ui_settings': {
                'auto_scan_models': True,
                'show_confidence': True,
                'show_bbox_labels': True,
                'default_mode': 'image'
            },
            'history_limit': 50,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
    
    def save_config(self):
        """保存配置到文件"""
        try:
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 更新最后修改时间
            self.config['last_updated'] = datetime.now().isoformat()
            
            # 写入文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def get(self, key: str, default=None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self.config
        
        # 导航到最后一级
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 设置值
        config[keys[-1]] = value
    
    def is_first_run(self) -> bool:
        """是否首次运行"""
        return self.config.get('first_run', True)
    
    def mark_first_run_done(self):
        """标记首次运行完成"""
        self.config['first_run'] = False
        self.save_config()
    
    def save_last_models(self, student_model: str = None, teacher_model: str = None):
        """保存最后使用的模型"""
        if student_model:
            self.set('last_models.student', student_model)
        if teacher_model:
            self.set('last_models.teacher', teacher_model)
        self.save_config()
    
    def get_last_models(self) -> Dict[str, str]:
        """获取最后使用的模型"""
        return self.config.get('last_models', {'student': None, 'teacher': None})
    
    def save_detection_params(self, confidence: float = None, iou: float = None, frame_skip: int = None):
        """保存检测参数"""
        if confidence is not None:
            self.set('detection_params.confidence', confidence)
        if iou is not None:
            self.set('detection_params.iou', iou)
        if frame_skip is not None:
            self.set('detection_params.frame_skip', frame_skip)
        self.save_config()
    
    def get_detection_params(self) -> Dict[str, Any]:
        """获取检测参数"""
        return self.config.get('detection_params', {
            'confidence': 0.25,
            'iou': 0.45,
            'frame_skip': 2
        })
    
    def get_ui_settings(self) -> Dict[str, Any]:
        """获取UI设置"""
        return self.config.get('ui_settings', {
            'auto_scan_models': True,
            'show_confidence': True,
            'show_bbox_labels': True,
            'default_mode': 'image'
        })
    
    def save_ui_settings(self, settings: Dict[str, Any]):
        """保存UI设置"""
        current = self.get_ui_settings()
        current.update(settings)
        self.set('ui_settings', current)
        self.save_config()
    
    def reset_to_default(self):
        """重置为默认配置"""
        self.config = self._get_default_config()
        self.save_config()

