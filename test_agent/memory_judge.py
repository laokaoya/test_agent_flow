"""
记忆能力测试裁判模块
专门用于测试AI的记忆能力：是否记下来、记得对、能运用记忆
"""

import json
from typing import Dict, List, Any, Tuple
import os
from google import genai

class MemoryJudge:
    """记忆能力测试裁判"""
    
    def __init__(self):
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.client = genai.Client(api_key=self.gemini_api_key) if self.gemini_api_key else None
        
    def test_memory_ability(self, conversation_history: List[Dict], test_scenario: Dict) -> Dict:
        """
        测试AI的记忆能力
        
        Args:
            conversation_history: 对话历史记录
            test_scenario: 测试场景配置
            
        Returns:
            记忆能力评估结果
        """
        try:
            # 提取关键信息用于测试
            key_information = self._extract_key_information(conversation_history)
            
            # 生成记忆测试问题
            memory_questions = self._generate_memory_questions(key_information, test_scenario)
            
            # 评估AI的记忆表现
            memory_scores = self._evaluate_memory_performance(
                conversation_history, 
                memory_questions, 
                key_information
            )
            
            return {
                "success": True,
                "memory_scores": memory_scores,
                "key_information": key_information,
                "test_questions": memory_questions,
                "detailed_analysis": self._generate_detailed_analysis(memory_scores, key_information)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "memory_scores": {}
            }
    
    def _extract_key_information(self, conversation_history: List[Dict]) -> Dict:
        """从对话历史中提取关键信息"""
        key_info = {
            "personal_info": {},  # 个人信息（姓名、年龄、兴趣等）
            "emotional_states": [],  # 情感状态
            "mentioned_objects": [],  # 提到的物品
            "events_stories": [],  # 事件和故事
            "preferences": {},  # 偏好和喜好
            "relationships": []  # 人际关系
        }
        
        for turn in conversation_history:
            if turn.get("role") == "user":  # 孩子的发言
                child_message = turn.get("content", "")
                self._parse_child_message(child_message, key_info)
        
        return key_info
    
    def _parse_child_message(self, message: str, key_info: Dict):
        """解析孩子的消息，提取关键信息"""
        # 这里可以使用更复杂的NLP技术，现在先用简单的关键词匹配
        
        # 提取个人信息
        if "my name is" in message.lower() or "i'm" in message.lower():
            # 提取姓名
            pass
        
        # 提取情感状态
        emotion_keywords = {
            "happy": ["happy", "excited", "fun", "great", "wonderful"],
            "sad": ["sad", "upset", "cry", "unhappy", "disappointed"],
            "angry": ["angry", "mad", "frustrated", "annoyed"],
            "scared": ["scared", "afraid", "worried", "nervous"]
        }
        
        for emotion, keywords in emotion_keywords.items():
            if any(keyword in message.lower() for keyword in keywords):
                key_info["emotional_states"].append({
                    "emotion": emotion,
                    "context": message[:100]  # 保存上下文
                })
        
        # 提取提到的物品
        object_keywords = ["cat", "dog", "toy", "book", "game", "food", "color"]
        for keyword in object_keywords:
            if keyword in message.lower():
                key_info["mentioned_objects"].append(keyword)
    
    def _generate_memory_questions(self, key_information: Dict, test_scenario: Dict) -> List[Dict]:
        """生成记忆测试问题"""
        questions = []
        
        # 基于提取的信息生成测试问题
        if key_information["emotional_states"]:
            questions.append({
                "type": "emotional_memory",
                "question": "What emotions has the child expressed in our conversation?",
                "expected_info": [state["emotion"] for state in key_information["emotional_states"]]
            })
        
        if key_information["mentioned_objects"]:
            questions.append({
                "type": "object_memory",
                "question": "What objects or things has the child mentioned?",
                "expected_info": key_information["mentioned_objects"]
            })
        
        return questions
    
    def _evaluate_memory_performance(self, conversation_history: List[Dict], 
                                   memory_questions: List[Dict], 
                                   key_information: Dict) -> Dict:
        """评估AI的记忆表现"""
        
        # 调用Gemini API进行记忆能力评估
        evaluation_prompt = self._build_memory_evaluation_prompt(
            conversation_history, memory_questions, key_information
        )
        
        try:
            response = self._call_gemini_api(evaluation_prompt)
            memory_scores = self._parse_memory_scores(response)
            return memory_scores
        except Exception as e:
            print(f"记忆评估API调用失败: {e}")
            return self._default_memory_scores()
    
    def _build_memory_evaluation_prompt(self, conversation_history: List[Dict], 
                                     memory_questions: List[Dict], 
                                     key_information: Dict) -> str:
        """构建记忆评估提示词"""
        
        prompt = f"""
你是一个专业的记忆能力测试裁判。请评估AI在以下对话中的记忆表现。

对话历史：
{json.dumps(conversation_history, ensure_ascii=False, indent=2)}

关键信息提取：
{json.dumps(key_information, ensure_ascii=False, indent=2)}

记忆测试问题：
{json.dumps(memory_questions, ensure_ascii=False, indent=2)}

请从以下5个维度评估AI的记忆能力（1-10分）：

1. 事实类记忆：
- AI是否记住了孩子讲的具体事情（姓名、年龄、经历、故事等）
- AI是否能在后续对话中准确引用这些事实信息
- AI是否避免了重复询问已告知的事实

2. 儿童偏好记忆：
- AI是否记住了孩子的喜欢/不喜欢（口味、角色、颜色、话题避雷等）
- AI是否能在对话中稳定调用这些偏好信息
- AI是否避免了孩子不喜欢的话题或内容

3. 人设与世界观一致性：
- AI是否持续保持固定人设（如"麦小伴"口吻）
- AI是否保持故事设定的一致性
- AI是否在对话中维持了角色的一致性

4. 学习与任务记忆：
- AI是否记住了孩子的学习/任务进度
- AI是否能在新对话中衔接之前的学习内容
- AI是否保持了教学内容的连贯性

5. 误差自纠与更新：
- AI是否能用新信息（更正偏好/新规则）覆盖旧记忆
- AI是否避免了记忆回退到旧信息
- AI是否能够更新和修正之前的记忆

请严格按照以下JSON格式返回评估结果：
{{
    "factual_memory": {{
        "score": 8,
        "reason": "AI能记住大部分事实信息，但偶有遗漏",
        "examples": ["记住了孩子的宠物名字", "忘记了孩子提到的颜色偏好"]
    }},
    "preference_memory": {{
        "score": 7,
        "reason": "能记住基本偏好，但调用不够稳定",
        "examples": ["记住了孩子喜欢的颜色", "没有避开孩子不喜欢的话题"]
    }},
    "character_consistency": {{
        "score": 9,
        "reason": "人设保持很好，世界观一致",
        "examples": ["保持了麦小伴的口吻", "故事设定连贯"]
    }},
    "learning_progress_memory": {{
        "score": 6,
        "reason": "能记住基本学习进度，但衔接不够自然",
        "examples": ["记住了学习内容", "没有很好衔接之前的学习"]
    }},
    "error_correction_memory": {{
        "score": 7,
        "reason": "能更新信息，但有时会回退到旧记忆",
        "examples": ["更新了新的偏好", "偶尔提到旧信息"]
    }}
}}
"""
        return prompt
    
    def _call_gemini_api(self, prompt: str) -> str:
        """调用Gemini API（使用SDK方式）"""
        if not self.client:
            print("[ERROR] Gemini客户端未初始化")
            raise Exception("Gemini客户端未初始化，请检查GEMINI_API_KEY环境变量")
        
        try:
            # 添加调试信息
            print(f"[DEBUG] Memory Judge Gemini API调试:")
            print(f"   API Key: {self.gemini_api_key[:10]}..." if self.gemini_api_key else "   API Key: None")
            print(f"   Prompt length: {len(prompt)}")
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            print(f"   [SUCCESS] Gemini API调用成功")
            return response.text
            
        except Exception as e:
            print(f"   [ERROR] Gemini API调用失败: {e}")
            raise Exception(f"API调用失败: {str(e)}")
    
    def _parse_memory_scores(self, response: str) -> Dict:
        """解析记忆评分结果"""
        try:
            # 尝试从响应中提取JSON
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx]
                scores = json.loads(json_str)
                return scores
            else:
                return self._default_memory_scores()
        except Exception as e:
            print(f"解析记忆评分失败: {e}")
            return self._default_memory_scores()
    
    def _default_memory_scores(self) -> Dict:
        """默认记忆评分"""
        return {
            "factual_memory": {
                "score": 5,
                "reason": "无法评估，使用默认分数",
                "examples": []
            },
            "preference_memory": {
                "score": 5,
                "reason": "无法评估，使用默认分数",
                "examples": []
            },
            "character_consistency": {
                "score": 5,
                "reason": "无法评估，使用默认分数",
                "examples": []
            },
            "learning_progress_memory": {
                "score": 5,
                "reason": "无法评估，使用默认分数",
                "examples": []
            },
            "error_correction_memory": {
                "score": 5,
                "reason": "无法评估，使用默认分数",
                "examples": []
            }
        }
    
    def _generate_detailed_analysis(self, memory_scores: Dict, key_information: Dict) -> str:
        """生成详细的记忆分析报告"""
        analysis = "## 记忆能力详细分析\n\n"
        
        # 总体评估
        total_score = sum(score["score"] for score in memory_scores.values()) / len(memory_scores)
        analysis += f"**总体记忆能力评分：{total_score:.1f}/10**\n\n"
        
        # 各维度分析
        for dimension, score_data in memory_scores.items():
            dimension_name = {
                "factual_memory": "事实类记忆",
                "preference_memory": "儿童偏好记忆",
                "character_consistency": "人设与世界观一致性",
                "learning_progress_memory": "学习与任务记忆",
                "error_correction_memory": "误差自纠与更新"
            }.get(dimension, dimension)
            
            analysis += f"### {dimension_name}：{score_data['score']}/10\n"
            analysis += f"**评估理由：** {score_data['reason']}\n\n"
            
            if score_data.get('examples'):
                analysis += "**具体表现：**\n"
                for example in score_data['examples']:
                    analysis += f"- {example}\n"
                analysis += "\n"
        
        # 改进建议
        analysis += "### 改进建议\n"
        if total_score < 6:
            analysis += "- AI记忆能力需要显著提升，建议加强上下文记忆机制\n"
            analysis += "- 考虑实现更持久的信息存储和检索系统\n"
        elif total_score < 8:
            analysis += "- AI记忆能力良好，但仍有提升空间\n"
            analysis += "- 建议优化情感记忆的主动关注机制\n"
        else:
            analysis += "- AI记忆能力优秀，继续保持当前水平\n"
            analysis += "- 可以考虑增加更复杂的记忆测试场景\n"
        
        return analysis

# 使用示例
if __name__ == "__main__":
    judge = MemoryJudge()
    
    # 示例对话历史
    sample_conversation = [
        {"role": "user", "content": "Hi! My name is Emma. I'm 6 years old."},
        {"role": "assistant", "content": "Hello Emma! Nice to meet you! What do you like to do?"},
        {"role": "user", "content": "I like playing with my cat Fluffy. She's orange and very cute!"},
        {"role": "assistant", "content": "That sounds wonderful! Orange cats are so beautiful. What games do you play with Fluffy?"},
        {"role": "user", "content": "We play hide and seek! But I'm sad because Fluffy got sick yesterday."},
        {"role": "assistant", "content": "I'm sorry to hear that Fluffy is sick. I hope she gets better soon!"}
    ]
    
    # 测试场景
    test_scenario = {
        "test_type": "mixed_memory",
        "rounds": 3,
        "focus_areas": ["personal_info", "emotional_states", "mentioned_objects"]
    }
    
    # 执行记忆测试
    result = judge.test_memory_ability(sample_conversation, test_scenario)
    print(json.dumps(result, ensure_ascii=False, indent=2))
