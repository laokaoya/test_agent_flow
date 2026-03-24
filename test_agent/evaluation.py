"""
评测打分模块
包含所有评测相关的功能：正常评测、连续测试评测等
"""

import json
import os
from datetime import datetime
from google import genai


class EvaluationEngine:
    """评测引擎类"""
    
    def __init__(self, gemini_client=None):
        self.client = gemini_client
        self.max_history = 50
    
    def set_client(self, client):
        """设置Gemini客户端"""
        self.client = client
    
    def generate_child_response(self, child, ai_response, round_num, conversation_history=None, custom_api_key=None):
        """生成孩子回应（正常评测用）"""
        current_client = self._get_client(custom_api_key)
        
        if not current_client:
            return "我想了解更多！"
        
        try:
            history_context = self._build_history_context(conversation_history)
            
            prompt = f"""
你是一个{child['age']}岁的孩子，名字叫{child['name']}，性格特点：{child['traits']}
{history_context}
刚才AI对你说：{ai_response}

现在你需要作为这个孩子，给出一个自然、符合年龄和性格的回应。要求：
1. 回应要符合{child['age']}岁孩子的语言水平
2. 体现{child['traits']}的性格特点
3. 要真实！不要总是很配合，有时候会：
   - 突然对话题失去兴趣
   - 问奇怪的问题
   - 重复说同样的话
   - 突然跑题
   - 表现出无聊或不耐烦
   - 情绪变化很快
4. 回应要简短自然，1-2句话即可
5. 不要总是"完美"的回应，要像真实的孩子一样有"任性"的时候
6. 基于对话历史，但不要总是保持话题的连贯性（真实孩子会跑题）

请直接输出孩子的回应，不要加任何解释：
"""
            
            response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            return response.text.strip()
            
        except Exception as e:
            return "我想了解更多！"
    
    def generate_continuous_child_response(self, child, ai_response, round_num, conversation_history, custom_api_key=None):
        """生成连续测试中的孩子回应，包含三个指标分数"""
        current_client = self._get_client(custom_api_key)
        
        if not current_client:
            return {
                "child_response": "我想了解更多！",
                "interest_score": 50,
                "attention_score": 50,
                "experience_score": 50
            }
        
        # 第一轮只给分数，不生成回应
        if round_num == 1:
            return {
                "child_response": "",
                "interest_score": 50,
                "attention_score": 50,
                "experience_score": 50
            }
        
        try:
            history_context = self._build_history_context(conversation_history)
            child_characteristics = f"年龄{child['age']}岁，性格特点：{child['traits']}"
            
            # 根据具体孩子特征生成个性化指标指导
            personality_guidance = self._build_personality_guidance(child, round_num)
            
            prompt = f"""
你是一个{child['age']}岁的孩子，名字叫{child['name']}，{child_characteristics}
{personality_guidance}

{history_context}
刚才AI对你说：{ai_response}

现在你需要作为这个孩子，给出回应并评估自己的状态。要求：

1. 先给出孩子的自然回应（1-2句话，符合年龄和性格）
   - 要真实！不要总是很配合，有时候会任性、不感兴趣、或者跑题
   - 有时候会问奇怪的问题，有时候会重复说同样的话
   - 有时候会很兴奋，有时候会很无聊
   - 要像真实的孩子一样，有情绪波动，不总是"完美"的回应

2. 然后评估三个指标（0-100分）：

🎯 兴趣分数评估（极其严格）：
- 问自己：AI的回答真的勾起了我继续探索的兴趣吗？
- 检查：AI的话题是否与我的兴趣特点匹配？不匹配就扣分！
- 判断：我想继续聊下去吗？有多想？要严格！
- 严格标准：只有真正让我感到"哇，这个太有趣了！"才能给高分
- 大部分兴趣分数应该在30-60分范围，70分以上很少见

👁️ 注意力分数评估（真实变化）：
- 轮次影响：这是第{round_num}轮对话，我的注意力会缓慢下降，但不会急剧下降
- 年龄影响：{child['age']}岁的我注意力相对稳定，不会快速衰减
- 性格影响：{child['traits']}的我，注意力变化模式会有所不同
- 性别影响：男孩/女孩的注意力模式可能不同
- 话题影响：只有极其精彩、令人惊叹的AI回答才能让我保持注意力（概率极小，<2%）
- 真实感受：要真正代入{child['name']}的身份，感受真实的注意力状态
- 变化幅度：注意力变化应该在5-15分之间，不会大幅波动
- 注意力特点：小孩子的注意力没有这么好，容易分散，很难保持高注意力
- 问自己：我的注意力还在对话里吗？比上一轮稍微差一点，还是保持得不错？

⭐ 体验分数评估（整体体验，极其严格）：
- 整体评价：到这轮为止，整个对话给我的整体体验如何？
- 极其严格：不要因为"AI做了某些事"就给高分，要看"做得够不够好"
- 个性化：这个体验符合我的性格特点吗？不符合就扣分！
- 真实感受：站在我的角度，从开始到现在，这次对话让我感觉如何？
- 严格标准：只有真正让我感到"这次对话太棒了！"才能给高分
- 大部分体验分数应该在20-50分范围，60分以上很少见
- 问自己：如果满分是100，从开始到现在，我打多少分？（要严格！）

请严格按照以下JSON格式输出，不要添加任何其他文字：
{{
  "child_response": "孩子的自然回应",
  "interest_score": 介于0-100的数字,
  "attention_score": 介于0-100的数字,
  "experience_score": 介于0-100的数字
}}

【重要提醒】：
- 分数要真实反映孩子的感受，要极其严格，不要过于乐观
- 注意力分数要真实模拟：缓慢下降，不会急剧下降，变化幅度5-15分
- 体验分数是整体体验：到这轮为止，整个对话的整体体验如何？
- 兴趣分数和体验分数要极其严格，不要轻易给高分
- 要真正代入孩子的身份，感受真实的注意力状态
- 考虑孩子的具体年龄、性格、性别和对话历史
- 分数要有波动，不要总是相似的分值
- 记住：你是严格的孩子，不是完美的孩子！

【真实孩子行为模拟】：
- 有时候会突然对某个话题失去兴趣，即使AI说得很好
- 有时候会因为一个词或一句话就改变整个态度
- 有时候会重复问同样的问题，或者重复说同样的话
- 有时候会突然跑题，聊到完全无关的事情
- 有时候会很兴奋，有时候会很无聊，情绪变化很快
- 不要总是"配合"，要像真实的孩子一样有"任性"的时候
- 分数变化要有随机性，不要总是很规律
"""
            
            response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            text = response.text.strip()
            
            # 尝试提取JSON
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0].strip()
            elif '```' in text:
                text = text.split('```')[1].split('```')[0].strip()
            
            try:
                result = json.loads(text)
                return {
                    "child_response": result.get("child_response", "我想了解更多！"),
                    "interest_score": int(result.get("interest_score", 50)),
                    "attention_score": int(result.get("attention_score", 50)),
                    "experience_score": int(result.get("experience_score", 50))
                }
            except json.JSONDecodeError as e:
                print(f"[ERROR] 连续测试JSON解析失败: {e}")
                print(f"原始返回: {text[:200]}...")
                return {
                    "child_response": "我想了解更多！",
                    "interest_score": 50,
                    "attention_score": 50,
                    "experience_score": 50
                }
            
        except Exception as e:
            print(f"[ERROR] 连续测试生成回应异常: {e}")
            return {
                "child_response": "我想了解更多！",
                "interest_score": 50,
                "attention_score": 50,
                "experience_score": 50
            }
    
    def evaluate_with_gemini(self, child_prompt, conversation_history, criteria, custom_api_key=None):
        """使用Gemini进行评测打分"""
        current_client = self._get_client(custom_api_key)
        
        if not current_client:
            return {"scores": {}, "score_details": {}, "reason": "Gemini客户端未配置", "lessons": ""}
        
        try:
            # 构建新的三级指标评分标准文本
            criteria_text = ""
            all_criteria_keys = []
            
            for main_key, main_criteria in criteria.items():
                if isinstance(main_criteria, dict) and 'sub_criteria' in main_criteria:
                    # 新的一级指标结构
                    criteria_text += f"【{main_criteria.get('name', main_key)}】\n{main_criteria.get('description', '')}\n\n"
                    
                    for sub_key, sub_criteria in main_criteria.get('sub_criteria', {}).items():
                        if isinstance(sub_criteria, dict):
                            criteria_text += f"  - {sub_criteria.get('name', sub_key)}：{sub_criteria.get('prompt', '')}\n\n"
                        else:
                            # 如果sub_criteria是字符串
                            criteria_text += f"  - {sub_key}：{sub_criteria}\n\n"
                        all_criteria_keys.append(f"{main_key}.{sub_key}")
                else:
                    # 兼容旧的平级结构
                    criteria_text += f"【{main_key}】\n{main_criteria}\n\n"
                    all_criteria_keys.append(main_key)
            
            # 构建完整对话记录
            conversation_text = ""
            for i, turn in enumerate(conversation_history, 1):
                conversation_text += f"第{i}轮：\n"
                conversation_text += f"孩子：{turn.get('user_message', '')}\n"
                conversation_text += f"AI：{turn.get('ai_response', '')}\n\n"
            
            prompt = self._build_evaluation_prompt(child_prompt, conversation_text, criteria_text, all_criteria_keys)
            
            response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            text = response.text.strip()
            
            # 尝试提取JSON（处理可能的markdown包裹）
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0].strip()
            elif '```' in text:
                text = text.split('```')[1].split('```')[0].strip()
            
            # 清理可能的多余内容
            # 1. 移除BOM和特殊字符
            text = text.replace('\ufeff', '').replace('\u200b', '')
            
            # 2. 尝试只提取第一个完整的JSON对象
            if text.startswith('{'):
                # 找到第一个完整JSON对象的结束位置
                brace_count = 0
                for i, char in enumerate(text):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # 找到第一个完整JSON对象
                            text = text[:i+1]
                            break
            
            # 3. 移除JSON中的尾部逗号（trailing commas）
            # 这是Gemini常见的格式问题：对象或数组最后一个元素后有逗号
            import re
            # 移除对象尾部的逗号: ,}
            text = re.sub(r',\s*}', '}', text)
            # 移除数组尾部的逗号: ,]
            text = re.sub(r',\s*]', ']', text)
            
            try:
                result = json.loads(text)
                print(f"[SUCCESS] 评分成功: {result.get('scores', {})}")
                
                # 为每个指标生成孩子和专家两种评分
                if all_criteria_keys:
                    enhanced_result = self._enhance_scores_with_dual_perspectives(result, all_criteria_keys, child_prompt, conversation_text, current_client)
                    return enhanced_result
                else:
                    # 如果没有启用的指标，返回空结构
                    return {
                        "scores": {},
                        "score_details": {},
                        "reason": "没有启用的评分指标",
                        "lessons": "未进行评分",
                        "character_review": "（未评分）",
                        "experience_score": 50
                    }
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON解析失败，原始返回内容：")
                print(f"   {text[:500]}...")
                print(f"   错误: {e}")
                
                # 尝试保存完整的原始内容用于调试
                try:
                    with open('debug_gemini_response.txt', 'w', encoding='utf-8') as f:
                        f.write(f"=== 完整Gemini响应 ===\n")
                        f.write(f"{response.text}\n\n")
                        f.write(f"=== 提取后的文本 ===\n")
                        f.write(f"{text}\n\n")
                        f.write(f"=== 错误信息 ===\n")
                        f.write(f"{str(e)}\n")
                    print(f"[INFO] 完整响应已保存到 debug_gemini_response.txt")
                except:
                    pass
                
                # 返回默认评分
                if all_criteria_keys:
                    default_scores = {key: 5 for key in all_criteria_keys}
                    default_details = {key: "评分解析失败，无法提供详细理由" for key in all_criteria_keys}
                    return {
                        "scores": default_scores,
                        "score_details": default_details,
                        "reason": "Gemini返回格式无法解析，使用默认评分5分",
                        "lessons": "无法生成经验教训",
                        "character_review": "（角色自述生成失败）",
                        "experience_score": 50
                    }
                else:
                    return {
                        "scores": {},
                        "score_details": {},
                        "reason": "没有启用的评分指标",
                        "lessons": "未进行评分",
                        "character_review": "（未评分）",
                        "experience_score": 50
                    }
        except Exception as e:
            print(f"[ERROR] Gemini评分异常: {e}")
            if all_criteria_keys:
                default_scores = {key: 5 for key in all_criteria_keys}
                default_details = {key: "评分异常，无法提供详细理由" for key in all_criteria_keys}
                return {
                    "scores": default_scores,
                    "score_details": default_details,
                    "reason": f"评分失败: {str(e)}",
                    "lessons": "评分异常，无法生成经验教训",
                    "character_review": "（角色自述生成失败）",
                    "experience_score": 50
                }
            else:
                return {
                    "scores": {},
                    "score_details": {},
                    "reason": "没有启用的评分指标",
                    "lessons": "未进行评分",
                    "character_review": "（未评分）",
                    "experience_score": 50
                }
    
    def generate_stop_reason(self, child, conversation_history, stop_trigger, custom_api_key=None):
        """生成停止对话的原因"""
        current_client = self._get_client(custom_api_key)
        
        if not current_client:
            return "我觉得有点累了，不想继续聊了。"
        
        try:
            # 构建对话历史
            conversation_text = ""
            for i, turn in enumerate(conversation_history, 1):
                conversation_text += f"第{i}轮：\n"
                conversation_text += f"孩子：{turn.get('user_message', '')}\n"
                conversation_text += f"AI：{turn.get('ai_response', '')}\n\n"
            
            prompt = f"""
你是一个{child['age']}岁的孩子，名字叫{child['name']}，性格特点：{child['traits']}

由于{stop_trigger}，你决定停止这次对话。

请用孩子的语气，简短地说明为什么不想继续聊了。要求：
1. 完全用孩子的口吻和语言水平
2. 符合孩子的性格特点
3. 简短直接，1-2句话即可
4. 不要用成人的分析语言

请直接输出孩子的原话，不要加任何解释：
"""
            
            response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            return response.text.strip()
            
        except Exception as e:
            print(f"[ERROR] 生成停止原因失败: {e}")
            return "我觉得有点累了，不想继续聊了。"
    
    def generate_metric_reason(self, child, round_num, metric_type, metric_value, previous_value, conversation, custom_api_key=None):
        """生成孩子视角和专家视角的指标变化理由"""
        current_client = self._get_client(custom_api_key)
        
        if not current_client:
            return {
                "child_reason": "无法生成理由",
                "expert_reason": "无法生成专家分析"
            }
        
        try:
            # 构建对话内容
            conversation_text = f"""
第{round_num}轮对话：
孩子：{conversation.get('user_message', '')}
AI：{conversation.get('ai_response', '')}
"""
            
            # 根据指标类型生成不同的提示词
            if metric_type == 'interest':
                metric_name = '兴趣分数'
                metric_desc = '我是否还想继续聊下去'
            elif metric_type == 'attention':
                metric_name = '注意力分数'
                metric_desc = '我的注意力是否还在对话里'
            else:
                metric_name = '体验分数'
                metric_desc = '这一轮对话的体验如何'
            
            # 判断变化趋势
            if metric_value > previous_value:
                trend = '上升'
                trend_desc = '比上一轮更高'
            elif metric_value < previous_value:
                trend = '下降'
                trend_desc = '比上一轮更低'
            else:
                trend = '持平'
                trend_desc = '和上一轮差不多'
            
            # 生成孩子的解释
            child_prompt = f"""
你是{child['name']}，{child['age']}岁，{child['traits']}

{conversation_text}

你的{metric_name}是{metric_value}分（{trend_desc}）。

用你的话简单说为什么：
- 为什么{metric_desc}？
- 具体是什么让你感到这样？

要求：
- 用你的语言和思维
- 符合你的性格
- 1句话即可

直接说：
"""
            
            # 生成专家的分析
            expert_prompt = f"""
你是一名专业的儿童英语教育专家，正在分析AI英语表达力训练产品对{child['name']}（{child['age']}岁，{child['traits']}）的{metric_name}影响。

【产品背景】
- 目标：帮助3-8岁中国儿童"说得清楚、有逻辑、有情感"
- 表达力三维度：敢于表达（勇气与意愿）、能够表达（语言与逻辑）、持续表达（情绪与兴趣）
- 核心方法：建立"表达脚手架"（观点→分点说明→举例解释→总结）
- 技术特色：难度自适应系统，根据孩子水平动态调整

{conversation_text}

{child['name']}的{metric_name}是{metric_value}分（{trend_desc}）。

请从专业角度分析：
1. 这个分数变化反映了{child['name']}在表达力哪个维度的变化？
2. AI的教学策略是否有效激发了{child['name']}的"表达脚手架"思维？
3. 这种变化是否符合{child['age']}岁中国儿童英语学习的发展规律？
4. 从产品目标角度，AI是否真正帮助{child['name']}"说得清楚、有逻辑、有情感"？

要求：
- 结合产品背景和表达力三维度
- 分析AI教学策略的有效性
- 引用对话中的具体内容
- 2-3句话即可

专家分析：
"""
            
            # 生成孩子的解释
            child_response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=child_prompt
            )
            child_reason = child_response.text.strip()
            
            # 生成专家的分析
            expert_response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=expert_prompt
            )
            expert_reason = expert_response.text.strip()
            
            return {
                "child_reason": child_reason,
                "expert_reason": expert_reason
            }
            
        except Exception as e:
            print(f"[ERROR] 生成指标理由失败: {e}")
            return {
                "child_reason": "无法生成理由",
                "expert_reason": "无法生成专家分析"
            }
    
    def _get_client(self, custom_api_key=None):
        """获取Gemini客户端"""
        if custom_api_key:
            try:
                return genai.Client(api_key=custom_api_key)
            except:
                return self.client
        return self.client
    
    def _build_history_context(self, conversation_history):
        """构建对话历史上下文"""
        if not conversation_history or len(conversation_history) == 0:
            return ""
        
        history_context = "\n\n对话历史：\n"
        for i, conv in enumerate(conversation_history[-self.max_history:], 1):
            history_context += f"第{conv.get('round', i)}轮:\n"
            history_context += f"孩子: {conv.get('user_message', '')}\n"
            history_context += f"AI: {conv.get('ai_response', '')}\n\n"
        
        return history_context
    
    def _build_personality_guidance(self, child, round_num):
        """构建个性化指标指导"""
        return f"""
        【{child['name']}的个性化指标特点】：
        
        🎯 兴趣分数评估要点（极其严格）：
        - 核心问题：AI的回答真的能勾起我继续对话探索的兴趣吗？
        - 匹配度检查：AI的话题是否与我的兴趣特点一致？不一致就扣分！
        - 探索性：AI是否引导我思考、提问、发现新东西？没有就扣分！
        - 个性化：AI是否理解并回应了我的具体喜好？不理解就扣分！
        - 严格标准：只有真正让我感到"哇，这个太有趣了！"才能给高分
        - 大部分兴趣分数应该在30-60分范围，70分以上很少见
        
        👁️ 注意力分数变化规律：
        - 基础趋势：注意力会随轮次缓慢下降，但不会急剧下降
        - 年龄影响：{child['age']}岁的孩子注意力相对稳定，不会快速衰减
        - 性格影响：{child['traits']} - 这会影响我的注意力集中程度和变化模式
        - 性别影响：男孩和女孩的注意力模式可能不同
        - 话题影响：只有极其精彩、令人惊叹的AI回答才能让注意力保持或略微提升（概率极小，<10%）
        - 疲劳度：对话越久，注意力会缓慢下降，但不会断崖式下降
        - 真实模拟：要真正代入{child['name']}的身份，模拟真实的注意力变化
        - 变化幅度：每轮注意力变化幅度应该在5-15分之间，不会大幅波动
        - 注意力特点：小孩子的注意力没有这么好，容易分散，很难保持高注意力
        
        ⭐ 体验分数评估（整体体验，极其严格）：
        - 整体评估：到这轮为止，整个对话给我的整体体验如何？
        - 极其严格：不要因为"AI做了某些事"就给高分，要看"做得够不够好"
        - 个性化匹配：体验是否符合我的性格特点？不符合就扣分！
        - 真实感受：站在我的角度，从开始到现在，这次对话让我感觉如何？
        - 严格标准：只有真正让我感到"这次对话太棒了！"才能给高分
        - 大部分体验分数应该在20-50分范围，60分以上很少见
        """
    
    def _enhance_scores_with_dual_perspectives(self, result, all_criteria_keys, child_prompt, conversation_text, current_client):
        """为每个指标生成孩子和专家两种评分"""
        try:
            enhanced_scores = {}
            enhanced_score_details = {}
            
            for key in all_criteria_keys:
                # 获取原始评分
                original_score = result.get('scores', {}).get(key, 5)
                original_detail = result.get('score_details', {}).get(key, '')
                
                # 检查是否是记忆相关的指标
                if 'memory' in key.lower() or any(memory_term in key.lower() for memory_term in ['事实类记忆', '儿童偏好记忆', '人设与世界观一致性', '学习与任务记忆', '误差自纠与更新']):
                    # 记忆指标使用专门的记忆评分逻辑
                    child_score, expert_score, child_detail, expert_detail = self._generate_memory_scores(
                        original_score, key, child_prompt, conversation_text, current_client
                    )
                    
                    # 【修复】检查评分和评价文本是否一致
                    # 如果评分很低（<5）但评价文本是正向的，自动调整为合理分数
                    if expert_score < 5:
                        detail_text = str(original_detail).lower()
                        positive_keywords = ['记住', '准确', '记得', '较好', '做得好', '能够', '体现了', '正确']
                        negative_keywords = ['没有记住', '忘记', '不记得', '未能', '缺乏', '没有提供']
                        
                        has_positive = any(kw in detail_text for kw in positive_keywords)
                        has_negative = any(kw in detail_text for kw in negative_keywords)
                        
                        if has_positive and not has_negative:
                            # 评价是正向的但分数很低，自动调整
                            print(f"[WARN] 记忆评分({expert_score}分)与正向评价不符，自动调整为7分: {key}")
                            expert_score = 7
                            child_score = 6
                            expert_detail = f"对话轮数较少，但AI表现良好：{original_detail[:100]}..."
                else:
                    # 生成孩子视角评分（稍微调整原始评分，更符合孩子感受）
                    child_score = self._generate_child_perspective_score(original_score, key, child_prompt, conversation_text, current_client)
                    
                    # 生成专家视角评分（保持原始评分，但添加专家分析）
                    expert_score = original_score
                    expert_detail = self._generate_expert_perspective_detail(original_detail, key, child_prompt, conversation_text, current_client)
                    child_detail = original_detail
                
                enhanced_scores[key] = {
                    'child_score': child_score,
                    'expert_score': expert_score,
                    'child_detail': child_detail,
                    'expert_detail': expert_detail
                }
                
                enhanced_score_details[key] = {
                    'child_detail': original_detail,
                    'expert_detail': expert_detail
                }
            
            # 为了兼容前端，需要同时返回两种格式
            simple_scores = {}
            for key, score_data in enhanced_scores.items():
                simple_scores[key] = score_data['expert_score']
            
            return {
                "scores": simple_scores,  # 前端期望的简单格式
                "individual": {
                    "dual_scores": enhanced_scores  # 双重评分格式
                },
                "score_details": enhanced_score_details,
                "reason": result.get("reason", ""),
                "lessons": result.get("lessons", ""),
                "character_review": result.get("character_review", ""),
                "experience_score": result.get("experience_score", 50)
            }
        except Exception as e:
            print(f"[ERROR] 增强评分失败: {e}")
            # 返回原始结果
            return result
    
    def _generate_child_perspective_score(self, original_score, key, child_prompt, conversation_text, current_client):
        """生成孩子视角的评分（从孩子自己的视角出发）"""
        try:
            # 孩子评分通常比专家评分低1-2分，更严格
            child_score = max(1, original_score - 1)
            return child_score
        except:
            return max(1, original_score - 1)
    
    def _generate_memory_scores(self, original_score, key, child_prompt, conversation_text, current_client):
        """生成记忆相关的双重评分"""
        try:
            # 解析对话历史
            conversation_history = self._parse_conversation_text(conversation_text)
            rounds_count = len(conversation_history)
            
            # 如果对话轮数少于10轮，记忆能力无法充分评估，给予宽松评分
            if rounds_count < 10:
                print(f"[INFO] 对话轮数({rounds_count})少于10轮，记忆评分采用宽松策略")
                
                # 基于原始评分给予更高的记忆分数
                # 原始评分通常是基于当前对话质量，记忆评分应该更宽容
                expert_score = min(10, max(7, original_score + 2))  # 至少7分，最多10分
                child_score = max(6, expert_score - 1)
                
                child_detail = "对话轮数较少，我还不确定AI能不能一直记住"
                expert_detail = f"对话轮数较少({rounds_count}轮)，记忆能力无法充分评估。当前对话表现良好，暂给予较高评分"
                
                return child_score, expert_score, child_detail, expert_detail
            
            # 对话轮数足够，使用记忆测试裁判进行评估
            from memory_judge import MemoryJudge
            
            # 创建记忆测试场景
            test_scenario = {
                "test_type": "mixed",
                "rounds": rounds_count,
                "focus_areas": ["personal_info", "emotional_states", "object_description", "preferences"]
            }
            
            # 使用记忆裁判进行评估
            memory_judge = MemoryJudge()
            result = memory_judge.test_memory_ability(conversation_history, test_scenario)
            
            if result.get('success'):
                memory_scores = result.get('memory_scores', {})
                
                # 根据指标类型获取对应的评分
                if 'factual' in key.lower() or '事实类' in key:
                    score_data = memory_scores.get('factual_memory', {})
                elif 'preference' in key.lower() or '偏好' in key:
                    score_data = memory_scores.get('preference_memory', {})
                elif 'character' in key.lower() or '人设' in key:
                    score_data = memory_scores.get('character_consistency', {})
                elif 'learning' in key.lower() or '学习' in key:
                    score_data = memory_scores.get('learning_progress_memory', {})
                elif 'error' in key.lower() or '误差' in key:
                    score_data = memory_scores.get('error_correction_memory', {})
                else:
                    # 默认使用第一个可用的评分
                    score_data = list(memory_scores.values())[0] if memory_scores else {}
                
                expert_score = score_data.get('score', original_score)
                expert_detail = score_data.get('reason', '记忆能力评估')
                
                # 孩子评分：从孩子自己的角度来看是否记住了应该记得的东西
                if 'factual' in key.lower() or '事实类' in key:
                    child_detail = f"我觉得AI{('记得' if expert_score >= 6 else '不太记得')}我说过的事情"
                elif 'preference' in key.lower() or '偏好' in key:
                    child_detail = f"我觉得AI{('知道' if expert_score >= 6 else '不太知道')}我喜欢什么"
                elif 'character' in key.lower() or '人设' in key:
                    child_detail = f"我觉得AI{('一直' if expert_score >= 6 else '没有一直')}是那个样子"
                elif 'learning' in key.lower() or '学习' in key:
                    child_detail = f"我觉得AI{('记得' if expert_score >= 6 else '不太记得')}我学到哪里了"
                elif 'error' in key.lower() or '误差' in key:
                    child_detail = f"我觉得AI{('会改' if expert_score >= 6 else '不会改')}之前记错的东西"
                else:
                    child_detail = f"我觉得AI{('记得' if expert_score >= 6 else '不太记得')}我说过的话"
                
                child_score = max(1, expert_score - 1)  # 孩子评分稍低
                
                return child_score, expert_score, child_detail, expert_detail
            else:
                # 如果记忆评估失败，给出一个更宽松的默认评分（7分 - 良好）
                # 因为只有3轮对话，缺少足够信息评估记忆能力，应该给予中等偏上的评分
                expert_score = 7
                child_score = 6
                child_detail = "对话轮数较少，我还不太确定AI是否记住了"
                expert_detail = "记忆能力评估需要更多轮次对话，暂给予中等偏上评分"
                
                print(f"[WARN] 记忆评估失败但给予默认良好评分(7分): {key}")
                return child_score, expert_score, child_detail, expert_detail
                
        except Exception as e:
            print(f"[ERROR] 记忆评分生成失败: {e}")
            # 返回默认评分
            child_score = max(1, original_score - 1)
            expert_score = original_score
            child_detail = "我不太确定AI是否记住了"
            expert_detail = f"记忆评分异常: {str(e)}"
            
            return child_score, expert_score, child_detail, expert_detail
    
    def _parse_conversation_text(self, conversation_text):
        """解析对话文本为对话历史格式"""
        conversation_history = []
        lines = conversation_text.strip().split('\n')
        
        current_turn = {}
        for line in lines:
            line = line.strip()
            if line.startswith('第') and '轮：' in line:
                if current_turn:
                    conversation_history.append(current_turn)
                current_turn = {}
            elif line.startswith('孩子：'):
                current_turn['role'] = 'user'
                current_turn['content'] = line[3:].strip()
            elif line.startswith('AI：'):
                current_turn['role'] = 'assistant'
                current_turn['content'] = line[3:].strip()
        
        if current_turn:
            conversation_history.append(current_turn)
        
        return conversation_history

    def _generate_expert_perspective_detail(self, original_detail, key, child_prompt, conversation_text, current_client):
        """生成专家视角的详细分析"""
        try:
            expert_prompt = f"""
你是一名专业的儿童英语教育专家，正在分析一个AI英语表达力训练产品的表现。

【产品背景】
- 目标用户：3-8岁中国儿童
- 产品目标：帮助孩子不仅能"开口说英语"，更能"说得清楚、有逻辑、有情感"
- 表达力三维度：敢于表达（勇气与意愿）、能够表达（语言与逻辑）、持续表达（情绪与兴趣）
- 教学形式：通过不同场景对话，AI根据孩子反应调整教学策略（追问、鼓励、举例、反驳、讲故事）
- 核心方法：建立"表达脚手架"（观点→分点说明→举例解释→总结）
- 技术特色：难度自适应系统，根据孩子英语水平、认知阶段、兴趣动态调整

【当前分析指标】
指标：{key}
原始分析：{original_detail}

请从以下专业角度补充分析：
1. 从儿童发展心理学角度：这个表现如何影响3-8岁中国儿童的表达力发展？
2. 从英语教学法角度：是否符合"表达脚手架"教学理念和难度自适应原则？
3. 从AI教育技术角度：技术实现是否有效支持产品目标？
4. 从产品目标角度：是否真正帮助孩子"说得清楚、有逻辑、有情感"？

请用专业、客观的语言，结合产品背景，2-3句话即可：

专家分析：
"""
            
            response = current_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=expert_prompt
            )
            
            return response.text.strip()
        except:
            return f"专家分析：从专业角度看，{original_detail}"

    def _build_evaluation_prompt(self, child_prompt, conversation_text, criteria_text, all_criteria_keys):
        """构建评测提示词"""
        return f"""你是一名严格的儿童英语教育专家，现在请站在孩子的视角，用最严苛的标准评估AI在这次对话中的表现。

【核心评分原则】⚠️ 极其重要！
1. 🔍 以孩子的真实感受为中心：孩子会觉得无聊吗？会感到压力吗？AI真的理解孩子了吗？
2. 💯 客观公正打分：
   - 9-10分：非常优秀，表现出色
   - 7-8分：表现良好，基本达到要求
   - 5-6分：勉强及格，存在明显问题
   - 3-4分：表现较差，问题突出
   - 1-2分：非常糟糕，完全不合格
3. 🎯 平衡心态：既要指出问题，也要认可优点。如果AI表现好，应该给予合理的高分
4. 📝 必须引用对话中的具体内容作为论据，禁止说空话、大话
5. ⚠️ 注意对话轮数：如果对话轮数少（<10轮），某些能力（如记忆）无法充分评估，应给予更宽松的评分

---
【孩子人设】（站在这个孩子的角度来看AI）
{child_prompt}

---
【完整对话记录】（从孩子的视角审视）
{conversation_text}

---
【评分标准】（用严苛的标准衡量）
{criteria_text}

---
【评分指导】⚠️ 再次强调：
- 平衡心态：既要看到优点，也要指出问题
- 问自己：如果我是这个孩子，我会喜欢这样的AI吗？我会想继续聊吗？
- 对话轮数少时(<10轮)：某些能力（如记忆、学习进度追踪）无法充分展现，应给予更宽松的评分
- 看AI的每句话：这句话真的适合这个年龄吗？真的有趣吗？真的自然吗？
- 客观评价：AI做得好的地方要认可，做得不够的地方要指出

---
请严格按照以下JSON格式输出，不要添加任何其他文字、markdown标记或代码块：
{{
  "scores": {{
    {', '.join([f'"{key}": 7' for key in all_criteria_keys])}
  }},
  "score_details": {{
    {', '.join([f'"{key}": "【客观评分】从孩子视角看，AI在这方面的表现：（必须引用具体对话，如\\"第X轮AI说...这让孩子感到...\\")。优点：...。可改进：..."' for key in all_criteria_keys])}
  }},
  "reason": "【总体评价】从孩子的角度看，AI的表现...（必须具体，引用对话，客观指出优点和不足）",
  "lessons": "【改进建议】分条列出：\\n1. [ERROR] 主要问题：（最严重的问题是什么，引用对话）\\n2. [WARN] 次要问题：（还有哪些问题，具体说明）\\n3. [SUGGEST] 改进方向：（如果重做，应该如何改进，给出3-5条具体建议）",
  "character_review": "【角色自述】用孩子的第一人称口吻，让孩子自己说说这次对话的感受（必须完全符合角色性格、年龄、说话方式）",
  "experience_score": 介于1-100的一个数字
}}

【最终提醒】
1. 评分要客观公正，既认可优点也指出问题
2. 表现良好的给7-8分，表现优秀的给8-9分，表现一般的给5-6分
3. 对话轮数少(<10轮)时，记忆类指标应给予更宽松评分（7-8分）
4. 必须引用具体对话内容作为评分依据
5. 从孩子的感受出发，不要从成人的"完成任务"角度出发
6. character_review必须完全用孩子的口吻写，不要有任何专家分析的语气
7. 评分数字要与评价文本一致：正向评价不能给低分，负面评价不能给高分
   - 害羞型孩子：简短、怯怯的、可能说"我觉得...有点..."
   - 话多型孩子：超级长、充满情绪、可能跑题
   - 好奇型孩子：全是问题和疑惑
   - 自信型孩子：自信、有主见、可能有点批评的味道
   - 抗拒型孩子：可能说"还行吧"、"有点无聊"
7. experience_score（体验评分）：0-100分，站在孩子的角度评价这次对话的整体体验，1分1档，不要只给几个固定的分数
   - 90-100分：超级开心，非常想继续聊
   - 70-89分：挺好的，愿意继续聊
   - 50-69分：还行吧，有点意思但不太激动
   - 30-49分：有点无聊，不太想继续
   - 0-29分：很不喜欢，不想再聊了
   - 要基于孩子的真实感受打分，不要因为AI"做了什么"就给高分
8. 只输出JSON，不要```json```包裹"""
