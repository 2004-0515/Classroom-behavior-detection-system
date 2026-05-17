#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
遗留演示测试脚本
会写入本地数据库，不再作为正式回归验收入口。
请优先使用 scripts/verify_all.py。
"""

import os
import sys
from pathlib import Path


def prepare_yolo_runtime():
    """确保 Ultralytics 配置写入项目本地目录，而不是仓库根目录副产物。"""
    yolo_config_dir = Path(os.environ.get('YOLO_CONFIG_DIR') or Path(__file__).resolve().parent / 'data' / 'yolo_config')
    yolo_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(yolo_config_dir))


def print_header(text):
    """打印标题"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def check_python_version():
    """检查Python版本"""
    print_header("检查 Python 版本")
    version = sys.version_info
    print(f"Python 版本: {version.major}.{version.minor}.{version.micro}")
    
    if version.major >= 3 and version.minor >= 8:
        print("[OK] Python 版本符合要求 (3.8+)")
        return True
    else:
        print("[FAIL] Python 版本过低，需要 3.8 或更高版本")
        return False

def check_dependencies():
    """检查依赖包"""
    print_header("检查依赖包")
    prepare_yolo_runtime()
    
    required_packages = {
        'flask': 'Flask',
        'ultralytics': 'YOLOv8',
        'cv2': 'OpenCV',
        'numpy': 'NumPy',
        'PIL': 'Pillow'
    }
    
    all_installed = True
    
    for module_name, display_name in required_packages.items():
        try:
            __import__(module_name)
            print(f"[OK] {display_name} 已安装")
        except ImportError:
            print(f"[FAIL] {display_name} 未安装")
            all_installed = False
    
    return all_installed

def check_directories():
    """检查目录结构"""
    print_header("检查目录结构")
    
    required_dirs = [
        'models',
        'uploads',
        'outputs',
        'data',
        'templates',
        'static',
        'static/css',
        'static/app',
        'legacy/prototype',
        'utils'
    ]
    
    all_exist = True
    
    for dir_name in required_dirs:
        if Path(dir_name).exists():
            print(f"[OK] {dir_name}/ 存在")
        else:
            print(f"[FAIL] {dir_name}/ 不存在")
            all_exist = False
    
    return all_exist

def check_files():
    """检查关键文件"""
    print_header("检查关键文件")
    
    required_files = [
        'app.py',
        'config.py',
        'requirements.txt',
        'templates/app_shell.html',
        'static/css/app.css',
        'static/app/main.js',
        'legacy/prototype/index.html',
        'legacy/prototype/style.css',
        'legacy/prototype/main.js',
        'utils/detector.py',
        'utils/database.py',
        'utils/report_generator.py'
    ]
    
    all_exist = True
    
    for file_name in required_files:
        if Path(file_name).exists():
            print(f"[OK] {file_name} 存在")
        else:
            print(f"[FAIL] {file_name} 不存在")
            all_exist = False
    
    return all_exist

def check_models():
    """检查模型文件"""
    print_header("检查模型文件")
    
    model_files = sorted(Path('models').glob('*.pt'))
    if not model_files:
        print("[WARN] models/ 下未找到 .pt 模型文件（需要手动放置）")
        return False

    for model_file in model_files:
        size = model_file.stat().st_size / (1024*1024)
        print(f"[OK] {model_file.as_posix()} 存在 ({size:.1f} MB)")
    return True

def check_gpu():
    """检查GPU支持"""
    print_header("检查 GPU 支持")
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"[OK] GPU 可用: {gpu_name}")
            print(f"   CUDA 版本: {torch.version.cuda}")
            return True
        else:
            print("[WARN] GPU 不可用，将使用 CPU（速度较慢）")
            return False
    except ImportError:
        print("[WARN] 无法检查 GPU（torch 未安装）")
        return False

def test_database():
    """测试数据库"""
    print_header("测试数据库")
    
    try:
        from utils.database import Database
        db = Database()
        print("[OK] 数据库初始化成功")
        
        # 测试创建任务
        test_task_id = "test_task_123"
        db.create_task(test_task_id, "test", "test.jpg")
        print("[OK] 数据库写入测试成功")
        
        # 测试读取
        task_info = db.get_task_info(test_task_id)
        if task_info:
            print("[OK] 数据库读取测试成功")
        
        return True
    except Exception as e:
        print(f"[FAIL] 数据库测试失败: {e}")
        return False

def test_detector():
    """测试检测器（如果模型存在）"""
    print_header("测试检测器")
    
    try:
        from utils.detector import BehaviorDetector
        from config import Config
        
        detector = BehaviorDetector(
            Config.STUDENT_MODEL_PATH,
            Config.TEACHER_MODEL_PATH
        )
        
        if detector.student_model or detector.teacher_model:
            print("[OK] 检测器初始化成功")
            return True
        else:
            print("[WARN] 检测器初始化成功，但未加载模型")
            return False
    except Exception as e:
        print(f"[FAIL] 检测器测试失败: {e}")
        return False

def print_summary(results):
    """打印测试摘要"""
    print_header("测试摘要")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n总测试项: {total}")
    print(f"通过: {passed}")
    print(f"失败: {total - passed}")
    print(f"通过率: {passed/total*100:.1f}%\n")
    
    if passed == total:
        print("[OK] 所有测试通过，系统可以正常运行。")
    elif passed >= total * 0.7:
        print("[WARN] 大部分测试通过，系统基本可用。")
        print("   建议解决失败的测试项以获得最佳体验。")
    else:
        print("[FAIL] 多个测试失败，请先解决这些问题。")
        print("   参考 README.md 和 docs/ 目录进行修复。")

def main():
    """主函数"""
    print("\n" + "="*60)
    print("  课堂行为检测系统 - 系统测试")
    print("="*60)
    
    results = {
        'Python版本': check_python_version(),
        '依赖包': check_dependencies(),
        '目录结构': check_directories(),
        '关键文件': check_files(),
        '模型文件': check_models(),
        'GPU支持': check_gpu(),
        '数据库': test_database(),
        '检测器': test_detector()
    }
    
    print_summary(results)
    
    print("\n" + "="*60)
    print("提示:")
    print("  - 如果模型文件不存在，请将训练好的模型放入 models/ 目录")
    print("  - 如果依赖包未安装，请运行: pip install -r requirements.txt")
    print("  - 详细说明请查看 README.md 和 docs/ 目录")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()

