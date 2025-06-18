# pip install openai gspread google-auth rapidfuzz
import base64
from openai import OpenAI
import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
import json
import os
import re
from rapidfuzz import process, fuzz
from datetime import datetime

# --- 시스템 메시지 정의 (초기화에 사용되므로 먼저 정의) ---
system_message_content = """
당신은 친절하고 도움이 되는 수술실 간호사의 AI 어시스턴트입니다.
긴급한 상황에서도 바로 보고 따라할 수 있도록 최대한 간결하게 답변해주세요.
이 챗봇을 사용하는 대상자는 수술실 간호사입니다. 표와 그림을 참고하여 답변해주세요.
한국어로 답변해주세요.
"""

# --- 세션 상태 변수들을 코드의 상단에서 미리 초기화 ---
# 로그인 상태 관리
if "login" not in st.session_state:
    st.session_state["login"] = False

# Perplexity 모델 초기화
if "perplexity_model" not in st.session_state:
    st.session_state["perplexity_model"] = "sonar-pro"

# 채팅 기록 관련 세션 상태 변수 초기화
if "chat_logs" not in st.session_state:
    st.session_state["chat_logs"] = {} # 모든 채팅 기록을 저장할 딕셔너리

if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None # 현재 보고 있는 채팅의 ID

# 메시지 리스트 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": system_message_content}
    ]
# 안내 문구 표시 여부 플래그 추가
if "show_guidelines" not in st.session_state:
    st.session_state.show_guidelines = True

# --- 동의어 사전 정의 ---
SYNONYM_MAP = {
    "수술 준비": ["수술 세팅", "수술준비", "수술세팅", "세팅", "준비"],
    "장비": ["기구", "물품"],
    "방법": ["과정", "절차"],
    "TUC": ["경요도", "요도절제술"],
    "사용하는": ["필요한", "필요한 장비", "필요한 물품", "필요한 기구", "필요한 것", "사용하는 장비"]
}

# --- 쿼리 확장 함수 ---
def expand_query_with_synonyms(query):
    expanded_queries = [query]
    for main_term, synonyms in SYNONYM_MAP.items():
        if main_term in query:
            for syn in synonyms:
                if syn not in query:
                    expanded_queries.append(query.replace(main_term, syn))
        for syn in synonyms:
            if syn in query:
                if main_term not in query:
                    expanded_queries.append(query.replace(syn, main_term))
                for other_syn in [s for s in synonyms if s != syn]:
                    if other_syn not in query:
                        expanded_queries.append(query.replace(syn, other_syn))
    return list(set(expanded_queries))

