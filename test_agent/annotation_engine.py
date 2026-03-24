"""
标注训练引擎
用于处理专家评分的标注数据和模型训练
"""

import json
import os
import statistics
from datetime import datetime
from typing import List, Dict, Any
import threading

# 文件路径
ANNOTATION_FILE = 'data/annotations.json'
IMPROVEMENTS_FILE = 'data/improvements.json'

# 线程锁
annotation_lock = threading.Lock()

class AnnotationEngine:
    """标注训练引擎"""
    
    def __init__(self):
        self.annotations = self.load_annotations()
        self.improvements = self.load_improvements()
    
    def load_annotations(self) -> List[Dict]:
        """加载标注数据"""
        try:
            if os.path.exists(ANNOTATION_FILE):
                with open(ANNOTATION_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"❌ 加载标注数据失败: {e}")
            return []
    
    def load_improvements(self) -> Dict:
        """加载改进建议"""
        try:
            if os.path.exists(IMPROVEMENTS_FILE):
                with open(IMPROVEMENTS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"❌ 加载改进建议失败: {e}")
            return {}
    
    def save_annotations(self):
        """保存标注数据"""
        try:
            with annotation_lock:
                with open(ANNOTATION_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.annotations, f, ensure_ascii=False, indent=2)
            print("✅ 标注数据保存成功")
        except Exception as e:
            print(f"❌ 保存标注数据失败: {e}")
    
    def save_improvements(self):
        """保存改进建议"""
        try:
            with open(IMPROVEMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.improvements, f, ensure_ascii=False, indent=2)
            print("✅ 改进建议保存成功")
        except Exception as e:
            print(f"❌ 保存改进建议失败: {e}")
    
    def generate_annotation_data(self) -> List[Dict]:
        """从测试结果生成标注数据"""
        try:
            # 从test_results.json读取测试数据
            if not os.path.exists('data/test_results.json'):
                return []
            
            with open('data/test_results.json', 'r', encoding='utf-8') as f:
                test_results = json.load(f)
            
            annotations = []
            for i, test in enumerate(test_results):
                if 'scores' not in test or not test['scores']:
                    continue
                
                # 为每个评分指标生成标注数据
                for criterion_id, score_data in test['scores'].items():
                    if isinstance(score_data, dict) and 'child_score' in score_data and 'expert_score' in score_data:
                        annotation = {
                            'id': f"{test.get('test_id', f'test_{i}')}_{criterion_id}",
                            'test_id': test.get('test_id', f'test_{i}'),
                            'timestamp': test.get('timestamp', ''),
                            'criterion_id': criterion_id,
                            'criterion_name': self._get_criterion_name(criterion_id),
                            'criterion_description': self._get_criterion_description(criterion_id),
                            'child_score': score_data.get('child_score', 0),
                            'expert_score': score_data.get('expert_score', 0),
                            'child_analysis': test.get('score_details', {}).get(criterion_id, {}).get('child_detail', ''),
                            'expert_analysis': test.get('score_details', {}).get(criterion_id, {}).get('expert_detail', ''),
                            'conversation_history': test.get('conversations', []),
                            'agreement': self._calculate_agreement(score_data.get('child_score', 0), score_data.get('expert_score', 0)),
                            'expert_accuracy': None,  # 待标注
                            'expert_quality': None,   # 待标注
                            'suggested_score': None,  # 待标注
                            'feedback': '',           # 待标注
                            'annotated': False
                        }
                        annotations.append(annotation)
            
            return annotations
        except Exception as e:
            print(f"❌ 生成标注数据失败: {e}")
            return []
    
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
    
    def add_annotation(self, annotation_id: str, annotation_data: Dict):
        """添加标注数据"""
        try:
            # 查找对应的标注项
            for annotation in self.annotations:
                if annotation['id'] == annotation_id:
                    annotation.update(annotation_data)
                    annotation['annotated'] = True
                    annotation['annotated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    break
            
            self.save_annotations()
            print(f"✅ 标注数据已保存: {annotation_id}")
        except Exception as e:
            print(f"❌ 添加标注数据失败: {e}")
    
    def analyze_annotations(self, annotations: List[Dict] = None) -> Dict[str, Any]:
        """分析标注数据，生成改进建议"""
        try:
            # 使用传入的标注数据或内部数据
            annotated_data = annotations if annotations else [a for a in self.annotations if a.get('annotated', False)]
            
            if not annotated_data:
                return {'message': '没有标注数据可供分析'}
            
            # 统计分析
            expert_accuracy_scores = [a.get('expert_accuracy', 0) for a in annotated_data if a.get('expert_accuracy')]
            expert_quality_scores = [a.get('expert_quality', 0) for a in annotated_data if a.get('expert_quality')]
            suggested_scores = [a.get('suggested_score', 0) for a in annotated_data if a.get('suggested_score')]
            
            # 计算平均分
            avg_accuracy = statistics.mean(expert_accuracy_scores) if expert_accuracy_scores else 0
            avg_quality = statistics.mean(expert_quality_scores) if expert_quality_scores else 0
            avg_suggested = statistics.mean(suggested_scores) if suggested_scores else 0
            
            # 分析问题模式
            low_accuracy_items = [a for a in annotated_data if a.get('expert_accuracy', 0) < 6]
            low_quality_items = [a for a in annotated_data if a.get('expert_quality', 0) < 6]
            
            # 分析评分差异
            score_differences = []
            for a in annotated_data:
                if a.get('expert_score') and a.get('suggested_score'):
                    diff = abs(a['expert_score'] - a['suggested_score'])
                    score_differences.append(diff)
            
            avg_score_diff = statistics.mean(score_differences) if score_differences else 0
            
            # 收集反馈建议
            feedback_suggestions = []
            for item in annotated_data:
                if item.get('feedback'):
                    feedback_suggestions.append({
                        'criterion': item['criterion_name'],
                        'feedback': item['feedback']
                    })
            
            # 生成改进建议
            improvements = {
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_annotations': len(annotated_data),
                'statistics': {
                    'avg_expert_accuracy': round(avg_accuracy, 2),
                    'avg_expert_quality': round(avg_quality, 2),
                    'avg_suggested_score': round(avg_suggested, 2),
                    'avg_score_difference': round(avg_score_diff, 2)
                },
                'issues': {
                    'low_accuracy_count': len(low_accuracy_items),
                    'low_quality_count': len(low_quality_items),
                    'accuracy_rate': round((len(annotated_data) - len(low_accuracy_items)) / len(annotated_data) * 100, 1),
                    'quality_rate': round((len(annotated_data) - len(low_quality_items)) / len(annotated_data) * 100, 1)
                },
                'feedback_suggestions': feedback_suggestions,
                'prompt_improvements': self._generate_prompt_improvements(annotated_data),
                'scoring_improvements': self._generate_scoring_improvements(annotated_data),
                'recommendations': self._generate_recommendations(annotated_data, avg_accuracy, avg_quality, avg_score_diff)
            }
            
            self.improvements = improvements
            self.save_improvements()
            
            return improvements
        except Exception as e:
            print(f"❌ 分析标注数据失败: {e}")
            return {'error': str(e)}
    
    def _generate_prompt_improvements(self, annotated_data: List[Dict]) -> List[str]:
        """生成prompt改进建议"""
        improvements = []
        
        # 分析低质量评分的共同问题
        low_quality_items = [a for a in annotated_data if a.get('expert_quality', 0) < 6]
        
        if low_quality_items:
            improvements.append("专家分析质量较低，建议在prompt中增加更具体的分析指导")
        
        # 分析反馈中的常见问题
        common_issues = {}
        for item in annotated_data:
            if item.get('feedback'):
                # 简单的关键词提取（实际应用中可以使用更复杂的NLP技术）
                feedback = item['feedback'].lower()
                if '不准确' in feedback or '错误' in feedback:
                    common_issues['准确性'] = common_issues.get('准确性', 0) + 1
                if '不够详细' in feedback or '简单' in feedback:
                    common_issues['详细性'] = common_issues.get('详细性', 0) + 1
                if '不符合' in feedback or '偏离' in feedback:
                    common_issues['一致性'] = common_issues.get('一致性', 0) + 1
        
        for issue, count in common_issues.items():
            if count > len(annotated_data) * 0.3:  # 超过30%的标注提到此问题
                improvements.append(f"专家分析在{issue}方面存在问题，需要优化相关prompt")
        
        return improvements
    
    def _generate_scoring_improvements(self, annotated_data: List[Dict]) -> List[str]:
        """生成评分改进建议"""
        improvements = []
        
        # 分析评分偏差
        score_deviations = []
        for item in annotated_data:
            if item.get('suggested_score') and item.get('expert_score'):
                deviation = abs(item['suggested_score'] - item['expert_score'])
                score_deviations.append(deviation)
        
        if score_deviations:
            avg_deviation = statistics.mean(score_deviations)
            if avg_deviation > 2:
                improvements.append("专家评分与建议评分偏差较大，需要调整评分标准")
        
        # 分析一致性
        low_agreement_items = [a for a in annotated_data if a.get('agreement', 0) < 60]
        if len(low_agreement_items) > len(annotated_data) * 0.4:
            improvements.append("孩子评分与专家评分一致性较低，需要优化评分逻辑")
        
        return improvements
    
    def _generate_recommendations(self, annotated_data: List[Dict], avg_accuracy: float, avg_quality: float, avg_score_diff: float) -> List[str]:
        """生成具体推荐建议"""
        recommendations = []
        
        # 基于准确性的建议
        if avg_accuracy < 7:
            recommendations.append("专家评分准确性偏低，建议检查评分标准是否过于严格或模糊")
        elif avg_accuracy > 8.5:
            recommendations.append("专家评分准确性很高，可以考虑保持当前标准")
        
        # 基于质量的分析
        if avg_quality < 6:
            recommendations.append("专家分析质量需要提升，建议在prompt中增加更详细的分析框架")
        elif avg_quality > 8:
            recommendations.append("专家分析质量优秀，可以作为其他标准的参考")
        
        # 基于评分差异的建议
        if avg_score_diff > 2:
            recommendations.append("专家评分与建议评分差异较大，建议重新审视评分标准的一致性")
        elif avg_score_diff < 1:
            recommendations.append("专家评分与建议评分高度一致，评分标准运行良好")
        
        # 基于反馈的建议
        feedback_count = len([a for a in annotated_data if a.get('feedback')])
        if feedback_count > 0:
            recommendations.append(f"收集到 {feedback_count} 条反馈建议，建议优先处理高频问题")
        
        return recommendations

    def update_expert_prompts(self, improvements: Dict[str, Any]):
        """根据改进建议更新专家prompt"""
        try:
            # 这里可以实现自动更新evaluation.py中的prompt
            # 或者生成更新建议供人工审核
            print("📝 专家prompt更新建议已生成")
            print("建议手动审核并更新evaluation.py中的相关prompt")
            
            # 可以在这里添加自动更新逻辑
            # 例如：读取evaluation.py，根据improvements更新prompt，写回文件
            
        except Exception as e:
            print(f"❌ 更新专家prompt失败: {e}")

# 全局实例
annotation_engine = AnnotationEngine()

# 导出函数供app.py使用
def generate_annotation_data():
    return annotation_engine.generate_annotation_data()

def save_annotation_to_file(annotation_id: str, annotation_data: Dict):
    annotation_engine.add_annotation(annotation_id, annotation_data)

def analyze_annotations(annotations: List[Dict]):
    return annotation_engine.analyze_annotations(annotations)

def update_expert_prompts(improvements: Dict[str, Any]):
    annotation_engine.update_expert_prompts(improvements)
