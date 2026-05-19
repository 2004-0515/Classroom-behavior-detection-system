import os
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Any
import time
from collections import defaultdict, deque

from tracking_fallback import (
    TRACK_ID_FALLBACK_IOU,
    TRACK_ID_FALLBACK_MAX_FRAME_GAP,
    TrackAssignmentState,
    assign_track_ids_for_frame,
)

def _prepare_yolo_runtime() -> None:
    project_root = Path(__file__).resolve().parent.parent
    yolo_config_dir = Path(os.environ.get("YOLO_CONFIG_DIR") or project_root / "data" / "yolo_config")
    yolo_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config_dir))


_prepare_yolo_runtime()

from ultralytics import YOLO

TRACKER_CONFIG = "bytetrack.yaml"


def _draw_detection(image: np.ndarray, *, bbox: list[float], label: str, color: tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = [int(value) for value in bbox]
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        image,
        label,
        (x1, max(18, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
    )


class TrackingRuntime:
    def __init__(self, student_model_path: str, teacher_model_path: str, conf_threshold: float, iou_threshold: float, img_size: int):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.student_model = YOLO(student_model_path) if student_model_path and Path(student_model_path).exists() else None
        self.teacher_model = YOLO(teacher_model_path) if teacher_model_path and Path(teacher_model_path).exists() else None
        self._frame_index = 0
        self._fallback_trackers = {
            "student": TrackAssignmentState(),
            "teacher": TrackAssignmentState(),
        }

    def _assign_fallback_track_ids(self, source: str, detections: List[Dict[str, Any]]) -> None:
        state = self._fallback_trackers[source]
        assignments = assign_track_ids_for_frame(
            [
                (
                    detection,
                    tuple(float(value) for value in detection["bbox"]),
                    int(detection["track_id"]) if detection.get("track_id") is not None else None,
                )
                for detection in detections
            ],
            frame_number=self._frame_index,
            state=state,
            iou_threshold=TRACK_ID_FALLBACK_IOU,
            max_frame_gap=TRACK_ID_FALLBACK_MAX_FRAME_GAP,
        )
        for detection, track_id in assignments:
            detection["track_id"] = int(track_id)

    def detect_image(self, image: np.ndarray) -> Dict[str, Any]:
        self._frame_index += 1
        results = {
            "student_detections": [],
            "teacher_detections": [],
            "annotated_image": image.copy(),
            "student_behavior_counts": {},
            "teacher_behavior_counts": {},
        }
        for source, model, color in (
            ("student", self.student_model, (255, 0, 0)),
            ("teacher", self.teacher_model, (0, 255, 0)),
        ):
            if not model:
                continue
            tracked_results = model.track(
                image,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.img_size,
                verbose=False,
                persist=True,
                tracker=TRACKER_CONFIG,
            )
            source_detections = []
            for result in tracked_results:
                boxes = result.boxes
                track_ids = boxes.id.int().cpu().tolist() if getattr(boxes, "id", None) is not None else [None] * len(boxes)
                for index, box in enumerate(boxes):
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = result.names[cls]
                    track_id = int(track_ids[index]) if track_ids[index] is not None else None
                    source_detections.append(
                        {
                            "behavior": label,
                            "confidence": conf,
                            "bbox": [float(x1), float(y1), float(x2), float(y2)],
                            "track_id": track_id,
                        }
                    )
            self._assign_fallback_track_ids(source, source_detections)
            bucket = results[f"{source}_behavior_counts"]
            for item in source_detections:
                results[f"{source}_detections"].append(item)
                bucket[item["behavior"]] = bucket.get(item["behavior"], 0) + 1
                track_id = item.get("track_id")
                display_label = "{} #{} {:.2f}".format(item["behavior"], track_id, item["confidence"]) if track_id is not None else "{} {:.2f}".format(item["behavior"], item["confidence"])
                _draw_detection(results["annotated_image"], bbox=item["bbox"], label=display_label, color=color)
        return results

class BehaviorDetector:
    """双模型行为检测器"""
    
    @staticmethod
    def scan_models_directory(models_dir: str) -> List[Dict[str, Any]]:
        """
        扫描模型目录并获取所有模型的信息
        
        Args:
            models_dir: 模型目录路径
            
        Returns:
            模型信息列表
        """
        models_info = []
        models_path = Path(models_dir)
        
        if not models_path.exists():
            return models_info
        
        # 递归查找所有.pt文件，兼容训练输出目录中的best.pt/last.pt
        pt_files = list(models_path.rglob('*.pt'))
        
        for pt_file in pt_files:
            try:
                # 临时加载模型获取信息
                temp_model = YOLO(str(pt_file))
                
                # 提取类别信息
                classes = []
                if hasattr(temp_model, 'names'):
                    names_dict = temp_model.names
                    classes = [names_dict[i] for i in sorted(names_dict.keys())]
                
                # 获取文件大小
                file_size = pt_file.stat().st_size / (1024 * 1024)  # MB
                
                models_info.append({
                    'filename': pt_file.name,
                    'path': str(pt_file),
                    'num_classes': len(classes),
                    'classes': classes,
                    'file_size_mb': round(file_size, 2),
                    'task': getattr(temp_model, 'task', 'detect')
                })
                
                # 释放模型
                del temp_model
                
            except Exception as e:
                print(f"无法读取模型 {pt_file.name}: {e}")
                models_info.append({
                    'filename': pt_file.name,
                    'path': str(pt_file),
                    'error': str(e)
                })
        
        return models_info
    
    def __init__(self, student_model_path: str, teacher_model_path: str,
                 conf_threshold: float = 0.25, iou_threshold: float = 0.45, img_size: int = 640):
        """
        初始化检测器
        
        Args:
            student_model_path: 学生行为模型路径
            teacher_model_path: 人头行为模型路径
            conf_threshold: 置信度阈值
            iou_threshold: IOU阈值
            img_size: 输入图像大小
        """
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        
        # 模型路径
        self.student_model_path = student_model_path
        self.teacher_model_path = teacher_model_path
        
        # 自动识别的类别信息
        self.student_classes = []
        self.teacher_classes = []
        
        # 加载模型
        try:
            self.student_model = YOLO(student_model_path) if Path(student_model_path).exists() else None
            self.teacher_model = YOLO(teacher_model_path) if Path(teacher_model_path).exists() else None
            
            if self.student_model:
                self.student_classes = self._get_model_classes(self.student_model)
                print(f"✓ 学生行为模型加载成功: {student_model_path}")
                print(f"  类别数量: {len(self.student_classes)}")
                print(f"  类别列表: {', '.join(self.student_classes)}")
            else:
                print(f"✗ 学生行为模型未找到: {student_model_path}")
                
            if self.teacher_model:
                self.teacher_classes = self._get_model_classes(self.teacher_model)
                print(f"✓ 人头行为模型加载成功: {teacher_model_path}")
                print(f"  类别数量: {len(self.teacher_classes)}")
                print(f"  类别列表: {', '.join(self.teacher_classes)}")
            else:
                print(f"✗ 人头行为模型未找到: {teacher_model_path}")
                
        except Exception as e:
            print(f"模型加载错误: {e}")
            self.student_model = None
            self.teacher_model = None
        
        # 行为统计
        self.student_behavior_counts = defaultdict(int)
        self.teacher_behavior_counts = defaultdict(int)
        
        # 用于实时统计的滑动窗口
        self.recent_student_behaviors = deque(maxlen=30)  # 保留最近30帧
        self.recent_teacher_behaviors = deque(maxlen=30)
    
    def _get_model_classes(self, model) -> List[str]:
        """
        从模型中提取类别名称列表
        
        Args:
            model: YOLO模型对象
            
        Returns:
            类别名称列表
        """
        try:
            if model and hasattr(model, 'names'):
                # YOLOv8模型的names属性是一个字典: {0: 'class1', 1: 'class2', ...}
                names_dict = model.names
                # 按照索引排序并提取类别名称
                classes = [names_dict[i] for i in sorted(names_dict.keys())]
                return classes
            return []
        except Exception as e:
            print(f"获取模型类别失败: {e}")
            return []
    
    def get_model_info(self, model_type: str) -> Dict[str, Any]:
        """
        获取指定模型的详细信息
        
        Args:
            model_type: 'student' 或 'teacher'
            
        Returns:
            模型信息字典
        """
        if model_type == 'student':
            model = self.student_model
            classes = self.student_classes
            path = self.student_model_path
        elif model_type == 'teacher':
            model = self.teacher_model
            classes = self.teacher_classes
            path = self.teacher_model_path
        else:
            return {}
        
        if model is None:
            return {
                'loaded': False,
                'path': path,
                'error': '模型未加载'
            }
        
        try:
            return {
                'loaded': True,
                'path': path,
                'num_classes': len(classes),
                'classes': classes,
                'model_type': model_type,
                'task': getattr(model, 'task', 'detect')
            }
        except Exception as e:
            return {
                'loaded': False,
                'path': path,
                'error': str(e)
            }

    def create_tracking_runtime(self):
        return TrackingRuntime(
            student_model_path=self.student_model_path,
            teacher_model_path=self.teacher_model_path,
            conf_threshold=self.conf_threshold,
            iou_threshold=self.iou_threshold,
            img_size=self.img_size,
        )
    
    def update_parameters(self, conf_threshold: float = None, iou_threshold: float = None, img_size: int = None):
        """更新检测参数"""
        if conf_threshold is not None:
            self.conf_threshold = conf_threshold
            print(f"[Detector] 更新置信度阈值: {self.conf_threshold}")
        if iou_threshold is not None:
            self.iou_threshold = iou_threshold
            print(f"[Detector] 更新IOU阈值: {self.iou_threshold}")
        if img_size is not None:
            self.img_size = img_size
            print(f"[Detector] 更新图像大小: {self.img_size}")
    
    def load_model(self, model_type: str, model_path: str):
        """动态加载模型并自动识别类别"""
        try:
            model = YOLO(model_path)
            classes = self._get_model_classes(model)
            
            if model_type == 'student':
                self.student_model = model
                self.student_model_path = model_path
                self.student_classes = classes
                print(f"✓ 学生模型重新加载: {model_path}")
                print(f"  类别数量: {len(classes)}")
                print(f"  类别列表: {', '.join(classes)}")
            elif model_type == 'teacher':
                self.teacher_model = model
                self.teacher_model_path = model_path
                self.teacher_classes = classes
                print(f"✓ 人头模型重新加载: {model_path}")
                print(f"  类别数量: {len(classes)}")
                print(f"  类别列表: {', '.join(classes)}")
            
            return True
        except Exception as e:
            print(f"模型加载失败: {e}")
            return False
    
    def detect_image(self, image: np.ndarray) -> Dict[str, Any]:
        """
        对单张图片进行检测
        
        Args:
            image: OpenCV格式的图像（BGR）
            
        Returns:
            检测结果字典
        """
        results = {
            'student_detections': [],
            'teacher_detections': [],
            'annotated_image': image.copy(),
            'student_behavior_counts': {},
            'teacher_behavior_counts': {}
        }
        
        # 学生行为检测
        if self.student_model:
            student_results = self.student_model.predict(
                image,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.img_size,
                verbose=False
            )
            
            for result in student_results:
                boxes = result.boxes
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = result.names[cls]
                    
                    results['student_detections'].append({
                        'behavior': label,
                        'confidence': conf,
                        'bbox': [float(x1), float(y1), float(x2), float(y2)]
                    })
                    
                    # 统计
                    results['student_behavior_counts'][label] = \
                        results['student_behavior_counts'].get(label, 0) + 1
                    
                    # 绘制边界框（蓝色）
                    cv2.rectangle(results['annotated_image'], 
                                (int(x1), int(y1)), (int(x2), int(y2)), 
                                (255, 0, 0), 2)
                    cv2.putText(results['annotated_image'], 
                              f'{label} {conf:.2f}',
                              (int(x1), int(y1) - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        
        # 人头行为检测
        if self.teacher_model:
            teacher_results = self.teacher_model.predict(
                image,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.img_size,
                verbose=False
            )
            
            for result in teacher_results:
                boxes = result.boxes
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = result.names[cls]
                    
                    results['teacher_detections'].append({
                        'behavior': label,
                        'confidence': conf,
                        'bbox': [float(x1), float(y1), float(x2), float(y2)]
                    })
                    
                    # 统计
                    results['teacher_behavior_counts'][label] = \
                        results['teacher_behavior_counts'].get(label, 0) + 1
                    
                    # 绘制边界框（绿色）
                    cv2.rectangle(results['annotated_image'], 
                                (int(x1), int(y1)), (int(x2), int(y2)), 
                                (0, 255, 0), 2)
                    cv2.putText(results['annotated_image'], 
                              f'{label} {conf:.2f}',
                              (int(x1), int(y1) - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return results
    
    def detect_video(self, video_path: str, output_path: str, 
                    frame_skip: int = 1, progress_callback=None) -> Dict[str, Any]:
        """
        对视频进行检测
        
        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径
            frame_skip: 跳帧数（提高处理速度）
            progress_callback: 进度回调函数
            
        Returns:
            检测统计结果
        """
        cap = cv2.VideoCapture(video_path)
        
        # 获取视频属性
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 创建视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        # 统计信息
        frame_count = 0
        processed_count = 0
        student_stats = defaultdict(int)
        teacher_stats = defaultdict(int)
        all_confidences = []
        
        start_time = time.time()
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 跳帧处理
            if frame_count % (frame_skip + 1) != 0:
                out.write(frame)
                continue
            
            # 执行检测
            results = self.detect_image(frame)
            
            # 统计
            for det in results['student_detections']:
                student_stats[det['behavior']] += 1
                all_confidences.append(det['confidence'])
            
            for det in results['teacher_detections']:
                teacher_stats[det['behavior']] += 1
                all_confidences.append(det['confidence'])
            
            # 写入处理后的帧
            out.write(results['annotated_image'])
            
            processed_count += 1
            
            # 进度回调
            if progress_callback:
                progress = (frame_count / total_frames) * 100
                progress_callback(progress, frame_count, total_frames)
        
        cap.release()
        out.release()
        
        duration = time.time() - start_time
        avg_confidence = np.mean(all_confidences) if all_confidences else 0.0
        
        return {
            'total_frames': total_frames,
            'processed_frames': processed_count,
            'duration': duration,
            'fps': processed_count / duration if duration > 0 else 0,
            'student_behavior_stats': dict(student_stats),
            'teacher_behavior_stats': dict(teacher_stats),
            'total_detections': len(all_confidences),
            'average_confidence': float(avg_confidence)
        }
    
    def get_realtime_stats(self) -> Dict[str, Any]:
        """获取实时统计信息（用于视频流）"""
        # 计算最近帧的行为占比
        student_counts = defaultdict(int)
        teacher_counts = defaultdict(int)
        
        for behavior in self.recent_student_behaviors:
            student_counts[behavior] += 1
        
        for behavior in self.recent_teacher_behaviors:
            teacher_counts[behavior] += 1
        
        total_student = sum(student_counts.values())
        total_teacher = sum(teacher_counts.values())
        
        student_ratios = {k: v/total_student*100 if total_student > 0 else 0 
                         for k, v in student_counts.items()}
        teacher_ratios = {k: v/total_teacher*100 if total_teacher > 0 else 0 
                         for k, v in teacher_counts.items()}
        
        return {
            'student_behavior_ratios': student_ratios,
            'teacher_behavior_ratios': teacher_ratios,
            'student_counts': dict(student_counts),
            'teacher_counts': dict(teacher_counts)
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.student_behavior_counts.clear()
        self.teacher_behavior_counts.clear()
        self.recent_student_behaviors.clear()
        self.recent_teacher_behaviors.clear()