# --- 이미지 Base64 인코딩 함수 (중복 코드를 줄이기 위해) ---
@st.cache_data
def get_ori_icon_base64():
    try:
        with open("ori_icon.png", "rb") as f:
            image_bytes = f.read()
            return base64.b64encode(image_bytes).decode()
    except FileNotFoundError:
        st.warning("ori_icon.png 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
        return None

# --- 제목 및 아이콘 렌더링 함수 ---
def render_title_and_icon(is_clickable=False): # is_clickable은 더 이상 실제 클릭 기능을 제어하지 않지만, 호출 형식 유지를 위해 남겨둡니다.
    col1_main, col2_main, col3_main = st.columns([0.5, 3, 0.5])

    with col2_main:
        st.markdown("<h1 style='text-align: center; display: block; width: 100%; margin-bottom: 0px;'>나만의 스크럽 메이트 ORi</h1>", unsafe_allow_html=True)
        
        encoded_image = get_ori_icon_base64()
        if encoded_image:
            # is_clickable 값과 관계없이 항상 이미지만 렌더링하고, 링크를 제거합니다.
            st.markdown(
                f"<p style='text-align: center; width: 100%; margin-top: 5px;'><img src='data:image/png;base64,{encoded_image}' width='100'></p>",
                unsafe_allow_html=True
            )

def login():
    render_title_and_icon(is_clickable=False) # 로그인 화면에서는 클릭 불가 (어차피 이제 클릭 기능 없음)

    st.subheader("로그인")
    user_id = st.text_input("아이디")
    user_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        if user_id == "ori" and user_pw == "0":
            st.session_state["login"] = True
            st.success("로그인 성공!")
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

# --- 앱 시작 시 쿼리 파라미터 처리 (아이콘 클릭 시 새 채팅) ---
# ORi 아이콘 클릭 시 화면 전환 기능을 제거했으므로, 이 쿼리 파라미터 처리 로직은 더 이상 필요 없습니다.
# 기존 코드를 주석 처리하거나 삭제합니다.
# if "action" in st.query_params and st.query_params["action"] == "new_chat":
#     del st.query_params["action"]
#     if st.session_state["login"]:
#         start_new_chat()
#     else:
#         st.rerun()


if not st.session_state["login"]:
    login()
    st.stop()

def extract_image_url(text):
    return None

def extract_core_summary(answer):
    return answer.split('\n')[0].strip()

# --- [수정된 제목 및 아이콘 가운데 정렬 부분 시작] ---
# 로그인 후 메인 앱 화면에서는 아이콘을 클릭 가능하게 렌더링 -> 이제 클릭 불가능
render_title_and_icon(is_clickable=False) # 아이콘은 있지만 클릭 기능 없음
# --- [수정된 제목 및 아이콘 가운데 정렬 부분 끝] ---

# 챗봇 사용 가이드라인 표시
if st.session_state.show_guidelines and len(st.session_state.messages) == 1:
    st.markdown("---")
    st.subheader("🏥 ORi 사용법")
    st.markdown("##### **수술실 준비와 장비 배치 정보를 빠르게 제공합니다!**")
    st.markdown("---")
    col1_guide, col2_guide = st.columns(2)

    with col1_guide:
        st.markdown("##### 💡 이렇게 질문하세요")
        st.info("• 37번방 TUC 수술 세팅 방법")
        st.info("• TUC 수술 필요 장비")

    with col2_guide:
        st.markdown("##### ✨ 이런 답변을 받아요")
        st.success("• 핵심 정보 요약")
        st.success("• 관련 이미지/표 제공")

    st.markdown("---")
    st.markdown("##### 💬 궁금한 점을 편하게 물어보세요!")
    st.warning("⚠️ **ORi는 참고용 정보입니다.** 실제 업무 시 병원 프로토콜을 우선 따르세요!")
    st.markdown("---")

@st.cache_data
def load_google_sheet_data():
    try:
        if not os.path.exists('service_key.json'):
            st.warning("⚠️ service_key.json 파일이 없습니다. 구글 시트 데이터 없이 실행됩니다.")
            return None
        credentials = service_account.Credentials.from_service_account_file(
            'service_key.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive']
        )
        gc = gspread.authorize(credentials)
        sheet_url = "https://docs.google.com/spreadsheets/d/11DUuktRmn1UlchUbeytQAsxC9RaHmL-PW-6480vXYSo/edit?gid=0#gid=0"
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
        sh = gc.open_by_key(sheet_id)
        worksheet = sh.worksheet('Sheet1')
        data = worksheet.get_all_values()
        if len(data) < 2:
            st.warning("구글 시트에 데이터가 없습니다. 시트에 '질문', '답변', 'Image URL' 컬럼을 포함해 데이터를 입력해 주세요.")
            return None
        df = pd.DataFrame(data[1:], columns=data[0])

        expanded_questions = []
        expanded_answers = []
        expanded_image_urls = []

        for index, row in df.iterrows():
            question_cell = str(row['질문'])
            answer_cell = row['답변']
            image_url_cell = row['Image URL'] if 'Image URL' in df.columns else None

            for q in question_cell.split(','):
                q_stripped = q.strip()
                if q_stripped:
                    expanded_questions.append(q_stripped)
                    expanded_answers.append(answer_cell)
                    expanded_image_urls.append(image_url_cell)
        
        return {
            'questions': expanded_questions,
            'answers': expanded_answers,
            'image_urls': expanded_image_urls
        }

    except FileNotFoundError:
        st.error("❌ service_key.json 파일을 찾을 수 없습니다.")
        st.info("📝 README.md 파일을 참고하여 구글 서비스 계정 키를 설정해주세요.")
        return None
    except Exception as e:
        st.error(f"❌ 구글 시트 연결 오류: {str(e)}")
        st.info("📝 구글 시트가 서비스 계정과 공유되어 있는지 확인해주세요.")
        return None

sheet_data_loaded = load_google_sheet_data()

questions = []
answers = []
image_urls = []

if sheet_data_loaded is not None:
    questions = sheet_data_loaded['questions']
    answers = sheet_data_loaded['answers']
    image_urls = sheet_data_loaded['image_urls']
    if not questions:
        st.info("ℹ️ 구글 시트에 등록된 질문이 없습니다. 시트에 질문/답변 데이터를 추가해 주세요.")
