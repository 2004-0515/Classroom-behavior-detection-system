#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
遗留模型演示脚本
用于手动查看模型信息，不作为正式回归验收入口。
"""

from pathlib import Path
from utils.detector import BehaviorDetector
from config import Config


def test_scan_models():
    """测试扫描模型目录"""
    print("=" * 60)
    print("测试：扫描模型目录")
    print("=" * 60)
    
    models_info = BehaviorDetector.scan_models_directory(str(Config.MODEL_FOLDER))
    
    if not models_info:
        print("[FAIL] 未找到任何模型文件")
        print(f"   请将 .pt 模型文件放入 {Config.MODEL_FOLDER} 目录")
        return False
    
    print(f"\n[OK] 找到 {len(models_info)} 个模型文件：\n")
    
    for i, model in enumerate(models_info, 1):
        print(f"模型 {i}: {model['filename']}")
        print("-" * 40)
        
        if 'error' in model:
            print(f"  [FAIL] 加载失败: {model['error']}")
        else:
            print(f"  [INFO] 文件大小: {model['file_size_mb']} MB")
            print(f"  [INFO] 类别数量: {model['num_classes']}")
            print(f"  [INFO] 类别列表:")
            
            # 分行显示类别
            classes = model['classes']
            for j in range(0, len(classes), 5):
                batch = classes[j:j+5]
                print(f"      {', '.join(batch)}")
        
        print()
    
    return True


def test_model_loading():
    """测试加载模型并获取信息"""
    print("=" * 60)
    print("测试：加载模型并提取类别信息")
    print("=" * 60)
    
    # 检查模型文件是否存在
    student_exists = Path(Config.STUDENT_MODEL_PATH).exists()
    teacher_exists = Path(Config.TEACHER_MODEL_PATH).exists()
    
    if not student_exists and not teacher_exists:
        print("[FAIL] 未找到模型文件")
        print(f"   学生模型: {Config.STUDENT_MODEL_PATH}")
        print(f"   人头模型: {Config.TEACHER_MODEL_PATH}")
        return False
    
    print("\n创建检测器...\n")
    
    detector = BehaviorDetector(
        Config.STUDENT_MODEL_PATH,
        Config.TEACHER_MODEL_PATH
    )
    
    # 测试获取学生模型信息
    if detector.student_model:
        print("\n[INFO] 学生模型信息：")
        print("-" * 40)
        student_info = detector.get_model_info('student')
        
        if student_info.get('loaded'):
            print(f"[OK] 加载成功")
            print(f"[INFO] 路径: {student_info['path']}")
            print(f"[INFO] 类别数量: {student_info['num_classes']}")
            print(f"[INFO] 类别列表: {', '.join(student_info['classes'])}")
        else:
            print(f"[FAIL] 加载失败: {student_info.get('error')}")
    else:
        print("\n[WARN] 学生模型未加载")
    
    # 测试获取人头模型信息
    if detector.teacher_model:
        print("\n[INFO] 人头模型信息：")
        print("-" * 40)
        teacher_info = detector.get_model_info('teacher')
        
        if teacher_info.get('loaded'):
            print(f"[OK] 加载成功")
            print(f"[INFO] 路径: {teacher_info['path']}")
            print(f"[INFO] 类别数量: {teacher_info['num_classes']}")
            print(f"[INFO] 类别列表: {', '.join(teacher_info['classes'])}")
        else:
            print(f"[FAIL] 加载失败: {teacher_info.get('error')}")
    else:
        print("\n[WARN] 人头模型未加载")
    
    return True


def test_dynamic_loading():
    """测试动态加载模型"""
    print("\n" + "=" * 60)
    print("测试：动态加载不同的模型")
    print("=" * 60)
    
    # 获取所有可用模型
    models_info = BehaviorDetector.scan_models_directory(str(Config.MODEL_FOLDER))
    
    if len(models_info) < 1:
        print("[FAIL] 需要至少一个模型文件来测试")
        return False
    
    # 选择第一个有效的模型
    test_model = None
    for model in models_info:
        if 'error' not in model:
            test_model = model
            break
    
    if not test_model:
        print("[FAIL] 没有有效的模型文件")
        return False
    
    print(f"\n测试动态加载: {test_model['filename']}")
    print("-" * 40)
    
    # 创建一个空的检测器
    detector = BehaviorDetector(
        Config.STUDENT_MODEL_PATH,
        Config.TEACHER_MODEL_PATH
    )
    
    # 动态加载为学生模型
    model_path = str(Path(Config.MODEL_FOLDER) / test_model['filename'])
    success = detector.load_model('student', model_path)
    
    if success:
        print(f"[OK] 动态加载成功")
        print(f"[INFO] 自动识别的类别: {', '.join(detector.student_classes)}")
        return True
    else:
        print(f"[FAIL] 动态加载失败")
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  YOLOv8 模型信息自动识别测试")
    print("=" * 60)
    print()
    
    results = []
    
    # 测试1: 扫描模型
    try:
        result1 = test_scan_models()
        results.append(('扫描模型目录', result1))
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        results.append(('扫描模型目录', False))
    
    print("\n" + "=" * 60 + "\n")
    
    # 测试2: 加载模型
    try:
        result2 = test_model_loading()
        results.append(('加载模型', result2))
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        results.append(('加载模型', False))
    
    print("\n" + "=" * 60 + "\n")
    
    # 测试3: 动态加载
    try:
        result3 = test_dynamic_loading()
        results.append(('动态加载', result3))
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        results.append(('动态加载', False))
    
    # 打印测试摘要
    print("\n" + "=" * 60)
    print("测试摘要")
    print("=" * 60)
    
    for test_name, result in results:
        status = "[OK] 通过" if result else "[FAIL] 失败"
        print(f"{test_name}: {status}")
    
    total = len(results)
    passed = sum(1 for _, r in results if r)
    
    print(f"\n总计: {passed}/{total} 测试通过")
    print("=" * 60)
    
    if passed == total:
        print("\n[OK] 所有测试通过，模型自动识别功能正常工作。")
    else:
        print("\n[WARN] 部分测试失败，请检查模型文件。")
    
    print("\n提示:")
    print("  - 确保 models/ 目录中有 .pt 格式的模型文件")
    print("  - 模型文件必须是 YOLOv8 训练的")
    print("  - 如果所有测试都失败，请检查依赖包安装")
    print()


if __name__ == '__main__':
    main()

