# pip install openai gspread google-auth rapidfuzz
from openai import OpenAI
import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
import json
import os
import re
from rapidfuzz import process, fuzz

# 로그인 상태 관리
if "login" not in st.session_state:
    st.session_state["login"] = False

def login():
    st.title("나만의 스크럽 메이트 ORi🐥")
    st.subheader("로그인")
    user_id = st.text_input("아이디")
    user_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        if user_id == "ori" and user_pw == "0000":
            st.session_state["login"] = True
            st.success("로그인 성공!")
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

if not st.session_state["login"]:
    login()
    st.stop()

def extract_image_url(text):
    return None # 이제 이 함수는 사용하지 않으므로, 항상 None을 반환하도록 합니다.

def extract_core_summary(answer):
    # 답변에서 첫 번째 문장(혹은 핵심 요약)만 추출
    return answer.split('\n')[0].strip()

st.title("나만의 스크럽 메이트 ORi🐥")

# 구글 시트 연결
@st.cache_data # 데이터 로딩 성능 개선을 위해 @st.cache_data 데코레이터 주석 해제
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
        return df
    except FileNotFoundError:
        st.error("❌ service_key.json 파일을 찾을 수 없습니다.")
        st.info("📝 README.md 파일을 참고하여 구글 서비스 계정 키를 설정해주세요.")
        return None
    except Exception as e:
        st.error(f"❌ 구글 시트 연결 오류: {str(e)}")
        st.info("📝 구글 시트가 서비스 계정과 공유되어 있는지 확인해주세요.")
        return None

# 구글 시트 데이터 로드
sheet_data = load_google_sheet_data()

# Perplexity API 키 확인
if "PERPLEXITY_API_KEY" not in st.secrets:
    st.error("❌ PERPLEXITY_API_KEY가 설정되지 않았습니다.")
    st.info("📝 .streamlit/secrets.toml 파일에 API 키를 추가해주세요.")
    st.stop()

client = OpenAI(
    api_key=st.secrets["PERPLEXITY_API_KEY"],
    base_url="https://api.perplexity.ai"
)

if "perplexity_model" not in st.session_state:
    st.session_state["perplexity_model"] = "sonar-pro"

# RapidFuzz로 유사도 기반 질문 매칭 함수 (임계값 60~70)
def find_best_match(user_input, questions, threshold=65):
    if not questions:
        return None, 0, -1
    result = process.extractOne(user_input, questions, scorer=fuzz.ratio)
    if result and result[1] >= threshold:
        return result[0], result[1], result[2]
    return None, result[1] if result else 0, result[2] if result else -1

# 질문-답변 리스트 생성 및 안내
questions = []
answers = []
image_urls = [] # 이미지 URL 리스트 초기화

if sheet_data is not None:
    if '질문' in sheet_data.columns and '답변' in sheet_data.columns:
        questions = sheet_data['질문'].tolist()
        answers = sheet_data['답변'].tolist()
        
        if 'Image URL' in sheet_data.columns:
            # NaN 값(구글 시트의 빈 셀)은 None으로 처리하여 나중에 st.image()에서 오류가 나지 않도록 합니다.
            # 시트에 이제 '파일 이름'이 들어있으므로, 그대로 리스트로 변환합니다.
            image_urls = sheet_data['Image URL'].apply(lambda x: x if pd.notna(x) else None).tolist()
        else:
            st.warning("⚠️ 구글 시트에 'Image URL' 컬럼이 없습니다. 이미지 표시 기능이 제한될 수 있습니다.")
            image_urls = [None] * len(questions)
        
        if not questions:
            st.info("ℹ️ 구글 시트에 등록된 질문이 없습니다. 시트에 질문/답변 데이터를 추가해 주세요.")
    else:
        st.info("ℹ️ 구글 시트에 '질문', '답변' 컬럼이 없습니다. 시트 구조를 확인해 주세요.")
else:
    st.info("ℹ️ 구글 시트 데이터 로드에 실패했습니다. 위의 오류 메시지를 확인해 주세요.")


# 시스템 프롬프트
system_message_content = """
당신은 친절하고 도움이 되는 수술실 간호사의 AI 어시스턴트입니다.
긴급한 상황에서도 바로 보고 따라할 수 있도록 최대한 간결하게 답변해주세요.
이 챗봇을 사용하는 대상자는 수술실 간호사입니다. 표와 그림을 참고하여 답변해주세요.
한국어로 답변해주세요.
"""

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": system_message_content}
    ]

# 이전 대화 출력
for message in st.session_state.messages:
    if message["role"] != "system":
        if message["role"] == "assistant":
            with st.chat_message("assistant", avatar="ori_icon.png"):
                if "image_url" in message and message["image_url"]:
                    # --- [수정 필요 부분 1: 이미지 경로 생성] ---
                    # current_image_url은 이제 'room37_setting_tuc.png'와 같은 파일 이름이므로
                    # 'images/' 접두사를 붙여 올바른 로컬 경로를 생성합니다.
                    local_image_path = os.path.join("images", message["image_url"])
                    st.image(local_image_path, caption="관련 이미지", use_container_width=True)
                st.markdown(message["content"])
        else:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

# 유저 입력 처리
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    if len(st.session_state.messages) == 0 or st.session_state.messages[-1]["role"] != "user":
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if not questions:
            with st.chat_message("assistant"):
                st.warning("질문 데이터가 없습니다. 구글 시트에 질문/답변을 입력해 주세요.")
            st.session_state.messages.append({
                "role": "assistant",
                "content": "질문 데이터가 없습니다. 구글 시트에 질문/답변을 입력해 주세요.",
                "image_url": None
            })
        else:
            best_match, score, idx = find_best_match(prompt, questions)
            if best_match is not None and idx != -1:
                answer_from_sheet = answers[idx]
                
                # --- [수정 필요 부분 2: current_image_url 사용 방식] ---
                # image_urls 리스트에서 가져온 값은 이미 파일 이름입니다.
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
                    # --- [수정 필요 부분 3: st.image에 로컬 파일 경로 전달] ---
                    if current_image_file_name: # 파일 이름이 있다면
                        # 'images/' 폴더 안에 있는 파일 경로를 생성합니다.
                        image_path_to_display = os.path.join("images", current_image_file_name)
                        st.image(image_path_to_display, caption="수술방 장비 세팅 예시", use_container_width=True)
                    
                    message_placeholder = st.empty()
                    for chunk in stream:
                        if chunk.choices[0].delta.content is not None:
                            response_from_perplexity += chunk.choices[0].delta.content
                            message_placeholder.markdown(response_from_perplexity + "▌")
                    
                    message_placeholder.markdown(response_from_perplexity)
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_from_perplexity,
                    "image_url": current_image_file_name # 세션 상태에는 파일 이름만 저장 (경로는 st.image에서 다시 생성)
                })
            else:
                with st.chat_message("assistant"):
                    st.warning(f"죄송합니다. 해당 정보를 찾을 수 없습니다.")
                    st.markdown("다른 질문이 있으신가요? 다른 질문을 입력해주세요. 예시) 수술실 장비 세팅 방법을 알려주세요.")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f" 죄송합니다. 해당 정보를 찾을 수 없습니다.",
                    "image_url": None
                })
    else:
        st.warning("Assistant의 응답이 끝난 뒤에 입력하세요.")