else:
    st.info("ℹ️ 구글 시트 데이터 로드에 실패했습니다. 위의 오류 메시지를 확인해 주세요.")


if "PERPLEXITY_API_KEY" not in st.secrets:
    st.error("❌ PERPLEXITY_API_KEY가 설정되지 않았습니다.")
    st.info("📝 .streamlit/secrets.toml 파일에 API 키를 추가해주세요.")
    st.stop()

client = OpenAI(
    api_key=st.secrets["PERPLEXITY_API_KEY"],
    base_url="https://api.perplexity.ai"
)

def find_best_match(user_input, questions, threshold=65):
    if not questions:
        return None, 0, -1
    result = process.extractOne(user_input, questions, scorer=fuzz.ratio)
    if result and result[1] >= threshold:
        return result[0], result[1], result[2]
    return None, result[1] if result else 0, result[2] if result else -1

# 새 대화 시작 함수 (기존 로직 유지)
def start_new_chat():
    if len(st.session_state.messages) > 1:
        if st.session_state.current_chat_id in st.session_state.chat_logs:
            st.session_state.chat_logs[st.session_state.current_chat_id]["messages"] = st.session_state.messages[1:]
        else:
            if st.session_state.current_chat_id is None:
                new_chat_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            else:
                new_chat_id = st.session_state.current_chat_id
            
            first_user_message = next((m for m in st.session_state.messages if m["role"] == "user"), None)
            log_title = first_user_message["content"] if first_user_message else "새 대화"
            log_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            st.session_state.chat_logs[new_chat_id] = {
                "title": log_title,
                "datetime": log_datetime,
                "messages": st.session_state.messages[1:]
            }

    st.session_state.messages = [
        {"role": "system", "content": system_message_content}
    ]
    st.session_state.current_chat_id = None
    st.session_state.show_guidelines = True
    st.rerun()

# 특정 채팅 로드 함수 (기존 로직 유지)
def load_chat_log(chat_id):
    if st.session_state.current_chat_id and st.session_state.current_chat_id != chat_id:
        if len(st.session_state.messages) > 1:
            if st.session_state.current_chat_id not in st.session_state.chat_logs:
                first_user_message = next((m for m in st.session_state.messages if m["role"] == "user"), None)
                log_title = first_user_message["content"] if first_user_message else "새 대화"
                log_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.chat_logs[st.session_state.current_chat_id] = {
                    "title": log_title,
                    "datetime": log_datetime,
                    "messages": st.session_state.messages[1:]
                }
            else:
                st.session_state.chat_logs[st.session_state.current_chat_id]["messages"] = st.session_state.messages[1:]

    loaded_log = st.session_state.chat_logs.get(chat_id)
    if loaded_log:
        st.session_state.messages = [
            {"role": "system", "content": system_message_content}
        ] + loaded_log["messages"]
        st.session_state.current_chat_id = chat_id
        st.session_state.show_guidelines = False
    st.rerun()

