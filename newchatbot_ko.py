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
    "TUC": ["Tuc","tuc", "경요도", "요도절제술"],
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
        # 1. secrets에 GOOGLE_SERVICE_ACCOUNT_KEY가 있는지 확인
        if "GOOGLE_SERVICE_ACCOUNT_KEY" not in st.secrets:
            st.error("❌ GOOGLE_SERVICE_ACCOUNT_KEY가 Streamlit Secrets에 설정되지 않았습니다.")
            st.info("📝 Streamlit Cloud 앱 설정에서 Advanced settings > Secrets에 Google 서비스 계정 키(JSON 내용)를 추가해주세요.")
            return None

        # 2. secrets에서 JSON 문자열을 가져와 파싱
        # service_key.json의 내용을 문자열로 직접 사용
        json_key_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_KEY"])

        # 3. service_account.Credentials.from_service_account_info 사용
        credentials = service_account.Credentials.from_service_account_info(
            json_key_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive']
        )
        gc = gspread.authorize(credentials)
        sheet_url = "https://docs.google.com/spreadsheets/d/11DUuktRmn1UlchUbeytQAsxC9RaHmL-PW-6480vXYSo/edit?gid=0#gid=0"
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
        sh = gc.open_by_key(sheet_id)
        
        # --- 기존 Sheet1 로드 ---
        worksheet_main = sh.worksheet('Sheet1') # 기존 'Sheet1'
        data_main = worksheet_main.get_all_values()
        df_main = pd.DataFrame(data_main[1:], columns=data_main[0])
        
        # --- 새로운 Data_Input 시트 로드 ---
        df_input_full = pd.DataFrame() # Data_Input 전체 데이터를 담을 변수 초기화
        try:
            worksheet_input = sh.worksheet('Data_Input') # 새롭게 추가한 'Data_Input' 시트
            data_input = worksheet_input.get_all_values()
            if data_input: # 데이터가 있을 경우에만 DataFrame 생성
                df_input_full = pd.DataFrame(data_input[1:], columns=data_input[0])
            else:
                st.info("ℹ️ 'Data_Input' 시트에 데이터가 없습니다. 새로운 정보를 입력해주세요.")
            
            # --- 여기에서 '질문', '답변', 'Image URL' 컬럼을 합치는 로직은 그대로 유지 ---
            cols_to_use = ['질문', '답변', 'Image URL']
            df_main_filtered = df_main[cols_to_use] if all(col in df_main.columns for col in cols_to_use) else pd.DataFrame(columns=cols_to_use)
            df_input_filtered = df_input_full[cols_to_use] if all(col in df_input_full.columns for col in cols_to_use) else pd.DataFrame(columns=cols_to_use)

            combined_df = pd.concat([df_main_filtered, df_input_filtered], ignore_index=True)

        except gspread.exceptions.WorksheetNotFound:
            st.warning("⚠️ 'Data_Input' 시트를 찾을 수 없습니다. 새로운 정보를 저장하려면 시트를 생성해주세요.")
            combined_df = df_main # Data_Input이 없으면 기존 Sheet1만 사용

        if len(combined_df) < 1 or combined_df.empty:
            st.warning("구글 시트에 유효한 데이터가 없습니다. 시트에 '질문', '답변', 'Image URL' 컬럼을 포함해 데이터를 입력해 주세요.")
            return None

        questions = []
        answers = []
        image_urls = []

        for index, row in combined_df.iterrows():
            question_cell = str(row.get('질문', ''))
            answer_cell = row.get('답변', '')
            image_url_cell = row.get('Image URL', '')

            for q in question_cell.split(','):
                q_stripped = q.strip()
                if q_stripped:
                    questions.append(q_stripped)
                    answers.append(answer_cell)
                    image_urls.append(image_url_cell)
        
        return {
            'questions': questions,
            'answers': answers,
            'image_urls': image_urls,
            'full_data_input': df_input_full # 'Data_Input' 시트의 전체 데이터프레임을 반환
        }


    except json.JSONDecodeError:
        st.error("❌ Streamlit Secrets의 GOOGLE_SERVICE_ACCOUNT_KEY 내용이 올바른 JSON 형식이 아닙니다.")
        st.info("📝 service_key.json 파일의 전체 내용을 큰따옴표 안에 정확히 복사했는지 확인해주세요.")
        return None
    except Exception as e:
        st.error(f"❌ 구글 시트 연결 또는 인증 오류: {type(e).__name__} - {str(e)}")
        st.info("📝 1. 구글 서비스 계정 이메일 주소가 구글 시트와 공유되어 있는지 확인해주세요.\n"
                "📝 2. Streamlit Secrets에 입력된 GOOGLE_SERVICE_ACCOUNT_KEY의 내용이 정확한지 확인해주세요.")
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

    # 여기에 '정보 입력' 섹션을 추가합니다.
    st.header("새 정보 입력")
    st.markdown("##### 📝 새로운 수술 정보를 추가하세요")

    # 정보 입력 폼
    with st.form("new_data_form", clear_on_submit=True):
        input_question = st.text_input("질문 (예: TUC 수술 세팅 방법)", key="input_question_field")
        input_answer = st.text_area("답변 내용 (자세한 절차, 기구 목록 등)", key="input_answer_field")

        # 파일 업로드 (이미지)
        uploaded_file = st.file_uploader("관련 이미지 업로드 (선택 사항)", type=["png", "jpg", "jpeg"], key="image_uploader_field")
        
        # 텍스트 입력 필드
        input_doctor = st.text_input("집도의", key="input_doctor_field")
        input_room = st.text_input("수술방 번호", key="input_room_field")
        input_surgery = st.text_input("수술명", key="input_surgery_field")

        # --- 이 부분이 수정됩니다: '도구/장비 구분' 대신 '수술 장비', '수술 도구' 입력 필드 ---
        input_surgery_device = st.text_input("수술 장비 (콤마로 구분)", help="예: C-arm, 전기소작기, 모니터", key="input_surgery_device_field")
        input_surgery_tool = st.text_input("수술 도구 (콤마로 구분)", help="예: Foley Catheter, Resectoscope Set", key="input_surgery_tool_field")
        # --- 수정 끝 ---

        submitted = st.form_submit_button("정보 저장")

        if submitted:
            # 1. 파일명 생성 및 로컬 저장 (프로토타입용)
            image_filename = None
            if uploaded_file is not None:
                file_extension = uploaded_file.name.split('.')[-1]
                image_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name.replace(' ', '_')}"
                
                if not os.path.exists("images"):
                    os.makedirs("images")
                
                with open(os.path.join("images", image_filename), "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success(f"이미지 '{image_filename}'가 로컬 'images' 폴더에 저장되었습니다. 💾")
            
            # 2. Google Sheets에 데이터 추가
            try:
                json_key_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_KEY"])
                credentials = service_account.Credentials.from_service_account_info(
                    json_key_info,
                    scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
                )
                gc = gspread.authorize(credentials)
                sheet_url = "https://docs.google.com/spreadsheets/d/11DUuktRmn1UlchUbeytQAsxC9RaHmL-PW-6480vXYSo/edit?gid=0#gid=0"
                sheet_id = sheet_url.split('/d/')[1].split('/')[0]
                sh = gc.open_by_key(sheet_id)
                input_worksheet = sh.worksheet('Data_Input') # 'Data_Input' 탭 선택

                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # --- 이 부분이 수정됩니다: new_row 순서 및 컬럼 매칭 ---
                new_row = [
                    input_question,
                    input_answer,
                    image_filename if image_filename else "",
                    current_time,
                    input_doctor,
                    input_room,
                    input_surgery,
                    input_surgery_device, # H열: 수술 장비
                    input_surgery_tool   # I열: 수술 도구
                ]
                # --- 수정 끝 ---

                input_worksheet.append_row(new_row)
                st.success("새로운 정보가 성공적으로 저장되었습니다! ✅")
                
                load_google_sheet_data.clear()
                
            except Exception as e:
                st.error(f"정보 저장 중 오류 발생: {e}")
                st.warning("Google Sheet 권한, 탭 이름, 컬럼 이름이 정확한지 확인해주세요.")

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
                "예시) tuc 수술 준비"
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