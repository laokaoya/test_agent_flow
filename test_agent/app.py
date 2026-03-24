from flask import Flask, render_template, request, jsonify
import json
import os
import sys
from datetime import datetime
import requests
from google import genai
from dotenv import load_dotenv
import time
import csv
import threading
from evaluation import EvaluationEngine
from complete_data_manager import get_complete_data, add_normal_test, add_continuous_test, add_multi_session_test, update_test, get_test, get_annotation_data, add_annotation
from annotation_engine import analyze_annotations, update_expert_prompts
from memory_judge import MemoryJudge

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    load_dotenv()
except Exception as e:
    print(f"警告: 无法加载.env文件: {e}")

app = Flask(__name__)

import logging

class UTF8StreamHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        if sys.platform == 'win32':
            self.stream = io.TextIOWrapper(
                sys.stderr.buffer if hasattr(sys.stderr, 'buffer') else sys.stderr,
                encoding='utf-8',
                errors='replace'
            )

if not app.debug:
    handler = UTF8StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

DIFY_API_URL = "http://dify.myia.fun/v1/chat-messages"
DIFY_API_KEY = "app-H2vp53SbK9fzU3l0coIKqEVI"  #"app-Gkp3pbFwcubZ2IeO7IXAq5Wx"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBKlCSu_ZCyuhYZxplIgOm9CDYc1q3HTuA")

MAX_HISTORY = 3
MAX_ROUNDS = 3
USE_CONVERSATION_ID = True

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# 初始化评测引擎
evaluation_engine = EvaluationEngine(client)

# 数据文件路径
CSV_FILE = os.path.join("data", "test_results.csv")
JSON_FILE = os.path.join("data", "test_results.json")
CONTINUOUS_JSON_FILE = os.path.join("data", "continuous_test_results.json")
file_lock = threading.Lock()