# --- [사이드바 구현] ---
with st.sidebar:
    st.header("나의 채팅 기록")
    
    # "새 채팅" 버튼은 그대로 유지하여 사이드바를 통해 새 채팅 시작
    if st.button("새 채팅", key="new_chat_button"):
        start_new_chat()

    st.markdown("---")

    if st.session_state.chat_logs:
        sorted_chat_logs = sorted(
            st.session_state.chat_logs.items(),
            key=lambda item: datetime.strptime(item[1]["datetime"], "%Y-%m-%d %H:%M:%S"),
            reverse=True
        )

        for chat_id, log_data in sorted_chat_logs:
            col1_log, col2_log = st.columns([0.8, 0.2])
            with col1_log:
                formatted_datetime = datetime.strptime(log_data['datetime'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d\n%H:%M")
                button_label = f"{log_data['title']}\n{formatted_datetime}"
                
                if st.button(
                    button_label, 
                    key=f"chat_select_{chat_id}", 
                    use_container_width=True,
                    help="클릭하여 이 대화 기록을 불러옵니다."
                ):
                    load_chat_log(chat_id)

            with col2_log:
                if st.button("🗑️", key=f"delete_{chat_id}", help="이 대화 기록을 삭제합니다."):
                    del st.session_state.chat_logs[chat_id]
                    if st.session_state.current_chat_id == chat_id:
                        start_new_chat()
                    else:
                        st.rerun()
            st.markdown("---")
    else:
        st.info("저장된 채팅 기록이 없습니다.")

    st.markdown("---")

    if st.button("로그아웃", key="logout_button", help="현재 세션을 종료하고 로그인 화면으로 돌아갑니다."):
        st.session_state["login"] = False
        st.session_state.clear()
        st.rerun()

# --- [기존 대화 출력 로직 유지] ---
for message in st.session_state.messages:
    if message["role"] == "system":
        continue
    
    avatar_icon = "ori_icon.png" if message["role"] == "assistant" else "user"
    
    with st.chat_message(message["role"], avatar=avatar_icon):
        if "image_url" in message and message["image_url"]:
            local_image_path = os.path.join("images", message["image_url"])
            if os.path.exists(local_image_path):
                st.image(local_image_path, caption="수술방 장비 세팅 예시", use_container_width=True)
            else:
                st.warning(f"이미지 파일을 찾을 수 없습니다: {message['image_url']}")
        st.markdown(message["content"])

# --- [유저 입력 처리 로직 유지] ---
if prompt := st.chat_input("어떤 수술 준비를 도와드릴까요?"):
    st.session_state.show_guidelines = False

    if st.session_state.current_chat_id is None:
        chat_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        st.session_state.current_chat_id = chat_id
        st.session_state.chat_logs[chat_id] = {
            "title": prompt,
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "messages": []
        }

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.chat_logs[st.session_state.current_chat_id]["messages"].append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    if not questions:
        response_content = "질문 데이터가 없습니다. 구글 시트에 질문/답변을 입력해 주세요."
        with st.chat_message("assistant", avatar="ori_icon.png"):
            st.warning(response_content)
        
        st.session_state.messages.append({
            "role": "assistant",
            "content": response_content,
            "image_url": None
        })
        st.session_state.chat_logs[st.session_state.current_chat_id]["messages"].append({
            "role": "assistant",
            "content": response_content,
            "image_url": None
        })

    else:
        expanded_prompts = expand_query_with_synonyms(prompt)
        
        best_match = None
        score = 0
        idx = -1
        
        for current_prompt_candidate in expanded_prompts:
            temp_match, temp_score, temp_idx = find_best_match(current_prompt_candidate, questions)
            if temp_score > score:
                best_match = temp_match
                score = temp_score
                idx = temp_idx

        if best_match is not None and idx != -1:
            answer_from_sheet = answers[idx]
            current_image_file_name = image_urls[idx] if idx < len(image_urls) else None
            
            messages_for_perplexity = [
                {"role": "system", "content": f"다음은 수술실 관련 질문에 대한 정보입니다. 이 정보를 바탕으로 사용자 질문에 핵심만 간결하게 요약해서 답변하세요. 필요하다면 번호 매기기와 아이콘과 표를 사용하세요. 불필요한 설명은 생략하세요. \n\n정보: {answer_from_sheet}"},
                {"role": "user", "content": prompt}
            ]
            
            stream = client.chat.completions.create(
                model=st.session_state["perplexity_model"],
                messages=messages_for_perplexity,
                stream=True,
            )
            
            response_from_perplexity = ""
            with st.chat_message("assistant", avatar="ori_icon.png"):
                if current_image_file_name:
                    local_image_path = os.path.join("images", current_image_file_name)
                    if os.path.exists(local_image_path):
                        st.image(local_image_path, caption="수술방 장비 세팅 예시", use_container_width=True)
                    else:
                        st.warning(f"이미지 파일을 찾을 수 없습니다: {current_image_file_name}")
                
                message_placeholder = st.empty()
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        response_from_perplexity += chunk.choices[0].delta.content
                        message_placeholder.markdown(response_from_perplexity + "▌")
                
                message_placeholder.markdown(response_from_perplexity)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": response_from_perplexity,
                "image_url": current_image_file_name
            })
            st.session_state.chat_logs[st.session_state.current_chat_id]["messages"].append({
                "role": "assistant",
                "content": response_from_perplexity,
                "image_url": current_image_file_name
            })

        else:
            response_content = (
                "죄송합니다. 해당 정보를 찾을 수 없습니다.\n"
                "다른 질문이 있으신가요? \n"
                "예시) 37번방 tuc 수술 준비 방법 알려주세요."
            )
            with st.chat_message("assistant", avatar="ori_icon.png"):
                st.markdown(response_content)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": response_content,
                "image_url": None
            })
            st.session_state.chat_logs[st.session_state.current_chat_id]["messages"].append({
                "role": "assistant",
                "content": response_content,
                "image_url": None
            })