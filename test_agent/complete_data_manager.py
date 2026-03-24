"""
完整数据管理模块
记录所有测试数据，包括完整的对话记录、评分详情、分析结果等
"""

import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
import uuid

# 文件路径
TEST_RESULTS_FILE = 'data/test_results.json'

# 线程锁
data_lock = threading.Lock()

class CompleteDataManager:
    """完整数据管理器 - 简化版本，与evaluation.py返回结构一致"""
    
    def __init__(self):
        self.data = self.load_test_data()
    
    def load_test_data(self) -> Dict:
        """加载测试数据"""
        try:
            if os.path.exists(TEST_RESULTS_FILE):
                with open(TEST_RESULTS_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:  # 文件为空
                        print(f"[WARN] {TEST_RESULTS_FILE} 文件为空，重新初始化")
                        return self._create_empty_data()
                    return json.loads(content)
            return self._create_empty_data()
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON解析失败: {e}")
            try:
                # 备份损坏的文件
                backup_file = f"{TEST_RESULTS_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                import shutil
                shutil.move(TEST_RESULTS_FILE, backup_file)
                print(f"[INFO] 已备份损坏文件到: {backup_file}")
            except Exception as backup_error:
                print(f"[WARN] 备份失败: {backup_error}")
            return self._create_empty_data()
        except Exception as e:
            print(f"[ERROR] 加载测试数据失败: {e}")
            return self._create_empty_data()
    
    def _create_empty_data(self) -> Dict:
        """创建空的数据结构"""
        return {
            "version": "2.0",
            "description": "AI儿童测试结果存储 - 简化结构",
            "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "last_updated": "",
            "total_tests": 0,
            "tests": []
        }
    
    def save_complete_data(self, calculate_stats=True):
        """保存测试数据"""
        try:
            print(f"[DEBUG] 准备保存JSON文件到: {TEST_RESULTS_FILE}")
            
            # 验证数据结构
            if not isinstance(self.data, dict):
                raise ValueError(f"数据必须是字典类型，当前类型: {type(self.data)}")
            
            if "tests" not in self.data:
                raise ValueError("数据缺少 'tests' 字段")
            
            # 确保文件目录存在
            os.makedirs(os.path.dirname(TEST_RESULTS_FILE), exist_ok=True)
            
            with data_lock:
                print(f"[DEBUG] 已获取data_lock")
                self.data["last_updated"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.data["total_tests"] = len(self.data["tests"])
                print(f"[DEBUG] 数据更新完成，total_tests={self.data['total_tests']}")
                
                print(f"[DEBUG] 开始写入文件...")
                
                # 尝试序列化数据以检查是否有不可序列化的对象
                try:
                    json_str = json.dumps(self.data, ensure_ascii=False, indent=2, default=str)
                    print(f"[DEBUG] 数据序列化成功，大小: {len(json_str)} 字节")
                except (TypeError, ValueError) as serialize_error:
                    print(f"[ERROR] 数据序列化失败: {serialize_error}")
                    print(f"[ERROR] 问题数据内容: {self.data}")
                    raise
                
                # 写入文件
                with open(TEST_RESULTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)
                    
                print(f"[DEBUG] 文件写入完成")
            print("[SUCCESS] 测试数据保存成功")
        except json.JSONEncodeError as e:
            print(f"[ERROR] JSON编码失败: {e}")
            print(f"[ERROR] 无法序列化的数据类型: {type(e.obj)}")
            import traceback
            traceback.print_exc()
        except PermissionError as e:
            print(f"[ERROR] 文件权限错误: {e}")
            print(f"[ERROR] 无法写入文件: {TEST_RESULTS_FILE}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            print(f"[ERROR] 保存测试数据失败: {e}")
            print(f"[ERROR] 错误类型: {type(e)}")
            import traceback
            traceback.print_exc()
    
    def add_normal_test(self, test_data: Dict) -> str:
        """添加正常测试数据"""
        try:
            # 生成唯一测试ID
            test_id = self._generate_test_id("normal", test_data)
            
            # 构建完整的测试记录
            complete_test = {
                "test_id": test_id,
                "test_type": "normal",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "test_date": datetime.now().strftime('%Y-%m-%d'),
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                
                # 孩子信息
                "child": {
                    "name": test_data.get("child", {}).get("name", ""),
                    "age": test_data.get("child", {}).get("age", ""),
                    "type": test_data.get("child", {}).get("type", ""),
                    "traits": test_data.get("child", {}).get("traits", ""),
                    "opening": test_data.get("child", {}).get("opening", ""),
                    "gender": test_data.get("child", {}).get("gender", ""),
                    "personality": test_data.get("child", {}).get("personality", "")
                },
                
                # 对话记录
                "conversations": test_data.get("conversations", []),
                "rounds": len(test_data.get("conversations", [])),
                
                # 评分数据
                "scores": self._format_scores(test_data.get("scores", {})),
                
                # 评估结果
                "evaluation": {
                    "reason": test_data.get("reason", ""),
                    "lessons": test_data.get("lessons", ""),
                    "character_review": test_data.get("character_review", ""),
                    "experience_score": test_data.get("experience_score", 50),
                    "overall_quality": test_data.get("overall_quality", ""),
                    "improvement_suggestions": test_data.get("improvement_suggestions", "")
                },
                
                # 统计信息
                "statistics": self._calculate_test_statistics(test_data),
                
                # 使用的评分标准
                "criteria_used": test_data.get("criteria_used", []),
                
                # 原始数据（用于调试和回溯）
                "raw_data": test_data
            }
            
            # 添加到数据中
            self.data["tests"].append(complete_test)
            self.save_complete_data()
            
            print(f"[SUCCESS] 正常测试数据已添加: {test_id}")
            return test_id
        except Exception as e:
            print(f"[ERROR] 添加正常测试数据失败: {e}")
            return ""
    
    def add_continuous_test(self, test_data: Dict) -> str:
        """添加连续测试数据"""
        try:
            # 生成唯一测试ID
            test_id = self._generate_test_id("continuous", test_data)
            
            # 构建完整的测试记录
            complete_test = {
                "test_id": test_id,
                "test_type": "continuous",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "test_date": datetime.now().strftime('%Y-%m-%d'),
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                
                # 孩子信息
                "child": {
                    "name": test_data.get("child", {}).get("name", ""),
                    "age": test_data.get("child", {}).get("age", ""),
                    "type": test_data.get("child", {}).get("type", ""),
                    "traits": test_data.get("child", {}).get("traits", ""),
                    "opening": test_data.get("child", {}).get("opening", ""),
                    "gender": test_data.get("child", {}).get("gender", ""),
                    "personality": test_data.get("child", {}).get("personality", "")
                },
                
                # 对话记录
                "conversations": test_data.get("conversations", []),
                "rounds": len(test_data.get("conversations", [])),
                
                # 连续测试特有数据
                "continuous_metrics": test_data.get("continuous_metrics", {}),
                "stop_reason": test_data.get("stop_reason", ""),
                "max_rounds": test_data.get("max_rounds", 0),
                "thresholds": test_data.get("thresholds", {}),
                
                # 评分数据
                "scores": self._format_scores(test_data.get("scores", {})),
                
                # 评估结果
                "evaluation": {
                    "reason": test_data.get("reason", ""),
                    "lessons": test_data.get("lessons", ""),
                    "character_review": test_data.get("character_review", ""),
                    "experience_score": test_data.get("experience_score", 50),
                    "overall_quality": test_data.get("overall_quality", ""),
                    "improvement_suggestions": test_data.get("improvement_suggestions", "")
                },
                
                # 统计信息
                "statistics": self._calculate_test_statistics(test_data),
                
                # 使用的评分标准
                "criteria_used": test_data.get("criteria_used", []),
                
                # 原始数据（用于调试和回溯）
                "raw_data": test_data
            }
            
            # 添加到数据中
            self.data["tests"].append(complete_test)
            self.save_complete_data()
            
            print(f"[SUCCESS] 连续测试数据已添加: {test_id}")
            return test_id
        except Exception as e:
            print(f"[ERROR] 添加连续测试数据失败: {e}")
            return ""
    
    def add_multi_session_test(self, test_data: Dict) -> str:
        """添加多Session测试数据"""
        try:
            # 生成唯一测试ID
            test_id = self._generate_test_id("multi_session", test_data)
            
            # 构建完整的测试记录
            complete_test = {
                "test_id": test_id,
                "test_type": "multi_session",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "test_date": datetime.now().strftime('%Y-%m-%d'),
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                
                # 孩子信息
                "child": {
                    "name": test_data.get("child", {}).get("name", ""),
                    "age": test_data.get("child", {}).get("age", ""),
                    "type": test_data.get("child", {}).get("type", ""),
                    "traits": test_data.get("child", {}).get("traits", ""),
                    "opening": test_data.get("child", {}).get("opening", ""),
                    "gender": test_data.get("child", {}).get("gender", ""),
                    "personality": test_data.get("child", {}).get("personality", ""),
                    "user_id": test_data.get("child", {}).get("user_id", "")
                },
                
                # 多Session特有数据
                "multi_session_info": {
                    "session_count": test_data.get("session_count", 0),
                    "total_rounds": test_data.get("total_rounds", 0),
                    "end_reason": test_data.get("end_reason", "normal"),
                    "max_rounds_limit": test_data.get("max_rounds_limit", 0),
                    "sessions": self._organize_sessions(test_data.get("conversations", []))
                },
                
                # 对话记录（所有session合并）
                "conversations": test_data.get("conversations", []),
                "rounds": len(test_data.get("conversations", [])),
                
                # 评分数据
                "scores": self._format_scores(test_data.get("scores", {})),
                
                # 评估结果
                "evaluation": {
                    "reason": test_data.get("reason", ""),
                    "lessons": test_data.get("lessons", ""),
                    "character_review": test_data.get("character_review", ""),
                    "experience_score": test_data.get("experience_score", 50),
                    "overall_quality": test_data.get("overall_quality", ""),
                    "improvement_suggestions": test_data.get("improvement_suggestions", "")
                },
                
                # 统计信息
                "statistics": self._calculate_multi_session_statistics(test_data),
                
                # 使用的评分标准
                "criteria_used": test_data.get("criteria_used", []),
                
                # 原始数据（用于调试和回溯）
                "raw_data": test_data
            }
            
            # 添加到数据中
            self.data["tests"].append(complete_test)
            self.save_complete_data()
            
            print(f"[SUCCESS] 多Session测试数据已添加: {test_id}")
            return test_id
        except Exception as e:
            print(f"[ERROR] 添加多Session测试数据失败: {e}")
            return ""
    
    def add_or_update_round_result(self, test_data: Dict, round_data: Dict) -> str:
        """添加或更新Round评测结果（实时保存） - 增强版本，保存更详细的信息
        
        Args:
            test_data: 基础测试信息（child, test_type等）
            round_data: 当前round的评测结果（直接保存evaluation.py的返回结构）
        
        Returns:
            test_id
        """
        with data_lock:
            try:
                print(f"[DEBUG] 开始保存Round数据...")
                
                # 生成或获取test_id
                test_id = test_data.get('test_id')
                
                if not test_id:
                    # 第一个round，创建新测试记录
                    child_name = test_data.get('child', {}).get('name', 'Unknown')
                    short_uuid = str(uuid.uuid4())[:8]
                    test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{child_name}_{short_uuid}"
                    
                    # 创建新的测试记录 - 增强版本，包含更多元信息
                    complete_test = {
                        "test_id": test_id,
                        "test_type": "multi_session",
                        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "child": test_data.get('child', {}),
                        "test_config": {
                            "max_rounds_limit": test_data.get('max_rounds_limit', 0),
                            "criteria_used": [],
                            "api_keys_used": {
                                "dify": bool(test_data.get('dify_api_key')),
                                "gemini": bool(test_data.get('gemini_api_key'))
                            }
                        },
                        "rounds": [],  # 存储每个round的详细评测结果
                        "summary": {
                            "total_rounds": 0,
                            "total_sessions": 0,
                            "total_conversations": 0,
                            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                    }
                    
                    self.data["tests"].append(complete_test)
                    print(f"[SUCCESS] 创建新的实时测试记录: {test_id}")
                
                # 查找现有测试记录
                complete_test = None
                for test in self.data["tests"]:
                    if test.get("test_id") == test_id:
                        complete_test = test
                        break
                
                if not complete_test:
                    print(f"[ERROR] 未找到测试记录: {test_id}")
                    return ""
                
                # 🔥 增强round数据，添加更多详细信息
                print(f"[DEBUG] 开始准备round数据，Round {round_data.get('round_number', 1)}")
                print(f"[DEBUG] 原始round数据包含: {list(round_data.keys())}")
                
                # 计算对话统计数据
                conversations = round_data.get('conversations', [])
                conversation_stats = {
                    "total_conversations": len(conversations),
                    "total_chars_child": sum(len(c.get('user_message', '')) for c in conversations),
                    "total_chars_ai": sum(len(c.get('ai_response', '')) for c in conversations),
                    "avg_chars_child": 0,
                    "avg_chars_ai": 0,
                    "conversation_length_distribution": [len(c.get('user_message', '')) for c in conversations],
                    "ai_response_length_distribution": [len(c.get('ai_response', '')) for c in conversations]
                }
                
                if len(conversations) > 0:
                    conversation_stats["avg_chars_child"] = round(conversation_stats["total_chars_child"] / len(conversations), 2)
                    conversation_stats["avg_chars_ai"] = round(conversation_stats["total_chars_ai"] / len(conversations), 2)
                
                # 🔥 详细的评分信息
                scores = round_data.get('scores', {})
                detailed_scores = {
                    "individual_scores": {},
                    "dual_scores": {},
                    "criteria_count": 0,
                    "score_statistics": {
                        "child_scores": [],
                        "expert_scores": [],
                        "child_avg": 0,
                        "expert_avg": 0,
                        "score_difference_avg": 0
                    }
                }
                
                # 提取所有评分详情
                child_scores = []
                expert_scores = []
                
                for criterion_name, score_value in scores.items():
                    if isinstance(score_value, dict) and 'child_score' in score_value and 'expert_score' in score_value:
                        detailed_scores["dual_scores"][criterion_name] = {
                            "child_score": score_value.get('child_score', 0),
                            "expert_score": score_value.get('expert_score', 0),
                            "child_detail": score_value.get('child_detail', ''),
                            "expert_detail": score_value.get('expert_detail', ''),
                            "score_difference": abs(score_value.get('child_score', 0) - score_value.get('expert_score', 0)),
                            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        child_scores.append(score_value.get('child_score', 0))
                        expert_scores.append(score_value.get('expert_score', 0))
                    else:
                        detailed_scores["individual_scores"][criterion_name] = score_value
                
                # 计算评分统计
                if child_scores:
                    detailed_scores["score_statistics"]["child_scores"] = child_scores
                    detailed_scores["score_statistics"]["expert_scores"] = expert_scores
                    detailed_scores["score_statistics"]["child_avg"] = round(sum(child_scores) / len(child_scores), 2)
                    detailed_scores["score_statistics"]["expert_avg"] = round(sum(expert_scores) / len(expert_scores), 2)
                    detailed_scores["score_statistics"]["score_difference_avg"] = round(
                        sum(abs(c - e) for c, e in zip(child_scores, expert_scores)) / len(child_scores), 2
                    )
                
                detailed_scores["criteria_count"] = len(detailed_scores["dual_scores"]) + len(detailed_scores["individual_scores"])
                
                # 🔥 构建增强的round数据
                enhanced_round_data = {
                    "round_number": round_data.get('round_number', 1),
                    "session_count": round_data.get('session_count', 0),
                    "timestamp": round_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    "saved_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    
                    # 对话记录（完整保留）
                    "conversations": conversations,
                    
                    # 详细的对话统计
                    "conversation_statistics": conversation_stats,
                    
                    # 详细的评分信息
                    "scores": detailed_scores,
                    
                    # 原始评分数据（保持兼容性）
                    "scores_raw": scores,
                    "score_details": round_data.get('score_details', {}),
                    
                    # 评测分析结果
                    "evaluation": {
                        "reason": round_data.get('reason', ''),
                        "lessons": round_data.get('lessons', ''),
                        "character_review": round_data.get('character_review', ''),
                        "experience_score": round_data.get('experience_score', 50),
                        "analysis_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    },
                    
                    # 元数据
                    "metadata": {
                        "round_duration_seconds": 0,  # 可以在前端计算后传入
                        "evaluation_completed": bool(scores),
                        "has_conversations": len(conversations) > 0,
                        "data_completeness": {
                            "has_scores": bool(scores),
                            "has_conversations": len(conversations) > 0,
                            "has_evaluation": bool(round_data.get('reason') or round_data.get('lessons')),
                            "has_experience_score": round_data.get('experience_score', 0) > 0
                        }
                    }
                }
                
                # 确保有rounds数组
                if "rounds" not in complete_test:
                    complete_test["rounds"] = []
                
                complete_test["rounds"].append(enhanced_round_data)
                
                # 🔥 更新测试摘要信息
                if "summary" not in complete_test:
                    complete_test["summary"] = {}
                
                complete_test["summary"].update({
                    "total_rounds": len(complete_test["rounds"]),
                    "total_sessions": sum(r.get('session_count', 0) for r in complete_test["rounds"]),
                    "total_conversations": sum(len(r.get('conversations', [])) for r in complete_test["rounds"]),
                    "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "latest_round_number": enhanced_round_data["round_number"],
                    "latest_session_count": enhanced_round_data["session_count"]
                })
                
                print(f"[DEBUG] 增强round数据已添加，共{len(complete_test['rounds'])}个rounds")
                print(f"[DEBUG] 当前round详细信息:")
                print(f"  - Round编号: {enhanced_round_data['round_number']}")
                print(f"  - Session数: {enhanced_round_data['session_count']}")
                print(f"  - 对话数: {len(conversations)}")
                print(f"  - 评分标准数: {detailed_scores['criteria_count']}")
                print(f"  - 平均孩子评分: {detailed_scores['score_statistics']['child_avg']}")
                print(f"  - 平均专家评分: {detailed_scores['score_statistics']['expert_avg']}")
                
                # 保存文件
                print(f"[DEBUG] 准备开始保存JSON文件...")
                start_time = datetime.now()
                
                self.save_complete_data(calculate_stats=False)
                save_duration = (datetime.now() - start_time).total_seconds()
                
                print(f"[SUCCESS] Round {enhanced_round_data['round_number']} 详细数据已保存 (耗时: {save_duration:.2f}秒)")
                print(f"[DEBUG] ✅ 保存完成，返回test_id: {test_id}")
                
                return test_id
                
            except Exception as e:
                print(f"[ERROR] 保存Round数据失败: {e}")
                import traceback
                traceback.print_exc()
                return ""
    
    def update_test(self, test_id: str, updates: Dict) -> bool:
        """更新测试数据"""
        try:
            for i, test in enumerate(self.data["tests"]):
                if test["test_id"] == test_id:
                    self.data["tests"][i].update(updates)
                    self.data["tests"][i]["updated_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.save_complete_data()
                    print(f"[SUCCESS] 测试数据已更新: {test_id}")
                    return True
            return False
        except Exception as e:
            print(f"[ERROR] 更新测试数据失败: {e}")
            return False
    
    def get_test(self, test_id: str) -> Optional[Dict]:
        """获取指定测试数据"""
        for test in self.data["tests"]:
            if test["test_id"] == test_id:
                return test
        return None
    
    def get_tests_by_type(self, test_type: str) -> List[Dict]:
        """根据测试类型获取测试数据"""
        return [test for test in self.data["tests"] if test.get("test_type") == test_type]
    
    def get_tests_by_criteria(self, criteria: str) -> List[Dict]:
        """根据评分标准获取测试数据"""
        return [test for test in self.data["tests"] if criteria in test.get("criteria_used", [])]
    
    def get_annotation_data(self) -> List[Dict]:
        """获取标注数据"""
        # 重新加载最新数据
        self.data = self.load_complete_data()
        annotations = []
        
        for test in self.data["tests"]:
            if "scores" not in test or not test["scores"]:
                continue
            
            # 处理双重评分格式
            dual_scores = test["scores"].get("dual_scores", {})
            for criterion_id, score_data in dual_scores.items():
                if isinstance(score_data, dict) and "child_score" in score_data and "expert_score" in score_data:
                    # 获取标注信息
                    annotation_info = score_data.get("annotation", {})
                    
                    annotation = {
                        "id": f"{test['test_id']}_{criterion_id}",
                        "test_id": test["test_id"],
                        "test_type": test.get("test_type", "normal"),
                        "timestamp": test.get("timestamp", ""),
                        "criterion_id": criterion_id,
                        "criterion_name": self._get_criterion_name(criterion_id),
                        "criterion_description": self._get_criterion_description(criterion_id),
                        "child_score": score_data.get("child_score", 0),
                        "expert_score": score_data.get("expert_score", 0),
                        "child_analysis": score_data.get("child_detail", ""),
                        "expert_analysis": score_data.get("expert_detail", ""),
                        "conversation_history": test.get("conversations", []),
                        "agreement": self._calculate_agreement(score_data.get("child_score", 0), score_data.get("expert_score", 0)),
                        "expert_accuracy": annotation_info.get("expert_accuracy"),
                        "expert_quality": annotation_info.get("expert_quality"),
                        "suggested_score": annotation_info.get("suggested_score"),
                        "feedback": annotation_info.get("feedback", ""),
                        "annotated": annotation_info.get("annotated", False),
                        "annotated_at": annotation_info.get("annotated_at")
                    }
                    annotations.append(annotation)
        
        return annotations
    
    def add_annotation(self, annotation_id: str, annotation_data: Dict):
        """添加标注数据"""
        try:
            # 解析annotation_id获取test_id和criterion_id
            # 格式: test_id_criterion_id，需要找到最后一个下划线后的criterion_id
            last_underscore = annotation_id.rfind('_')
            if last_underscore == -1:
                print(f"[ERROR] 无效的标注ID格式: {annotation_id}")
                return False
            
            test_id = annotation_id[:last_underscore]
            criterion_id = annotation_id[last_underscore + 1:]
            
            # 在测试数据中查找并更新标注信息
            for test in self.data["tests"]:
                if test["test_id"] == test_id:
                    # 在scores中查找对应的criterion
                    if "scores" in test and "dual_scores" in test["scores"]:
                        dual_scores = test["scores"]["dual_scores"]
                        if criterion_id in dual_scores:
                            # 添加标注信息到score_data
                            if "annotation" not in dual_scores[criterion_id]:
                                dual_scores[criterion_id]["annotation"] = {}
                            
                            dual_scores[criterion_id]["annotation"].update(annotation_data)
                            dual_scores[criterion_id]["annotation"]["annotated"] = True
                            dual_scores[criterion_id]["annotation"]["annotated_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            # 保存更新后的数据
                            self.save_complete_data()
                            print(f"[SUCCESS] 标注数据已保存: {annotation_id}")
                            return True
            
            print(f"[ERROR] 未找到对应的测试数据: {annotation_id}")
            return False
        except Exception as e:
            print(f"[ERROR] 添加标注数据失败: {e}")
            return False
    
    def _generate_test_id(self, test_type: str, test_data: Dict) -> str:
        """生成测试ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        child_name = test_data.get("child", {}).get("name", "未知")
        unique_id = str(uuid.uuid4())[:8]
        return f"{test_type}_{timestamp}_{child_name}_{unique_id}"
    
    def _format_scores(self, scores: Dict) -> Dict:
        """格式化评分数据"""
        if not scores:
            return {
                "individual": {},
                "dual_scores": {},
                "score_details": {},
                "summary": {
                    "average": 0,
                    "max": 0,
                    "min": 0,
                    "std_dev": 0,
                    "child_average": 0,
                    "expert_average": 0
                },
                "criteria_used": []
            }
        
        # 分离不同类型的评分
        individual_scores = {}
        dual_scores = {}
        score_details = {}
        
        for key, value in scores.items():
            if key in ["average", "max", "min", "std_dev", "child_average", "expert_average", "criteria_used", "score_details"]:
                if key == "score_details":
                    score_details = value
                continue
            elif isinstance(value, dict) and "child_score" in value and "expert_score" in value:
                dual_scores[key] = value
            else:
                individual_scores[key] = value
        
        return {
            "individual": individual_scores,
            "dual_scores": dual_scores,
            "score_details": score_details,
            "summary": {
                "average": scores.get("average", 0),
                "max": scores.get("max", 0),
                "min": scores.get("min", 0),
                "std_dev": scores.get("std_dev", 0),
                "child_average": scores.get("child_average", 0),
                "expert_average": scores.get("expert_average", 0)
            },
            "criteria_used": scores.get("criteria_used", [])
        }
    
    def _calculate_test_statistics(self, test_data: Dict) -> Dict:
        """计算测试统计信息"""
        conversations = test_data.get("conversations", [])
        
        # 基础统计
        total_chars_child = sum(len(conv.get("user_message", "")) for conv in conversations)
        total_chars_ai = sum(len(conv.get("ai_response", "")) for conv in conversations)
        total_chars_child_response = sum(len(conv.get("child_response", "")) for conv in conversations)
        
        # 计算平均值
        rounds = len(conversations)
        avg_chars_child = total_chars_child / rounds if rounds > 0 else 0
        avg_chars_ai = total_chars_ai / rounds if rounds > 0 else 0
        avg_chars_child_response = total_chars_child_response / rounds if rounds > 0 else 0
        
        # 对话质量指标
        quality_indicators = {
            "avg_response_length": avg_chars_child,
            "avg_ai_length": avg_chars_ai,
            "avg_child_response_length": avg_chars_child_response,
            "total_interaction_chars": total_chars_child + total_chars_ai + total_chars_child_response,
            "conversation_flow": self._analyze_conversation_flow(conversations),
            "engagement_level": self._calculate_engagement_level(conversations)
        }
        
        return {
            "total_chars_child": total_chars_child,
            "total_chars_ai": total_chars_ai,
            "total_chars_child_response": total_chars_child_response,
            "avg_chars_child": avg_chars_child,
            "avg_chars_ai": avg_chars_ai,
            "avg_chars_child_response": avg_chars_child_response,
            "quality_indicators": quality_indicators
        }
    
    def _analyze_conversation_flow(self, conversations: List[Dict]) -> Dict:
        """分析对话流程"""
        if not conversations:
            return {"flow_score": 0, "consistency": 0, "progression": 0}
        
        # 分析对话长度变化
        child_lengths = [len(conv.get("user_message", "")) for conv in conversations]
        ai_lengths = [len(conv.get("ai_response", "")) for conv in conversations]
        
        # 计算一致性（长度变化的标准差）
        child_consistency = 1 - (sum((x - sum(child_lengths)/len(child_lengths))**2 for x in child_lengths) / len(child_lengths))**0.5 / 100
        ai_consistency = 1 - (sum((x - sum(ai_lengths)/len(ai_lengths))**2 for x in ai_lengths) / len(ai_lengths))**0.5 / 100
        
        # 计算进展性（对话是否越来越深入）
        progression = 1 if len(conversations) > 1 and child_lengths[-1] > child_lengths[0] else 0.5
        
        return {
            "flow_score": (child_consistency + ai_consistency + progression) / 3,
            "consistency": (child_consistency + ai_consistency) / 2,
            "progression": progression
        }
    
    def _calculate_engagement_level(self, conversations: List[Dict]) -> float:
        """计算参与度"""
        if not conversations:
            return 0.0
        
        # 基于对话长度和内容分析参与度
        total_chars = sum(len(conv.get("user_message", "")) for conv in conversations)
        avg_length = total_chars / len(conversations)
        
        # 简单的参与度计算（可以根据需要优化）
        engagement = min(avg_length / 50, 1.0)  # 假设50字符为高参与度
        return round(engagement, 2)
    
    def _organize_sessions(self, conversations: List[Dict]) -> List[Dict]:
        """组织对话数据为session结构"""
        sessions = []
        current_session = []
        session_id = 1
        
        for conv in conversations:
            # 如果对话包含session信息，使用它
            if "session" in conv:
                if conv["session"] != session_id:
                    # 新session开始
                    if current_session:
                        sessions.append({
                            "session_id": session_id,
                            "rounds": len(current_session),
                            "conversations": current_session.copy()
                        })
                    current_session = []
                    session_id = conv["session"]
            
            current_session.append(conv)
        
        # 添加最后一个session
        if current_session:
            sessions.append({
                "session_id": session_id,
                "rounds": len(current_session),
                "conversations": current_session
            })
        
        return sessions
    
    def _calculate_multi_session_statistics(self, test_data: Dict) -> Dict:
        """计算多Session测试统计信息"""
        conversations = test_data.get("conversations", [])
        session_count = test_data.get("session_count", 0)
        
        # 基础统计
        base_stats = self._calculate_test_statistics(test_data)
        
        # 多Session特有统计
        sessions = self._organize_sessions(conversations)
        
        # Session统计
        session_stats = {
            "avg_rounds_per_session": round(len(conversations) / session_count, 2) if session_count > 0 else 0,
            "max_session_rounds": max(len(session["conversations"]) for session in sessions) if sessions else 0,
            "min_session_rounds": min(len(session["conversations"]) for session in sessions) if sessions else 0,
            "session_distribution": [len(session["conversations"]) for session in sessions]
        }
        
        # 跨Session一致性分析
        consistency_analysis = self._analyze_cross_session_consistency(sessions)
        
        return {
            **base_stats,
            "session_statistics": session_stats,
            "consistency_analysis": consistency_analysis
        }
    
    def _analyze_cross_session_consistency(self, sessions: List[Dict]) -> Dict:
        """分析跨Session一致性"""
        if len(sessions) < 2:
            return {"consistency_score": 1.0, "memory_retention": 1.0, "character_consistency": 1.0}
        
        # 分析角色一致性（基于对话风格）
        character_scores = []
        memory_scores = []
        
        for i in range(1, len(sessions)):
            prev_session = sessions[i-1]["conversations"]
            curr_session = sessions[i]["conversations"]
            
            # 角色一致性：比较对话风格
            prev_avg_length = sum(len(conv.get("user_message", "")) for conv in prev_session) / len(prev_session)
            curr_avg_length = sum(len(conv.get("user_message", "")) for conv in curr_session) / len(curr_session)
            
            length_consistency = 1 - abs(prev_avg_length - curr_avg_length) / max(prev_avg_length, curr_avg_length, 1)
            character_scores.append(length_consistency)
            
            # 记忆保持：检查是否提及之前的内容
            memory_retention = self._calculate_memory_retention(prev_session, curr_session)
            memory_scores.append(memory_retention)
        
        return {
            "consistency_score": round(sum(character_scores) / len(character_scores), 2) if character_scores else 1.0,
            "memory_retention": round(sum(memory_scores) / len(memory_scores), 2) if memory_scores else 1.0,
            "character_consistency": round(sum(character_scores) / len(character_scores), 2) if character_scores else 1.0
        }
    
    def _calculate_memory_retention(self, prev_session: List[Dict], curr_session: List[Dict]) -> float:
        """计算记忆保持度"""
        if not prev_session or not curr_session:
            return 0.0
        
        # 提取关键词
        prev_keywords = set()
        curr_keywords = set()
        
        for conv in prev_session:
            message = conv.get("user_message", "").lower()
            # 简单的关键词提取（可以根据需要优化）
            keywords = [word for word in message.split() if len(word) > 2]
            prev_keywords.update(keywords)
        
        for conv in curr_session:
            message = conv.get("user_message", "").lower()
            keywords = [word for word in message.split() if len(word) > 2]
            curr_keywords.update(keywords)
        
        # 计算重叠度
        if not prev_keywords:
            return 0.0
        
        overlap = len(prev_keywords.intersection(curr_keywords))
        retention = overlap / len(prev_keywords)
        
        return min(retention, 1.0)
    
    def _calculate_agreement(self, child_score: int, expert_score: int) -> float:
        """计算孩子和专家评分的一致性"""
        if child_score == 0 and expert_score == 0:
            return 100.0
        
        max_score = max(child_score, expert_score)
        min_score = min(child_score, expert_score)
        
        if max_score == 0:
            return 100.0
        
        agreement = (1 - (max_score - min_score) / max_score) * 100
        return round(agreement, 1)
    
    def _get_criterion_name(self, criterion_id: str) -> str:
        """获取评分标准名称"""
        try:
            with open('config/preset_criteria.json', 'r', encoding='utf-8') as f:
                criteria = json.load(f)
            
            if '.' in criterion_id:
                main_key, sub_key = criterion_id.split('.', 1)
                if main_key in criteria and 'sub_criteria' in criteria[main_key]:
                    sub_criteria = criteria[main_key]['sub_criteria']
                    if sub_key in sub_criteria:
                        return sub_criteria[sub_key].get('name', sub_key)
            return criterion_id
        except:
            return criterion_id
    
    def _get_criterion_description(self, criterion_id: str) -> str:
        """获取评分标准描述"""
        try:
            with open('config/preset_criteria.json', 'r', encoding='utf-8') as f:
                criteria = json.load(f)
            
            if '.' in criterion_id:
                main_key, sub_key = criterion_id.split('.', 1)
                if main_key in criteria and 'sub_criteria' in criteria[main_key]:
                    sub_criteria = criteria[main_key]['sub_criteria']
                    if sub_key in sub_criteria:
                        return sub_criteria[sub_key].get('description', '')
            return ''
        except:
            return ''
    
    def _calculate_statistics(self):
        """计算全局统计信息"""
        tests = self.data["tests"]
        
        # 基础统计
        self.data["statistics"]["total_conversations"] = sum(len(test.get("conversations", [])) for test in tests)
        self.data["statistics"]["total_rounds"] = sum(test.get("rounds", 0) for test in tests)
        
        if tests:
            self.data["statistics"]["avg_rounds_per_test"] = round(self.data["statistics"]["total_rounds"] / len(tests), 2)
        
        # 测试类型统计
        self.data["statistics"]["test_types"] = {"normal": 0, "continuous": 0, "multi_session": 0}
        self.data["statistics"]["child_types"] = {}
        self.data["statistics"]["criteria_usage"] = {}
        
        for test in tests:
            test_type = test.get("test_type", "normal")
            self.data["statistics"]["test_types"][test_type] = self.data["statistics"]["test_types"].get(test_type, 0) + 1
            
            # 孩子类型统计
            child_type = test.get("child", {}).get("type", "未知")
            self.data["statistics"]["child_types"][child_type] = self.data["statistics"]["child_types"].get(child_type, 0) + 1
            
            # 评分标准使用统计
            criteria_used = test.get("criteria_used", [])
            for criterion in criteria_used:
                self.data["statistics"]["criteria_usage"][criterion] = self.data["statistics"]["criteria_usage"].get(criterion, 0) + 1
        
        # 标注统计
        self.data["statistics"]["total_annotations"] = len(self.annotations)
        if self.annotations:
            agreements = [a.get("agreement", 0) for a in self.annotations if a.get("agreement")]
            self.data["statistics"]["avg_agreement"] = round(sum(agreements) / len(agreements), 2) if agreements else 0

# 全局实例
complete_data_manager = CompleteDataManager()

# 导出函数供其他模块使用
def get_complete_data():
    return complete_data_manager.data

def add_normal_test(test_data: Dict) -> str:
    return complete_data_manager.add_normal_test(test_data)

def add_continuous_test(test_data: Dict) -> str:
    return complete_data_manager.add_continuous_test(test_data)

def add_multi_session_test(test_data: Dict) -> str:
    return complete_data_manager.add_multi_session_test(test_data)

def add_or_update_round_result(test_data: Dict, round_data: Dict) -> str:
    return complete_data_manager.add_or_update_round_result(test_data, round_data)

def update_test(test_id: str, updates: Dict) -> bool:
    return complete_data_manager.update_test(test_id, updates)

def get_test(test_id: str) -> Optional[Dict]:
    return complete_data_manager.get_test(test_id)

def get_annotation_data():
    return complete_data_manager.get_annotation_data()

def add_annotation(annotation_id: str, annotation_data: Dict):
    complete_data_manager.add_annotation(annotation_id, annotation_data)