def save_to_csv(test_data):
    """保存测试结果到CSV文件（简化版，评分用JSON）"""
    try:
        with file_lock:
            file_exists = os.path.isfile(CSV_FILE)
            
            # 固定最多支持10轮对话的CSV结构
            MAX_CSV_ROUNDS = 10
            
            with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                # ========== 简化的列名设计（固定列）==========
                # 1. 基础信息
                fieldnames = [
                    '测试ID',           # 唯一标识符
                    '测试时间',         # 时间戳
                    '测试日期',         # 日期
                    '角色名称',         # 角色名
                    '角色类型',         # 害羞型/话多型等
                    '角色年龄',         # 年龄
                    '对话轮数',         # 实际轮数
                ]
                
                # 2. 对话内容（使用JSON字符串存储）
                fieldnames.append('对话记录_JSON')
                
                # 3. 评分数据（使用JSON字符串，避免动态列）
                fieldnames.extend([
                    '评分详情_JSON',      # 各项评分（JSON格式）
                    '评分详情_原因_JSON', # 评分原因详情（JSON格式）
                    '评分_平均分',        # 平均分
                    '评分_最高分',        # 最高分
                    '评分_最低分',        # 最低分
                    '评分_标准差',        # 标准差
                    '评分_平均分_孩子',   # 孩子评分平均分
                    '评分_平均分_专家',   # 专家评分平均分
                    '使用的评分标准',     # 标准列表
                    '角色体验评分',       # 角色给出的0-100分体验评分
                ])
                
                # 4. 对话统计
                fieldnames.extend([
                    '总字数_孩子',
                    '总字数_AI',
                    '平均字数_孩子',
                    '平均字数_AI',
                ])
                
                # 5. 评价内容
                fieldnames.extend([
                    '评分理由_总体',
                    '经验教训',
                    '角色自述',
                ])
                
                # 6. 元数据
                fieldnames.extend([
                    '角色完整设定',
                    '开场白',
                ])
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                conversations = test_data.get('conversations', [])
                actual_rounds = len(conversations)
                
                # 生成唯一测试ID（时间戳+角色名）
                timestamp_str = test_data.get('timestamp', datetime.now().strftime('%Y%m%d%H%M%S'))
                test_id = f"{timestamp_str.replace('-', '').replace(':', '').replace(' ', '_')}_{test_data.get('child_name', 'unknown')}"
                
                # 解析日期
                try:
                    test_datetime = datetime.strptime(test_data.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                    test_date = test_datetime.strftime('%Y-%m-%d')
                except:
                    test_date = datetime.now().strftime('%Y-%m-%d')
                
                # 提取角色类型（从性格特点中尝试提取）
                child_type = ''
                traits = test_data.get('child_traits', '')
                # 尝试从Markdown格式中提取类型
                if '害羞' in traits:
                    child_type = '害羞型'
                elif '话多' in traits:
                    child_type = '话多型'
                elif '好奇' in traits:
                    child_type = '好奇型'
                elif '自信' in traits:
                    child_type = '自信型'
                elif '抗拒' in traits:
                    child_type = '抗拒型'
                
                # 基础信息
                row = {
                    '测试ID': test_id,
                    '测试时间': test_data.get('timestamp', ''),
                    '测试日期': test_date,
                    '角色名称': test_data.get('child_name', ''),
                    '角色类型': child_type,
                    '角色年龄': test_data.get('child_age', ''),
                    '对话轮数': actual_rounds,
                }
                
                # 对话内容和字数统计（存储为JSON）
                total_child_chars = 0
                total_ai_chars = 0
                
                conversation_data = []
                for i, conv in enumerate(conversations, 1):
                    child_msg = conv.get('user_message', '')
                    ai_msg = conv.get('ai_response', '')
                    
                    child_chars = len(child_msg)
                    ai_chars = len(ai_msg)
                    
                    total_child_chars += child_chars
                    total_ai_chars += ai_chars
                    
                    conversation_data.append({
                        'round': i,
                        'child_message': child_msg,
                        'ai_response': ai_msg,
                        'child_chars': child_chars,
                        'ai_chars': ai_chars
                    })
                
                row['对话记录_JSON'] = json.dumps(conversation_data, ensure_ascii=False)
                
                # 评分数据（使用JSON字符串，支持双重评分）
                scores = test_data.get('scores', {})
                criteria_names = list(scores.keys())
                row['评分详情_JSON'] = json.dumps(scores, ensure_ascii=False)
                
                # 初始化评分详情字典
                score_details_dict = {}
                
                # 统计指标（支持双重评分）
                if scores:
                    # 提取所有评分值（包括孩子和专家评分）
                    all_score_values = []
                    child_score_values = []
                    expert_score_values = []
                    
                    # 处理双重评分格式
                    dual_scores = scores.get('dual_scores', {})
                    for key, score_data in dual_scores.items():
                        if isinstance(score_data, dict) and 'child_score' in score_data and 'expert_score' in score_data:
                            # 新的双重评分格式
                            child_score = score_data.get('child_score', 0)
                            expert_score = score_data.get('expert_score', 0)
                            if isinstance(child_score, (int, float)) and isinstance(expert_score, (int, float)):
                                child_score_values.append(child_score)
                                expert_score_values.append(expert_score)
                                all_score_values.extend([child_score, expert_score])
                                
                                # 记录评分原因（存储到JSON中，避免字段冲突）
                                score_details_dict[key] = {
                                    'child_score': child_score,
                                    'expert_score': expert_score,
                                    'child_detail': score_data.get('child_detail', ''),
                                    'expert_detail': score_data.get('expert_detail', '')
                                }
                        else:
                            # 兼容旧格式
                            if isinstance(score_data, (int, float)):
                                all_score_values.append(score_data)
                    
                    if all_score_values:
                        avg_score = sum(all_score_values) / len(all_score_values)
                        max_score = max(all_score_values)
                        min_score = min(all_score_values)
                        variance = sum((x - avg_score) ** 2 for x in all_score_values) / len(all_score_values)
                        std_dev = variance ** 0.5
                        
                        row['评分_平均分'] = f"{avg_score:.2f}"
                        row['评分_最高分'] = max_score
                        row['评分_最低分'] = min_score
                        row['评分_标准差'] = f"{std_dev:.2f}"
                        
                        # 如果有双重评分，添加分别的统计
                        if child_score_values and expert_score_values:
                            child_avg = sum(child_score_values) / len(child_score_values)
                            expert_avg = sum(expert_score_values) / len(expert_score_values)
                            row['评分_平均分_孩子'] = f"{child_avg:.2f}"
                            row['评分_平均分_专家'] = f"{expert_avg:.2f}"
                        else:
                            row['评分_平均分_孩子'] = ''
                            row['评分_平均分_专家'] = ''
                    else:
                        row['评分_平均分'] = ''
                        row['评分_最高分'] = ''
                        row['评分_最低分'] = ''
                        row['评分_标准差'] = ''
                        row['评分_平均分_孩子'] = ''
                        row['评分_平均分_专家'] = ''
                else:
                    row['评分_平均分'] = ''
                    row['评分_最高分'] = ''
                    row['评分_最低分'] = ''
                    row['评分_标准差'] = ''
                    row['评分_平均分_孩子'] = ''
                    row['评分_平均分_专家'] = ''
                
                row['使用的评分标准'] = ', '.join(criteria_names)
                row['角色体验评分'] = test_data.get('experience_score', '')
                
                # 对话统计
                row['总字数_孩子'] = total_child_chars
                row['总字数_AI'] = total_ai_chars
                row['平均字数_孩子'] = f"{total_child_chars / actual_rounds:.1f}" if actual_rounds > 0 else '0'
                row['平均字数_AI'] = f"{total_ai_chars / actual_rounds:.1f}" if actual_rounds > 0 else '0'
                
                # 评价内容
                row['评分理由_总体'] = test_data.get('reason', '')
                row['经验教训'] = test_data.get('lessons', '')
                row['角色自述'] = test_data.get('character_review', '')
                
                # 元数据
                row['角色完整设定'] = test_data.get('child_traits', '')
                row['开场白'] = test_data.get('opening', '')
                
                # 保存评分原因详情到JSON
                row['评分详情_原因_JSON'] = json.dumps(score_details_dict, ensure_ascii=False)
                
                writer.writerow(row)
                
        return True
    except Exception as e:
        print(f"保存CSV失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_continuous_test_data(test_data):
    """保存连续测试数据到JSON文件"""
    try:
        with file_lock:
            # 读取现有连续测试数据
            if os.path.isfile(CONTINUOUS_JSON_FILE):
                with open(CONTINUOUS_JSON_FILE, 'r', encoding='utf-8') as f:
                    try:
                        all_data = json.load(f)
                    except json.JSONDecodeError:
                        all_data = []
            else:
                all_data = []
            
            # 生成唯一测试ID
            timestamp_str = test_data.get('timestamp', datetime.now().strftime('%Y%m%d%H%M%S'))
            test_id = f"continuous_{timestamp_str.replace('-', '').replace(':', '').replace(' ', '_')}_{test_data.get('child_name', 'unknown')}"
            
            # 解析日期
            try:
                test_datetime = datetime.strptime(test_data.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                test_date = test_datetime.strftime('%Y-%m-%d')
            except:
                test_date = datetime.now().strftime('%Y-%m-%d')
            
            # 提取角色类型
            child_type = ''
            traits = test_data.get('child_traits', '')
            if '害羞' in traits:
                child_type = '害羞型'
            elif '话多' in traits:
                child_type = '话多型'
            elif '好奇' in traits:
                child_type = '好奇型'
            elif '自信' in traits:
                child_type = '自信型'
            elif '抗拒' in traits:
                child_type = '抗拒型'
            
            # 计算统计数据
            conversations = test_data.get('conversations', [])
            actual_rounds = len(conversations)
            total_child_chars = sum(len(conv.get('user_message', '')) for conv in conversations)
            total_ai_chars = sum(len(conv.get('ai_response', '')) for conv in conversations)
            
            # 计算指标统计
            metrics_history = test_data.get('metrics_history', [])
            if metrics_history:
                interest_scores = [m.get('interest_score', 0) for m in metrics_history]
                attention_scores = [m.get('attention_score', 0) for m in metrics_history]
                experience_scores = [m.get('experience_score', 0) for m in metrics_history]
                
                avg_interest = sum(interest_scores) / len(interest_scores)
                avg_attention = sum(attention_scores) / len(attention_scores)
                avg_experience = sum(experience_scores) / len(experience_scores)
                
                # 计算指标变化趋势
                interest_trend = interest_scores[-1] - interest_scores[0] if len(interest_scores) > 1 else 0
                attention_trend = attention_scores[-1] - attention_scores[0] if len(attention_scores) > 1 else 0
                experience_trend = experience_scores[-1] - experience_scores[0] if len(experience_scores) > 1 else 0
            else:
                avg_interest = avg_attention = avg_experience = 0
                interest_trend = attention_trend = experience_trend = 0
            
            # 构建连续测试记录
            record = {
                'test_id': test_id,
                'timestamp': test_data.get('timestamp', ''),
                'test_date': test_date,
                'child': {
                    'name': test_data.get('child_name', ''),
                    'age': test_data.get('child_age', ''),
                    'type': child_type,
                    'traits': test_data.get('child_traits', ''),
                    'opening': test_data.get('opening', '')
                },
                'conversations': conversations,
                'metrics_history': metrics_history,
                'rounds': actual_rounds,
                'stop_reason': test_data.get('stop_reason', ''),
                'stop_trigger': test_data.get('stop_trigger', ''),
                'thresholds': test_data.get('thresholds', {}),
                'metrics_summary': {
                    'avg_interest': round(avg_interest, 2),
                    'avg_attention': round(avg_attention, 2),
                    'avg_experience': round(avg_experience, 2),
                    'interest_trend': round(interest_trend, 2),
                    'attention_trend': round(attention_trend, 2),
                    'experience_trend': round(experience_trend, 2)
                },
                'statistics': {
                    'total_chars_child': total_child_chars,
                    'total_chars_ai': total_ai_chars,
                    'avg_chars_child': round(total_child_chars / actual_rounds, 1) if actual_rounds > 0 else 0,
                    'avg_chars_ai': round(total_ai_chars / actual_rounds, 1) if actual_rounds > 0 else 0
                }
            }
            
            # 添加到列表
            all_data.append(record)
            
            # 保存JSON文件
            with open(CONTINUOUS_JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        print(f"保存连续测试数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def query_dify_agent(message, conversation_id=None, custom_api_key=None, custom_api_url=None, 
                    custom_inputs=None):
    """
    查询Dify Agent
    
    Args:
        message: 用户消息
        conversation_id: 对话ID（可选）
        custom_api_key: 自定义API密钥（可选）
        custom_api_url: 自定义API URL（可选）
        custom_inputs: 自定义inputs参数字典（可选），例如：
            {
                "user_id_for_test": "user_bear_001",
                "run": "run_123",
                "agent": "memory_test_agent",
                "custom_field": "custom_value"
            }
    """
    session = requests.Session()
    
    try:
        # 使用自定义API密钥和URL，如果没有则使用默认的
        api_key = custom_api_key if custom_api_key else DIFY_API_KEY
        api_url = custom_api_url if custom_api_url else DIFY_API_URL
        
        # 构建inputs参数
        inputs = custom_inputs if custom_inputs else {}
        
        # 添加调试信息
        print(f"🔍 Dify API调试信息:")
        print(f"   URL: {api_url}")
        print(f"   API Key: {api_key[:10]}..." if api_key else "   API Key: None")
        print(f"   Message: {message[:50]}...")
        print(f"   Conversation ID: {conversation_id}")
        print(f"   Custom Inputs: {inputs}")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Connection": "close"
        }
        
        data = {
            "query": message, 
            "user": "test_user",
            "response_mode": "blocking",
            "inputs": inputs,
            "files": []
        }
        
        if USE_CONVERSATION_ID and conversation_id:
            data["conversation_id"] = conversation_id

        print(f"   Request data: {data}")

        response = session.post(
            api_url,
            json=data,
            headers=headers,
            timeout=60
        )
        
        print(f"   Response status: {response.status_code}")
        print(f"   Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Raw response: {result}")
            
            # 处理Dify的工具响应格式
            answer = ""
            conv_id = result.get("conversation_id")
            
            # 检查是否有answer字段（直接回复）
            if "answer" in result:
                answer = result.get("answer", "")
            # 检查是否有message字段（工具响应）
            elif "message" in result:
                message_data = result.get("message", {})
                if isinstance(message_data, dict):
                    answer = message_data.get("answer", "")
            
            print(f"   ✅ Extracted answer: {answer[:50]}...")
            time.sleep(0.3)
            return answer, conv_id
        else:
            print(f"   ❌ Error: {response.status_code} - {response.text}")
            return "", None

    except Exception as e:
        print(f"   ❌ Exception: {str(e)}")
        return "", None
    finally:
        session.close()

def generate_child_response(child, ai_response, round_num, conversation_history=None, custom_api_key=None):
    """生成孩子回应（已迁移到evaluation.py）"""
    return evaluation_engine.generate_child_response(child, ai_response, round_num, conversation_history, custom_api_key)

def evaluate_with_gemini(child_prompt, conversation_history, criteria, custom_api_key=None):
    """使用Gemini进行评测打分（已迁移到evaluation.py）"""
    return evaluation_engine.evaluate_with_gemini(child_prompt, conversation_history, criteria, custom_api_key)


@app.route('/')
def index():
    return render_template('index.html', max_rounds=MAX_ROUNDS)

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/continuous-test')
def continuous_test():
    return render_template('continuous_test.html')

@app.route('/annotation')
def annotation():
    return render_template('annotation.html')


@app.route('/api/preset-children', methods=['GET'])
def get_preset_children():
    """返回内置角色配置"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, 'config', 'preset_children.json')
        
        print(f"🔍 尝试读取文件: {json_path}")
        
        if not os.path.exists(json_path):
            print(f"❌ 文件不存在: {json_path}")
            return jsonify({"error": "配置文件不存在"}), 404
        
        with open(json_path, 'r', encoding='utf-8') as f:
            preset_children = json.load(f)
        
        print(f"✅ 成功加载 {len(preset_children)} 个内置角色")
        return jsonify(preset_children)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        return jsonify({"error": f"JSON格式错误: {str(e)}"}), 500
    except Exception as e:
        print(f"❌ 读取preset_children.json失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/preset-criteria', methods=['GET'])
def get_preset_criteria():
    """返回内置评分标准配置"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, 'config', 'preset_criteria.json')
        
        print(f"🔍 尝试读取评分标准文件: {json_path}")
        
        if not os.path.exists(json_path):
            print(f"❌ 文件不存在: {json_path}")
            return jsonify({"error": "配置文件不存在"}), 404
        
        with open(json_path, 'r', encoding='utf-8') as f:
            preset_criteria = json.load(f)
        
        print(f"✅ 成功加载 {len(preset_criteria)} 个内置评分标准")
        return jsonify(preset_criteria)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        return jsonify({"error": f"JSON格式错误: {str(e)}"}), 500
    except Exception as e:
        print(f"❌ 读取preset_criteria.json失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/test-round', methods=['POST'])
def test_single_round():
    data = request.json
    round_num = data.get('round_num', 1)
    conversation_id = data.get('conversation_id')
    current_message = data.get('message', '')
    custom_dify_key = data.get('dify_api_key')  # 获取自定义Dify API密钥
    custom_dify_url = data.get('dify_api_url')  # 获取自定义Dify API URL
    
    # 获取自定义inputs参数（支持灵活配置）
    custom_inputs = data.get('custom_inputs', {})
    
    # 如果没有custom_inputs，则使用旧的方式构建（向后兼容）
    if not custom_inputs:
        user_id = data.get('user_id', f'test_user_{round_num}')
        run_id = data.get('run_id', f'test_run_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        agent_id = data.get('agent_id', 'test_agent')
        custom_inputs = {
            "user_id_for_test": user_id,
            "run": run_id,
            "agent": agent_id
        }
    
    print(f"[test-round] Round {round_num}, Custom Inputs: {custom_inputs}")
    
    ai_response, new_conversation_id = query_dify_agent(
        current_message, conversation_id, custom_dify_key, custom_dify_url,
        custom_inputs
    )
    
    if not ai_response:
        print(f"[test-round] ❌ AI响应为空")
        return jsonify({
            "success": False,
            "error": "Dify API连接失败",
            "message": f"第{round_num}轮对话失败：Dify API无法返回回复",
            "round": round_num
        }), 500
    
    final_conversation_id = new_conversation_id if new_conversation_id else conversation_id
    
    result = {
        "success": True,
        "round": round_num,
        "user_message": current_message,
        "ai_response": ai_response,
        "conversation_id": final_conversation_id,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return jsonify(result)

@app.route('/api/generate-child-response', methods=['POST'])
def generate_child_response_api():
    data = request.json
    child = data.get('child', {})
    ai_response = data.get('ai_response', '')
    round_num = data.get('round_num', 1)
    conversation_history = data.get('conversation_history', [])
    custom_gemini_key = data.get('gemini_api_key')  # 获取自定义Gemini API密钥
    
    child_response = generate_child_response(child, ai_response, round_num, conversation_history, custom_gemini_key)
    
    return jsonify({
        "success": True,
        "child_response": child_response,
        "round": round_num,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/generate-opening', methods=['POST'])
def generate_opening_api():
    """生成开场白API"""
    data = request.json
    child = data.get('child', {})
    user_id = data.get('user_id', '')
    conversation_history = data.get('conversation_history', [])
    custom_gemini_key = data.get('gemini_api_key')
    
    # 生成开场白
    opening = generate_opening_message(child, user_id, conversation_history, custom_gemini_key)
    
    return jsonify({
        "success": True,
        "opening": opening,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

def generate_opening_message(child, user_id, conversation_history, custom_gemini_key=None):
    """使用Gemini生成开场白，考虑跨session记忆"""
    try:
        from evaluation import EvaluationEngine
        evaluation_engine = EvaluationEngine()
        
        # 构建提示词
        prompt = f"""
你是一个{child.get('age', 5)}岁的中国孩子，名字叫{child.get('name', 'Child')}。
你的性格特点：{child.get('traits', '')}

当前会话信息：
- 用户ID: {user_id}
- 之前的对话历史: {len(conversation_history)}轮对话
- 这是新的对话session

请生成一个开场白，要求：
1. 符合这个孩子的性格和语言水平
2. 如果是第一次对话，自然地开始聊天
3. 如果有之前的对话历史，可以参考之前的对话内容，但不要完全重复
4. 用孩子的语气，简短自然，不超过15个单词
5. 可以中英混杂（符合中国孩子的特点）

请只输出开场白内容，不要添加任何解释。
"""
        
        # 调用Gemini生成开场白
        import os
        from google import genai
        
        api_key = custom_gemini_key if custom_gemini_key else GEMINI_API_KEY
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt]
        )
        
        opening = response.text.strip()
        return opening if opening else child.get('opening', 'Hello!')
        
    except Exception as e:
        print(f"❌ 生成开场白失败: {e}")
        return child.get('opening', 'Hello!')

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    data = request.json
    child = data.get('child', {})
    conversation_history = data.get('conversation_history', [])
    criteria = data.get('criteria', {})
    custom_gemini_key = data.get('gemini_api_key')  # 获取自定义Gemini API密钥
    
    print(f"[DEBUG] 开始评测，对话轮数: {len(conversation_history)}")
    print(f"[DEBUG] 启用的评分标准数量: {len(criteria)}")
    
    eval_result = evaluate_with_gemini(child.get('traits', ''), conversation_history, criteria, custom_gemini_key)
    
    print(f"[DEBUG] 评测结果:")
    print(f"  - scores: {eval_result.get('scores', {})}")
    print(f"  - reason前50字: {eval_result.get('reason', '')[:50]}...")
    print(f"  - lessons前50字: {eval_result.get('lessons', '')[:50]}...")
    print(f"  - character_review前50字: {eval_result.get('character_review', '')[:50]}...")
    print(f"  - experience_score: {eval_result.get('experience_score', 50)}")
    
    response_data = {
        "success": True,
        "scores": eval_result.get("scores", {}),
        "score_details": eval_result.get("score_details", {}),
        "reason": eval_result.get("reason", ""),
        "lessons": eval_result.get("lessons", ""),
        "character_review": eval_result.get("character_review", ""),
        "experience_score": eval_result.get("experience_score", 50),
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    print(f"[DEBUG] 返回给前端的数据keys: {list(response_data.keys())}")
    
    return jsonify(response_data)

@app.route('/api/save-round-result', methods=['POST'])
def save_round_result():
    """实时保存每个Round的评测结果 - 简化直接版本"""
    try:
        print(f"[SAVE] 开始保存", flush=True)
        data = request.json
        print(f"[SAVE] 收到数据: Round {data.get('round_number')}", flush=True)
        
        # 读取现有JSON
        json_file = 'data/test_results.json'
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
            print(f"[SAVE] 已读取JSON，当前测试数: {len(all_data.get('tests', []))}", flush=True)
        except Exception as e:
            print(f"[SAVE] 读取JSON失败，创建新文件: {e}", flush=True)
            all_data = {
                "version": "2.0",
                "description": "AI儿童测试结果存储",
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "last_updated": "",
                "total_tests": 0,
                "tests": []
            }
        
        # 获取或创建test_id
        test_id = data.get('test_id')
        if not test_id:
            child_name = data.get('child', {}).get('name', 'unknown')
            test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{child_name}"
            print(f"[SAVE] 创建新测试ID: {test_id}", flush=True)
        
        # 查找或创建测试记录
        test_record = None
        for test in all_data['tests']:
            if test.get('test_id') == test_id:
                test_record = test
                print(f"[SAVE] 找到现有测试记录", flush=True)
                break
        
        if not test_record:
            test_record = {
                "test_id": test_id,
                "test_type": "multi_session",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "child": data.get('child', {}),
                "rounds": [],
                "summary": {
                    "total_rounds": 0,
                    "total_conversations": 0,
                    "last_updated": ""
                }
            }
            all_data['tests'].append(test_record)
            print(f"[SAVE] 创建新测试记录", flush=True)
        
        # 构建完整的round数据（保存所有信息）
        conversations = data.get('conversations', [])
        scores = data.get('scores', {})
        
        round_record = {
            "round_number": data.get('round_number', 1),
            "session_count": data.get('session_count', 0),
            "timestamp": data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            "saved_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            
            # 完整的对话记录
            "conversations": conversations,
            
            # 对话统计
            "conversation_stats": {
                "total_conversations": len(conversations),
                "total_chars_child": sum(len(c.get('user_message', '')) for c in conversations),
                "total_chars_ai": sum(len(c.get('ai_response', '')) for c in conversations),
                "avg_chars_child": round(sum(len(c.get('user_message', '')) for c in conversations) / len(conversations), 2) if conversations else 0,
                "avg_chars_ai": round(sum(len(c.get('ai_response', '')) for c in conversations) / len(conversations), 2) if conversations else 0
            },
            
            # 完整的评分数据
            "scores": scores,
            "score_details": data.get('score_details', {}),
            
            # 评测分析
            "evaluation": {
                "reason": data.get('reason', ''),
                "lessons": data.get('lessons', ''),
                "character_review": data.get('character_review', ''),
                "experience_score": data.get('experience_score', 50)
            }
        }
        
        # 添加到rounds数组
        test_record['rounds'].append(round_record)
        print(f"[SAVE] 添加Round数据，现在有{len(test_record['rounds'])}个rounds", flush=True)
        
        # 更新测试摘要
        test_record['summary'] = {
            "total_rounds": len(test_record['rounds']),
            "total_conversations": sum(len(r.get('conversations', [])) for r in test_record['rounds']),
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "latest_round_number": round_record['round_number']
        }
        
        # 更新全局统计
        all_data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        all_data['total_tests'] = len(all_data['tests'])
        
        # 保存JSON文件
        print(f"[SAVE] 准备写入文件...", flush=True)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        
        print(f"[SAVE] ✅ 保存成功！Test ID: {test_id}, Round: {round_record['round_number']}", flush=True)
        
        return jsonify({
            "success": True,
            "test_id": test_id,
            "message": f"Round {data.get('round_number')} 数据已保存"
        })
        
    except Exception as e:
        print(f"[SAVE] ❌ 保存失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/save-result', methods=['POST'])
def save_result():
    """保存测试结果到统一数据存储"""
    data = request.json
    
    # 构建统一格式的测试数据
    test_data = {
        'test_type': data.get('test_type', 'normal'),
        'timestamp': data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        'test_date': datetime.now().strftime('%Y-%m-%d'),
        'child': {
            'name': data.get('child', {}).get('name', ''),
            'age': data.get('child', {}).get('age', ''),
            'type': data.get('child', {}).get('type', ''),
            'traits': data.get('child', {}).get('traits', ''),
        'opening': data.get('child', {}).get('opening', ''),
            'user_id': data.get('child', {}).get('user_id', '')
        },
        'conversations': data.get('conversations', []),
        'rounds': len(data.get('conversations', [])),
        'scores': data.get('scores', {}),
        'evaluation': {
        'reason': data.get('reason', ''),
        'lessons': data.get('lessons', ''),
        'character_review': data.get('character_review', ''),
        'experience_score': data.get('experience_score', 50)
        },
        'statistics': {
            'total_chars_child': sum(len(conv.get('user_message', '')) for conv in data.get('conversations', [])),
            'total_chars_ai': sum(len(conv.get('ai_response', '')) for conv in data.get('conversations', [])),
            'avg_chars_child': 0,
            'avg_chars_ai': 0
        },
        'criteria_used': list(data.get('criteria', {}).keys())
    }
    
    # 计算平均字符数
    if test_data['rounds'] > 0:
        test_data['statistics']['avg_chars_child'] = test_data['statistics']['total_chars_child'] / test_data['rounds']
        test_data['statistics']['avg_chars_ai'] = test_data['statistics']['total_chars_ai'] / test_data['rounds']
    
    # 根据测试类型添加特定数据并保存
    test_type = test_data['test_type']
    if test_type == 'multi_session':
        test_data.update({
            'session_count': data.get('session_count', 0),
            'total_rounds': data.get('total_rounds', 0),
            'end_reason': data.get('end_reason', 'normal'),
            'max_rounds_limit': data.get('max_rounds_limit', 0)
        })
        test_id = add_multi_session_test(test_data)
    elif test_type == 'continuous':
        test_data.update({
            'continuous_metrics': data.get('continuous_metrics', {}),
            'stop_reason': data.get('stop_reason', ''),
            'max_rounds': data.get('max_rounds', 0),
            'thresholds': data.get('thresholds', {})
        })
        test_id = add_continuous_test(test_data)
    else:
        test_id = add_normal_test(test_data)
    
    # 同时保存到CSV（保持兼容性）
    csv_success = save_to_csv(test_data)
    
    if test_id:
            return jsonify({
            "success": True,
            "message": f"{test_type}测试结果已保存到统一数据存储",
            "test_id": test_id,
            "csv_saved": csv_success
        })
    else:
            return jsonify({
                "success": False,
            "message": "保存测试结果失败"
        }), 500

# ========== 数据可视化仪表盘 API ==========

@app.route('/api/dashboard/summary', methods=['GET'])
def get_dashboard_summary():
    """获取仪表盘概览数据"""
    try:
        data = get_complete_data()
        tests = data.get("tests", [])
        
        if not tests:
            return jsonify({
                "success": True,
                "data": {
                    "total_tests": 0,
                    "total_normal_tests": 0,
                    "total_continuous_tests": 0,
                    "total_memory_tests": 0,
                    "today_tests": 0,
                    "today_normal_tests": 0,
                    "today_continuous_tests": 0,
                    "today_memory_tests": 0,
                    "total_pass_rate": 0,
                    "normal_pass_rate": 0,
                    "continuous_pass_rate": 0,
                    "memory_pass_rate": 0,
                    "avg_score": 0,
                    "avg_normal_score": 0,
                    "avg_continuous_score": 0,
                    "avg_memory_score": 0,
                    "avg_experience_score": 0,
                    "avg_normal_experience_score": 0,
                    "avg_continuous_experience_score": 0,
                    "avg_memory_experience_score": 0,
                    "total_annotations": 0,
                    "normal_annotations": 0,
                    "continuous_annotations": 0,
                    "memory_annotations": 0
                }
            })
        
        # 分离正常测试、连续测试和记忆测试
        normal_tests = [t for t in tests if t.get('test_type') == 'normal']
        continuous_tests = [t for t in tests if t.get('test_type') == 'continuous']
        memory_tests = [t for t in tests if t.get('test_type') == 'memory']
        
        # 统计数据
        total_tests = len(tests)
        total_normal_tests = len(normal_tests)
        total_continuous_tests = len(continuous_tests)
        total_memory_tests = len(memory_tests)
        
        # 今日测试数
        today = datetime.now().strftime('%Y-%m-%d')
        today_normal_tests = sum(1 for test in normal_tests if test.get('timestamp', '').startswith(today))
        today_continuous_tests = sum(1 for test in continuous_tests if test.get('timestamp', '').startswith(today))
        today_memory_tests = sum(1 for test in memory_tests if test.get('timestamp', '').startswith(today))
        today_tests = today_normal_tests + today_continuous_tests + today_memory_tests
        
        # 计算平均分的辅助函数
        def calculate_avg_score(test_list):
            all_scores = []
            for test in test_list:
                # 判断测试类型
                test_type = test.get('test_type', '')
                
                if test_type == 'multi_session':
                    # 新格式：从rounds数组中提取scores
                    rounds = test.get('rounds', [])
                    for round_data in rounds:
                        scores = round_data.get('scores', {})
                        if scores:
                            # 直接提取分数值（简化版JSON结构）
                            score_values = [v for v in scores.values() if isinstance(v, (int, float))]
                            if score_values:
                                all_scores.append(sum(score_values) / len(score_values))
                else:
                    # normal和continuous测试：旧格式
                    scores = test.get('scores', {})
                    if 'individual' in scores and 'dual_scores' in scores['individual']:
                        # 新格式：计算专家评分的平均值
                        expert_scores = []
                        for criterion_id, score_data in scores['individual']['dual_scores'].items():
                            if isinstance(score_data, dict) and 'expert_score' in score_data:
                                expert_scores.append(score_data['expert_score'])
                        if expert_scores:
                            all_scores.append(sum(expert_scores) / len(expert_scores))
                    elif 'individual' in scores:
                        # 旧格式：使用individual分数
                        individual_scores = scores['individual']
                        if individual_scores:
                            all_scores.append(sum(individual_scores.values()) / len(individual_scores))
            return all_scores
        
        # 计算各类型测试的平均分
        normal_scores = calculate_avg_score(normal_tests)
        continuous_scores = calculate_avg_score(continuous_tests)
        memory_scores = calculate_avg_score(memory_tests)
        all_scores = calculate_avg_score(tests)
        
        avg_normal_score = sum(normal_scores) / len(normal_scores) if normal_scores else 0
        avg_continuous_score = sum(continuous_scores) / len(continuous_scores) if continuous_scores else 0
        avg_memory_score = sum(memory_scores) / len(memory_scores) if memory_scores else 0
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        # 通过率（≥7.0算通过）
        normal_pass_count = sum(1 for score in normal_scores if score >= 7.0)
        continuous_pass_count = sum(1 for score in continuous_scores if score >= 7.0)
        memory_pass_count = sum(1 for score in memory_scores if score >= 7.0)
        total_pass_count = normal_pass_count + continuous_pass_count + memory_pass_count
        
        normal_pass_rate = (normal_pass_count / len(normal_scores) * 100) if normal_scores else 0
        continuous_pass_rate = (continuous_pass_count / len(continuous_scores) * 100) if continuous_scores else 0
        memory_pass_rate = (memory_pass_count / len(memory_scores) * 100) if memory_scores else 0
        total_pass_rate = (total_pass_count / len(all_scores) * 100) if all_scores else 0
        
        # 计算体验评分平均值的辅助函数
        def calculate_experience_score(test_list):
            experience_scores = []
            for test in test_list:
                test_type = test.get('test_type', '')
                
                if test_type == 'multi_session':
                    # 新格式：从rounds数组中提取experience_score
                    rounds = test.get('rounds', [])
                    for round_data in rounds:
                        exp_score = round_data.get('evaluation', {}).get('experience_score', 0)
                        if exp_score > 0:
                            # 将100分制转换为10分制
                            normalized_score = exp_score / 10.0
                            experience_scores.append(normalized_score)
                else:
                    # normal和continuous测试：旧格式
                    exp_score = test.get('evaluation', {}).get('experience_score', 0)
                    if exp_score > 0:
                        # 将100分制转换为10分制
                        normalized_score = exp_score / 10.0
                        experience_scores.append(normalized_score)
            return experience_scores
        
        # 计算各类型测试的体验评分
        normal_experience_scores = calculate_experience_score(normal_tests)
        continuous_experience_scores = calculate_experience_score(continuous_tests)
        memory_experience_scores = calculate_experience_score(memory_tests)
        all_experience_scores = calculate_experience_score(tests)
        
        avg_normal_experience_score = sum(normal_experience_scores) / len(normal_experience_scores) if normal_experience_scores else 0
        avg_continuous_experience_score = sum(continuous_experience_scores) / len(continuous_experience_scores) if continuous_experience_scores else 0
        avg_memory_experience_score = sum(memory_experience_scores) / len(memory_experience_scores) if memory_experience_scores else 0
        avg_experience_score = sum(all_experience_scores) / len(all_experience_scores) if all_experience_scores else 0
        
        # 计算标注数量的辅助函数
        def calculate_annotations(test_list):
            total_annotations = 0
            for test in test_list:
                if 'scores' in test and 'individual' in test['scores'] and 'dual_scores' in test['scores']['individual']:
                    for criterion_id, score_data in test['scores']['individual']['dual_scores'].items():
                        if isinstance(score_data, dict) and score_data.get('annotation', {}).get('annotated', False):
                            total_annotations += 1
            return total_annotations
        
        # 计算各类型测试的标注数量
        normal_annotations = calculate_annotations(normal_tests)
        continuous_annotations = calculate_annotations(continuous_tests)
        memory_annotations = calculate_annotations(memory_tests)
        total_annotations = normal_annotations + continuous_annotations + memory_annotations
        
        return jsonify({
            "success": True,
            "data": {
                "total_tests": total_tests,
                "total_normal_tests": total_normal_tests,
                "total_continuous_tests": total_continuous_tests,
                "total_memory_tests": total_memory_tests,
                "today_tests": today_tests,
                "today_normal_tests": today_normal_tests,
                "today_continuous_tests": today_continuous_tests,
                "today_memory_tests": today_memory_tests,
                "total_pass_rate": round(total_pass_rate, 1),
                "normal_pass_rate": round(normal_pass_rate, 1),
                "continuous_pass_rate": round(continuous_pass_rate, 1),
                "memory_pass_rate": round(memory_pass_rate, 1),
                "avg_score": round(avg_score, 2),
                "avg_normal_score": round(avg_normal_score, 2),
                "avg_continuous_score": round(avg_continuous_score, 2),
                "avg_memory_score": round(avg_memory_score, 2),
                "avg_experience_score": round(avg_experience_score, 2),
                "avg_normal_experience_score": round(avg_normal_experience_score, 2),
                "avg_continuous_experience_score": round(avg_continuous_experience_score, 2),
                "avg_memory_experience_score": round(avg_memory_experience_score, 2),
                "total_annotations": total_annotations,
                "normal_annotations": normal_annotations,
                "continuous_annotations": continuous_annotations,
                "memory_annotations": memory_annotations
            }
        })
    except Exception as e:
        print(f"获取概览数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/dashboard/memory-stats', methods=['GET'])
def get_memory_stats():
    """获取记忆测试专用统计数据（支持multi_session的round级别数据提取）"""
    try:
        data = get_complete_data()
        tests = data.get("tests", [])
        
        # 筛选multi_session测试（记忆测试）
        memory_tests = [t for t in tests if t.get('test_type') == 'multi_session']
        
        if not memory_tests:
            return jsonify({
                "success": True,
                "data": {
                    "total_memory_tests": 0,
                    "total_rounds": 0,
                    "round_data": [],
                    "memory_criteria_stats": {},
                    "memory_by_role": {},
                    "memory_trend": [],
                    "avg_memory_scores": {
                        "factual_memory": 0,
                        "preference_memory": 0,
                        "character_consistency": 0,
                        "learning_progress_memory": 0,
                        "error_correction_memory": 0
                    }
                }
            })
        
        # 🆕 提取每个round的评测数据
        round_data_list = []
        memory_criteria_stats = {
            "factual_memory": {"scores": [], "count": 0},
            "preference_memory": {"scores": [], "count": 0},
            "character_consistency": {"scores": [], "count": 0},
            "learning_progress_memory": {"scores": [], "count": 0},
            "error_correction_memory": {"scores": [], "count": 0}
        }
        
        memory_by_role = {}
        memory_trend = []
        total_rounds = 0
        
        # 记忆指标映射（中文名称 -> 英文key）
        memory_key_mapping = {
            "🧠 记忆能力（Memory Ability）.事实类记忆": "factual_memory",
            "🧠 记忆能力（Memory Ability）.儿童偏好记忆": "preference_memory",
            "🧠 记忆能力（Memory Ability）.人设与世界观一致性": "character_consistency",
            "🧠 记忆能力（Memory Ability）.学习与任务记忆": "learning_progress_memory",
            "🧠 记忆能力（Memory Ability）.误差自纠与更新": "error_correction_memory"
        }
        
        for test in memory_tests:
            role_name = test.get('child', {}).get('name', '未知角色')
            test_id = test.get('test_id', '')
            
            # 🆕 检查是否有rounds数据（兼容新旧格式）
            rounds = test.get('rounds', [])  # 新格式：直接在test层级
            if not rounds:
                # 旧格式：在multi_session_info中
                multi_session_info = test.get('multi_session_info', {})
                rounds = multi_session_info.get('rounds', [])
            
            if rounds:
                # 有round级别数据，提取每个round
                for round_info in rounds:
                    total_rounds += 1
                    
                    round_number = round_info.get('round_number', 0)
                    scores = round_info.get('scores', {})
                    round_timestamp = round_info.get('timestamp', test.get('timestamp', ''))
                    
                    # 提取该round的记忆评分
                    round_memory_scores = {}
                    test_scores_list = []
                    
                    for key, score in scores.items():
                        # 检查是否是记忆相关指标
                        for chinese_key, english_key in memory_key_mapping.items():
                            if chinese_key in key:
                                round_memory_scores[english_key] = score
                                # 提取分数（可能是数字，也可能是字典）
                                if isinstance(score, dict):
                                    expert_score = score.get('expert_score', 0)
                                else:
                                    expert_score = score
                                
                                memory_criteria_stats[english_key]['scores'].append(expert_score)
                                memory_criteria_stats[english_key]['count'] += 1
                                test_scores_list.append(expert_score)
                    
                    # 计算该round的平均分
                    avg_score = sum(test_scores_list) / len(test_scores_list) if test_scores_list else 0
                    
                    round_data_list.append({
                        'test_id': test_id,
                        'round_number': round_number,
                        'role_name': role_name,
                        'timestamp': round_timestamp,
                        'avg_score': round(avg_score, 2),
                        'memory_scores': round_memory_scores,
                        'full_scores': scores
                    })
                    
                    # 添加到角色统计
                    if role_name not in memory_by_role:
                        memory_by_role[role_name] = {
                            'count': 0,
                            'rounds': [],
                            'avg_score': 0,
                            'scores': []
                        }
                    
                    memory_by_role[role_name]['rounds'].append({
                        'round_number': round_number,
                        'avg_score': round(avg_score, 2),
                        'scores': round_memory_scores
                    })
                    memory_by_role[role_name]['count'] += 1
                    memory_by_role[role_name]['scores'].append(avg_score)
                    
                    # 时间趋势
                    if round_timestamp:
                        memory_trend.append({
                            'date': round_timestamp[:10] if len(round_timestamp) >= 10 else test.get('timestamp', '')[:10],
                            'score': round(avg_score, 2),
                            'round_number': round_number,
                            'role_name': role_name
                        })
            else:
                # 没有round级别数据，使用传统方式（兼容旧数据）
                scores = test.get('scores', {})
                
                if isinstance(scores, dict) and 'individual' in scores:
                    individual_scores = scores['individual']
                    
                    for chinese_key, english_key in memory_key_mapping.items():
                        if chinese_key in individual_scores:
                            score_value = individual_scores[chinese_key]
                            if isinstance(score_value, dict):
                                expert_score = score_value.get('expert_score', 0)
                            else:
                                expert_score = score_value
                            
                            memory_criteria_stats[english_key]['scores'].append(expert_score)
                            memory_criteria_stats[english_key]['count'] += 1
        
        # 计算各记忆标准的平均分
        avg_memory_scores = {}
        for criterion_id, stats in memory_criteria_stats.items():
            if stats['scores']:
                avg_memory_scores[criterion_id] = round(sum(stats['scores']) / len(stats['scores']), 2)
            else:
                avg_memory_scores[criterion_id] = 0
        
        # 计算各角色的平均分
        for role_name, stats in memory_by_role.items():
            if stats['scores']:
                stats['avg_score'] = round(sum(stats['scores']) / len(stats['scores']), 2)
            else:
                stats['avg_score'] = 0
        
        return jsonify({
            "success": True,
            "data": {
                "total_memory_tests": len(memory_tests),
                "total_rounds": total_rounds,
                "round_data": round_data_list,  # 🆕 每个round的详细数据
                "memory_criteria_stats": memory_criteria_stats,
                "memory_by_role": memory_by_role,
                "memory_trend": memory_trend,
                "avg_memory_scores": avg_memory_scores
            }
        })
        
    except Exception as e:
        print(f"获取记忆测试统计数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/dashboard/role-stats', methods=['GET'])
def get_role_stats():
    """获取各角色统计数据"""
    try:
        data = get_complete_data()
        tests = data.get("tests", [])
        
        if not tests:
            return jsonify({"success": True, "data": []})
        
        # 分离正常测试和连续测试
        normal_tests = [t for t in tests if t.get('test_type') == 'normal']
        continuous_tests = [t for t in tests if t.get('test_type') == 'continuous']
        
        # 按角色类型统计的辅助函数
        def calculate_role_stats(test_list, test_type):
            role_stats = {}
            for test in test_list:
                role_type = test.get('child', {}).get('type', '未知')
                if role_type not in role_stats:
                    role_stats[role_type] = {
                        'count': 0,
                        'scores': [],
                        'experience_scores': []
                    }
                
                role_stats[role_type]['count'] += 1
                
                # 判断测试类型
                current_test_type = test.get('test_type', '')
                
                if current_test_type == 'multi_session':
                    # 新格式：从rounds数组聚合数据
                    rounds = test.get('rounds', [])
                    for round_data in rounds:
                        # 聚合分数
                        scores = round_data.get('scores', {})
                        if scores:
                            score_values = [v for v in scores.values() if isinstance(v, (int, float))]
                            if score_values:
                                avg_score = sum(score_values) / len(score_values)
                                role_stats[role_type]['scores'].append(avg_score)
                        
                        # 聚合体验分
                        exp_score = round_data.get('evaluation', {}).get('experience_score', 0)
                        if exp_score > 0:
                            normalized_exp_score = exp_score / 10.0
                            role_stats[role_type]['experience_scores'].append(normalized_exp_score)
                else:
                    # normal和continuous测试：旧格式
                    scores = test.get('scores', {})
                    if 'individual' in scores and 'dual_scores' in scores['individual']:
                        expert_scores = []
                        for criterion_id, score_data in scores['individual']['dual_scores'].items():
                            if isinstance(score_data, dict) and 'expert_score' in score_data:
                                expert_scores.append(score_data['expert_score'])
                        if expert_scores:
                            avg_score = sum(expert_scores) / len(expert_scores)
                            role_stats[role_type]['scores'].append(avg_score)
                    elif 'individual' in scores:
                        individual_scores = scores['individual']
                        if isinstance(individual_scores, dict):
                            # 过滤掉非数值的键值对
                            numeric_scores = [v for k, v in individual_scores.items() if isinstance(v, (int, float)) and k != 'dual_scores']
                            if numeric_scores:
                                avg_score = sum(numeric_scores) / len(numeric_scores)
                                role_stats[role_type]['scores'].append(avg_score)
                    
                    # 体验评分（如果有的话，标准化为10分制）
                    exp_score = test.get('evaluation', {}).get('experience_score', 0)
                    if exp_score > 0:
                        # 将100分制转换为10分制
                        normalized_exp_score = exp_score / 10.0
                        role_stats[role_type]['experience_scores'].append(normalized_exp_score)
            
            return role_stats
        
        # 分别计算正常测试和连续测试的角色统计
        normal_role_stats = calculate_role_stats(normal_tests, 'normal')
        continuous_role_stats = calculate_role_stats(continuous_tests, 'continuous')
        all_role_stats = calculate_role_stats(tests, 'all')
        
        # 计算平均值的辅助函数
        def calculate_averages(role_stats, test_type):
            result = []
            for role_type, stats in role_stats.items():
                avg_score = sum(stats['scores']) / len(stats['scores']) if stats['scores'] else 0
                avg_exp = sum(stats['experience_scores']) / len(stats['experience_scores']) if stats['experience_scores'] else 0
                pass_rate = sum(1 for s in stats['scores'] if s >= 7.0) / len(stats['scores']) * 100 if stats['scores'] else 0
                
                result.append({
                    'role_type': role_type,
                    'test_type': test_type,
                    'count': stats['count'],
                    'avg_score': round(avg_score, 2),
                    'avg_experience': round(avg_exp, 1),
                    'pass_rate': round(pass_rate, 1)
                })
            return result
        
        # 分别计算各类型测试的结果
        normal_result = calculate_averages(normal_role_stats, 'normal')
        continuous_result = calculate_averages(continuous_role_stats, 'continuous')
        all_result = calculate_averages(all_role_stats, 'all')
        
        # 合并结果
        result = normal_result + continuous_result + all_result
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        print(f"获取角色统计失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/dashboard/criteria-stats', methods=['GET'])
def get_criteria_stats():
    """获取各指标统计数据"""
    try:
        data = get_complete_data()
        tests = data.get("tests", [])
        
        if not tests:
            return jsonify({"success": True, "data": []})
        
        # 获取所有预设的评分标准
        with open('config/preset_criteria.json', 'r', encoding='utf-8') as f:
            preset_criteria = json.load(f)
        
        # 收集所有子标准，并创建中文名称到ID的映射
        all_criteria = {}
        name_to_id = {}
        for main_criteria in preset_criteria.values():
            if 'sub_criteria' in main_criteria:
                for sub_id, sub_criteria in main_criteria['sub_criteria'].items():
                    all_criteria[sub_id] = {
                        'name': sub_criteria['name'],
                        'weight': sub_criteria.get('weight', 1.0)
                    }
                    # 创建中文名称到ID的映射
                    name_to_id[sub_criteria['name']] = sub_id
                
                # 添加数据中实际使用的旧名称映射
                # 这些是历史数据中使用的名称，需要映射到新的标准
                old_to_new_mapping = {
                    "创意激发能力": "creative_divergent_thinking",
                    "年龄适配度": "cognitive_adaptivity", 
                    "情感支持表达": "encouragement_safety"
                }
                name_to_id.update(old_to_new_mapping)
                
                # 添加新格式的完整名称映射
                # 这些是最新数据中使用的完整名称格式
                new_format_mapping = {
                    "🎈 表达意愿激发（Will to Express）.趣味与互动吸引力": "fun_interaction_attraction",
                    "🎈 表达意愿激发（Will to Express）.鼓励与安全感": "encouragement_safety",
                    "🎈 表达意愿激发（Will to Express）.主动表达引导": "active_expression_guidance",
                    "🧠 英语表达能力培养（Ability to Express in English）.英语用词与句式多样化": "lexical_structural_richness",
                    "🧠 英语表达能力培养（Ability to Express in English）.表达逻辑与结构脚手架": "expression_scaffolding_reasoning",
                    "🧠 英语表达能力培养（Ability to Express in English）.叙事与故事完整性": "storytelling_coherence_structure",
                    "🧠 英语表达能力培养（Ability to Express in English）.思维拓展与创造性表达": "creative_divergent_thinking",
                    "⚙️ 教学自适应性（Adaptive Intelligence）.英语语言难度自适应": "linguistic_adaptivity",
                    "⚙️ 教学自适应性（Adaptive Intelligence）.认知难度自适应": "cognitive_adaptivity",
                    "⚙️ 教学自适应性（Adaptive Intelligence）.教学策略自适应": "strategic_adaptivity_by_scene"
                }
                name_to_id.update(new_format_mapping)
        
        # 统计各指标
        criteria_stats = {}
        for test in tests:
            test_type = test.get('test_type', '')
            
            if test_type == 'multi_session':
                # 新格式：从rounds数组提取scores
                rounds = test.get('rounds', [])
                for round_data in rounds:
                    scores = round_data.get('scores', {})
                    # 简化版JSON：scores直接是 {标准名称: 分数} 的字典
                    for criteria_name, score in scores.items():
                        if isinstance(score, (int, float)):
                            # 将中文名称映射到ID
                            criteria_id = name_to_id.get(criteria_name, criteria_name)
                            if criteria_id not in criteria_stats:
                                criteria_stats[criteria_id] = {
                                    'expert_scores': [],
                                    'child_scores': []
                                }
                            criteria_stats[criteria_id]['expert_scores'].append(score)
            else:
                # normal和continuous测试：旧格式
                scores = test.get('scores', {})
                if 'individual' in scores and 'dual_scores' in scores['individual']:
                    # 新格式1：双重评分在individual下
                    for criteria_name, score_data in scores['individual']['dual_scores'].items():
                        if isinstance(score_data, dict) and 'expert_score' in score_data:
                            # 将中文名称映射到ID
                            criteria_id = name_to_id.get(criteria_name, criteria_name)
                            if criteria_id not in criteria_stats:
                                criteria_stats[criteria_id] = {
                                    'expert_scores': [],
                                    'child_scores': []
                                }
                            criteria_stats[criteria_id]['expert_scores'].append(score_data['expert_score'])
                            if 'child_score' in score_data:
                                criteria_stats[criteria_id]['child_scores'].append(score_data['child_score'])
                elif 'dual_scores' in scores:
                    # 新格式2：双重评分直接在scores下
                    for criteria_name, score_data in scores['dual_scores'].items():
                        if isinstance(score_data, dict) and 'expert_score' in score_data:
                            # 将中文名称映射到ID
                            criteria_id = name_to_id.get(criteria_name, criteria_name)
                            if criteria_id not in criteria_stats:
                                criteria_stats[criteria_id] = {
                                    'expert_scores': [],
                                    'child_scores': []
                                }
                            criteria_stats[criteria_id]['expert_scores'].append(score_data['expert_score'])
                            if 'child_score' in score_data:
                                criteria_stats[criteria_id]['child_scores'].append(score_data['child_score'])
                elif 'individual' in scores:
                    # 旧格式：使用individual分数
                    individual_scores = scores['individual']
                    for criteria_name, score in individual_scores.items():
                        # 将中文名称映射到ID
                        criteria_id = name_to_id.get(criteria_name, criteria_name)
                        if criteria_id not in criteria_stats:
                            criteria_stats[criteria_id] = {
                                'expert_scores': [],
                                'child_scores': []
                            }
                        criteria_stats[criteria_id]['expert_scores'].append(score)
        
        # 计算平均值，包含所有预设标准
        result = []
        for criteria_id, criteria_info in all_criteria.items():
            if criteria_id in criteria_stats:
                scores = criteria_stats[criteria_id]
                expert_avg = sum(scores['expert_scores']) / len(scores['expert_scores']) if scores['expert_scores'] else 0
                child_avg = sum(scores['child_scores']) / len(scores['child_scores']) if scores['child_scores'] else expert_avg
                count = len(scores['expert_scores'])
            else:
                expert_avg = 0
                child_avg = 0
                count = 0
            
            result.append({
                'criteria': criteria_info['name'],
                'criteria_id': criteria_id,
                'avg_score': round(expert_avg, 2),
                'expert_score': round(expert_avg, 2),
                'child_score': round(child_avg, 2),
                'count': count,
                'weight': criteria_info['weight']
            })
        
        # 按平均分排序
        result.sort(key=lambda x: x['avg_score'], reverse=True)
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        print(f"获取指标统计失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/dashboard/trend', methods=['GET'])
def get_trend_data():
    """获取趋势数据"""
    try:
        data = get_complete_data()
        tests = data.get("tests", [])
        
        if not tests:
            return jsonify({"success": True, "data": []})
        
        # 按日期统计
        daily_stats = {}
        for test in tests:
            test_type = test.get('test_type', '')
            timestamp = test.get('timestamp', '')
            if not timestamp:
                continue
            
            # 提取日期部分
            test_date = timestamp.split(' ')[0] if ' ' in timestamp else timestamp[:10]
            
            if test_date not in daily_stats:
                daily_stats[test_date] = {
                    'count': 0,
                    'scores': [],
                    'experience_scores': []
                }
            
            daily_stats[test_date]['count'] += 1
            
            if test_type == 'multi_session':
                # 新格式：从rounds数组聚合数据
                rounds = test.get('rounds', [])
                for round_data in rounds:
                    # 聚合分数
                    scores = round_data.get('scores', {})
                    if scores:
                        score_values = [v for v in scores.values() if isinstance(v, (int, float))]
                        if score_values:
                            avg_score = sum(score_values) / len(score_values)
                            daily_stats[test_date]['scores'].append(avg_score)
                    
                    # 聚合体验分
                    exp_score = round_data.get('evaluation', {}).get('experience_score', 0)
                    if exp_score > 0:
                        normalized_exp_score = exp_score / 10.0
                        daily_stats[test_date]['experience_scores'].append(normalized_exp_score)
            else:
                # normal和continuous测试：旧格式
                scores = test.get('scores', {})
                if 'individual' in scores and 'dual_scores' in scores['individual']:
                    expert_scores = []
                    for criterion_id, score_data in scores['individual']['dual_scores'].items():
                        if isinstance(score_data, dict) and 'expert_score' in score_data:
                            expert_scores.append(score_data['expert_score'])
                    if expert_scores:
                        avg_score = sum(expert_scores) / len(expert_scores)
                        daily_stats[test_date]['scores'].append(avg_score)
                elif 'individual' in scores:
                    individual_scores = scores['individual']
                    if individual_scores:
                        avg_score = sum(individual_scores.values()) / len(individual_scores)
                        daily_stats[test_date]['scores'].append(avg_score)
                
                # 体验评分（如果有的话，标准化为10分制）
                exp_score = test.get('evaluation', {}).get('experience_score', 0)
                if exp_score > 0:
                    # 将100分制转换为10分制
                    normalized_exp_score = exp_score / 10.0
                    daily_stats[test_date]['experience_scores'].append(normalized_exp_score)
        
        # 计算每日平均值
        result = []
        for date, stats in sorted(daily_stats.items()):
            avg_score = sum(stats['scores']) / len(stats['scores']) if stats['scores'] else 0
            avg_exp = sum(stats['experience_scores']) / len(stats['experience_scores']) if stats['experience_scores'] else 0
            
            result.append({
                'date': date,
                'count': stats['count'],
                'avg_score': round(avg_score, 2),
                'avg_experience': round(avg_exp, 1)
            })
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        print(f"获取趋势数据失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/dashboard/recent-tests', methods=['GET'])
def get_recent_tests():
    """获取最近的测试记录"""
    try:
        limit = int(request.args.get('limit', 10))
        
        data = get_complete_data()
        tests = data.get("tests", [])
        
        if not tests:
            return jsonify({"success": True, "data": []})
        
        # 按时间戳排序，取最近的
        sorted_data = sorted(tests, key=lambda x: x.get('timestamp', ''), reverse=True)
        recent_tests = sorted_data[:limit]
        
        # 提取关键信息
        result = []
        for test in recent_tests:
            test_type = test.get('test_type', '')
            avg_score = 0
            expert_score = 0
            child_score = 0
            experience_score = 0
            rounds_count = 0
            
            if test_type == 'multi_session':
                # 新格式：从rounds数组聚合数据
                rounds = test.get('rounds', [])
                rounds_count = len(rounds)
                
                if rounds:
                    all_scores = []
                    all_exp_scores = []
                    
                    for round_data in rounds:
                        # 聚合分数
                        scores = round_data.get('scores', {})
                        if scores:
                            score_values = [v for v in scores.values() if isinstance(v, (int, float))]
                            if score_values:
                                all_scores.append(sum(score_values) / len(score_values))
                        
                        # 聚合体验分
                        exp = round_data.get('evaluation', {}).get('experience_score', 0)
                        if exp > 0:
                            all_exp_scores.append(exp)
                    
                    if all_scores:
                        avg_score = sum(all_scores) / len(all_scores)
                        expert_score = avg_score
                        child_score = avg_score
                    
                    if all_exp_scores:
                        experience_score = sum(all_exp_scores) / len(all_exp_scores)
            else:
                # normal和continuous测试：旧格式
                scores = test.get('scores', {})
                
                if 'individual' in scores and 'dual_scores' in scores['individual']:
                    expert_scores = []
                    child_scores = []
                    for criterion_id, score_data in scores['individual']['dual_scores'].items():
                        if isinstance(score_data, dict):
                            if 'expert_score' in score_data:
                                expert_scores.append(score_data['expert_score'])
                            if 'child_score' in score_data:
                                child_scores.append(score_data['child_score'])
                    if expert_scores:
                        expert_score = sum(expert_scores) / len(expert_scores)
                        avg_score = expert_score
                    if child_scores:
                        child_score = sum(child_scores) / len(child_scores)
                elif 'individual' in scores:
                    individual_scores = scores['individual']
                    if individual_scores:
                        avg_score = sum(individual_scores.values()) / len(individual_scores)
                        expert_score = avg_score
                        child_score = avg_score
                
                experience_score = test.get('evaluation', {}).get('experience_score', 0)
                rounds_count = test.get('rounds', 0)
            
            result.append({
                'test_id': test.get('test_id', ''),
                'timestamp': test.get('timestamp', ''),
                'child_name': test.get('child', {}).get('name', ''),
                'child_type': test.get('child', {}).get('type', ''),
                'avg_score': round(avg_score, 2),
                'expert_score': round(expert_score, 2),
                'child_score': round(child_score, 2),
                'experience_score': round(experience_score, 2) if experience_score else 0,
                'rounds': rounds_count,
                'passed': avg_score >= 7.0
            })
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        print(f"获取最近测试失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# ========== 连续测试功能 ==========

def generate_continuous_child_response(child, ai_response, round_num, conversation_history, custom_api_key=None):
    """生成连续测试中的孩子回应，包含三个指标分数（已迁移到evaluation.py）"""
    return evaluation_engine.generate_continuous_child_response(child, ai_response, round_num, conversation_history, custom_api_key)

@app.route('/api/continuous-test/round', methods=['POST'])
def continuous_test_round():
    """连续测试的单轮对话"""
    data = request.json
    child = data.get('child', {})
    ai_response = data.get('ai_response', '')
    round_num = data.get('round_num', 1)
    conversation_history = data.get('conversation_history', [])
    custom_gemini_key = data.get('gemini_api_key')
    
    # 生成孩子回应和三个指标分数
    child_result = generate_continuous_child_response(child, ai_response, round_num, conversation_history, custom_gemini_key)
    
    return jsonify({
        "success": True,
        "child_response": child_result["child_response"],
        "interest_score": child_result["interest_score"],
        "attention_score": child_result["attention_score"],
        "experience_score": child_result["experience_score"],
        "round": round_num,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/continuous-test/stop-reason', methods=['POST'])
def generate_stop_reason():
    """生成停止对话的原因"""
    data = request.json
    child = data.get('child', {})
    conversation_history = data.get('conversation_history', [])
    stop_trigger = data.get('stop_trigger', '')  # 哪个指标触发了停止
    custom_gemini_key = data.get('gemini_api_key')
    
    stop_reason = evaluation_engine.generate_stop_reason(child, conversation_history, stop_trigger, custom_gemini_key)
    
    return jsonify({
        "success": True,
        "stop_reason": stop_reason
    })

@app.route('/api/continuous-test/metric-reason', methods=['POST'])
def generate_metric_reason():
    """生成孩子视角和专家视角的指标变化理由"""
    data = request.json
    child = data.get('child', {})
    round_num = data.get('round_num', 1)
    metric_type = data.get('metric_type', '')  # interest, attention, experience
    metric_value = data.get('metric_value', 0)
    previous_value = data.get('previous_value', 0)
    conversation = data.get('conversation', {})
    custom_gemini_key = data.get('gemini_api_key')
    
    result = evaluation_engine.generate_metric_reason(
        child, round_num, metric_type, metric_value, previous_value, conversation, custom_gemini_key
    )
    
    return jsonify({
        "success": True,
        "child_reason": result["child_reason"],
        "expert_reason": result["expert_reason"]
    })

@app.route('/api/continuous-test/save', methods=['POST'])
def save_continuous_test():
    """保存连续测试数据"""
    data = request.json
    
    test_data = {
        'timestamp': data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        'child_name': data.get('child', {}).get('name', ''),
        'child_age': data.get('child', {}).get('age', ''),
        'child_traits': data.get('child', {}).get('traits', ''),
        'opening': data.get('child', {}).get('opening', ''),
        'conversations': data.get('conversations', []),
        'metrics_history': data.get('metrics_history', []),
        'stop_reason': data.get('stop_reason', ''),
        'stop_trigger': data.get('stop_trigger', ''),
        'thresholds': data.get('thresholds', {})
    }
    
    # 保存到完整数据存储
    test_id = add_continuous_test(test_data)
    
    if test_id:
        return jsonify({
            "success": True,
            "message": "连续测试数据已保存",
            "test_id": test_id
        })
    else:
        return jsonify({
            "success": False,
            "message": "保存连续测试数据失败"
        }), 500

# 标注训练相关API
@app.route('/api/annotations', methods=['GET'])
def get_annotations():
    """获取标注数据"""
    try:
        # 从统一数据中生成标注数据
        annotations = get_annotation_data()
        return jsonify({'annotations': annotations})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/annotations', methods=['POST'])
def save_annotation():
    """保存标注数据"""
    try:
        data = request.json
        annotation_id = data.get('id')
        annotation_data = {
            'expert_accuracy': data.get('expert_accuracy'),
            'expert_quality': data.get('expert_quality'),
            'suggested_score': data.get('suggested_score'),
            'feedback': data.get('feedback'),
            'annotated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 保存到统一数据管理
        add_annotation(annotation_id, annotation_data)
        
        return jsonify({'success': True, 'message': '标注保存成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/train-model', methods=['POST'])
def train_model():
    """训练专家评分模型"""
    try:
        data = request.json
        annotations = data.get('annotations', [])
        
        # 过滤出已标注的数据
        annotated_data = [a for a in annotations if a.get('annotated', False)]
        
        if not annotated_data:
            return jsonify({
                'success': False, 
                'message': '没有找到已标注的数据，请先完成一些标注'
            })
        
        # 分析标注数据，生成改进建议
        improvements = analyze_annotations(annotated_data)
        
        # 更新专家prompt
        update_expert_prompts(improvements)
        
        return jsonify({
            'success': True, 
            'message': f'模型训练完成！分析了 {len(annotated_data)} 条标注数据',
            'improvements': improvements,
            'analyzed_count': len(annotated_data)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
