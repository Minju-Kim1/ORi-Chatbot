# 🏥 ORi: 나만의 스크럽 메이트 AI 챗봇

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ori-chatbot.streamlit.app/)

## 🌟 프로젝트 소개

ORi(오리)는 수술실 간호사를 위한 AI 어시스턴트 챗봇입니다. 수술 준비 및 장비 배치에 대한 질문에 빠르고 간결하게 답변하여 긴급한 상황에서도 필요한 정보를 즉시 확인할 수 있도록 돕습니다. 구글 시트에서 데이터를 가져와 정보를 제공하며, Perplexity AI를 활용하여 사용자 질문에 최적화된 답변을 생성합니다.

**주요 기능:**
* **간결하고 핵심적인 답변:** 수술실 환경에 맞춰 불필요한 설명을 제외하고 핵심 정보만 제공합니다.
* **구글 시트 연동:** 백엔드 데이터를 구글 시트에서 관리하여 손쉽게 업데이트 및 확장이 가능합니다.
* **이미지 및 표 제공:** 답변과 관련된 이미지 및 표 정보를 함께 제공하여 이해를 돕습니다.
* **동의어 확장:** 다양한 질문에도 정확한 정보를 찾을 수 있도록 동의어 사전을 활용하여 쿼리를 확장합니다.
* **채팅 기록 관리:** 이전 대화 기록을 저장하고 불러올 수 있으며, 불필요한 기록은 삭제할 수 있습니다.
* **로그인 기능:** 사용자 인증을 통해 앱 접근을 제어합니다.

## 🔗 앱 바로가기

[**ORi 챗봇 앱 실행하기**](https://ori-chatbot.streamlit.app/)

## ✨ 기술 스택

* **Python**
* **Streamlit** (웹 애플리케이션 프레임워크)
* **Perplexity AI API** (자연어 처리 및 답변 생성)
* **Google Sheets API** (데이터 저장 및 관리)
* **`gspread`**, **`google-auth`** (구글 서비스 연동)
* **`rapidfuzz`** (질문 유사도 검색)

## 🚀 설치 및 실행 방법 (개발자용)

### 1. 저장소 클론

```bash
git clone [https://github.com/Minju-Kim1/ORi-Chatbot.git](https://github.com/Minju-Kim1/ORi-Chatbot.git)
cd ORi-Chatbot
2. 가상 환경 설정 (권장)
Bash

python -m venv myenv
# Windows
.\myenv\Scripts\activate
# macOS/Linux
source myenv/bin/activate
3. 의존성 설치
Bash

pip install -r requirements.txt
# 또는 직접 설치:
# pip install openai gspread google-auth pandas rapidfuzz streamlit
4. API 키 및 서비스 계정 설정 (필수!)
이 앱은 Perplexity AI와 Google Sheets API를 사용합니다. 보안을 위해 이 키들은 절대로 GitHub에 직접 커밋해서는 안 됩니다. Streamlit Cloud 배포 시에는 Streamlit Secrets 기능을 사용하고, 로컬 개발 시에는 .streamlit/secrets.toml 파일을 사용합니다.

🔑 Perplexity AI API 키 설정
Perplexity AI에서 API 키를 발급받으세요.
로컬에서 실행하는 경우: ORi-Chatbot/.streamlit/ 폴더 내에 secrets.toml 파일을 생성하고 다음 내용을 추가합니다:
Ini, TOML

PERPLEXITY_API_KEY = "YOUR_PERPLEXITY_AI_KEY_HERE"
Streamlit Cloud에 배포하는 경우: Streamlit Cloud 앱 대시보드의 Settings > Secrets에서 PERPLEXITY_API_KEY = "YOUR_PERPLEXITY_AI_KEY_HERE" 형태로 직접 입력합니다.
🔑 Google Service Account Key 설정
Google Sheets에서 데이터를 읽어오기 위한 서비스 계정 키 설정이 필요합니다.

Google Cloud Console에서 서비스 계정 생성:
Google Cloud Console에 접속합니다.
새 프로젝트를 생성하거나 기존 프로젝트를 선택합니다.
IAM 및 관리자 > 서비스 계정으로 이동하여 새 서비스 계정을 생성합니다.
역할은 Google Sheets API 편집자 및 Google Drive API 관련 역할을 부여하는 것이 좋습니다.
서비스 계정을 생성한 후, 해당 서비스 계정의 키를 JSON 형식으로 생성하고 다운로드합니다. (service_key.json과 같은 이름으로 저장될 것입니다.)
구글 시트 공유:
앱에서 사용할 구글 시트(예: https://docs.google.com/spreadsheets/d/11DUuktRmn1UlchUbeytQAsxC9RaHmL-PW-6480vXYSo/edit?gid=0#gid=0)의 편집 권한을 방금 생성한 서비스 계정의 이메일 주소(예: your-service-account@your-project-id.iam.gserviceaccount.com)와 공유합니다.
Streamlit Secrets에 JSON 키 추가:
다운로드한 service_key.json 파일의 전체 내용을 복사합니다.
로컬에서 실행하는 경우: .streamlit/secrets.toml 파일에 다음 형태로 추가합니다. (JSON 내용을 '''...''' 안에 넣어야 합니다. private_key의 줄바꿈(\n)도 그대로 포함되어야 합니다.)
Ini, TOML

GOOGLE_SERVICE_ACCOUNT_KEY = '''
{
  "type": "service_account",
  "project_id": "YOUR_PROJECT_ID",
  "private_key_id": "YOUR_PRIVATE_KEY_ID",
  "private_key": "-----BEGIN PRIVATE KEY-----\\nYOUR_PRIVATE_KEY_CONTENT\\n-----END PRIVATE KEY-----\\n",
  "client_email": "YOUR_SERVICE_ACCOUNT_EMAIL",
  "client_id": "YOUR_CLIENT_ID",
  "auth_uri": "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)",
  "token_uri": "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)",
  "auth_provider_x509_cert_url": "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)",
  "client_x509_cert_url": "[https://www.googleapis.com/robot/v1/metadata/x509/](https://www.googleapis.com/robot/v1/metadata/x509/)...",
  "universe_domain": "googleapis.com"
}
'''
Streamlit Cloud에 배포하는 경우: Streamlit Cloud 앱 대시보드의 Settings > Secrets에서 위와 동일한 형태로 GOOGLE_SERVICE_ACCOUNT_KEY 변수에 JSON 내용을 직접 입력합니다.
5. 구글 시트 데이터 준비
앱이 질문에 답변하기 위한 데이터는 구글 시트에서 가져옵니다.
제공된 구글 시트 URL(https://docs.google.com/spreadsheets/d/11DUuktRmn1UlchUbeytQAsxC9RaHmL-PW-6480vXYSo/edit?gid=0#gid=0)을 참고하여 Sheet1 워크시트에 다음 컬럼을 포함하는 데이터를 입력해야 합니다:

질문 (콤마로 구분하여 여러 질문을 입력 가능)
답변
Image URL (선택 사항, 로컬 images 폴더 내의 이미지 파일명. 예: room37_setting.png)
예시:

질문	답변	Image URL
37번방 TUC 수술 세팅 방법	37번방에서는 망원경, 방광경 카메라, 쇄석위 고정 장치...	room37_setting.png
TUC 수술 필요한 장비	TUC 수술에 사용하는 장비는...	37_setting_tuc.png

Sheets로 내보내기
6. 이미지 파일 준비
구글 시트에 Image URL을 지정한 경우, 해당 이미지 파일은 프로젝트 루트의 images/ 폴더에 위치해야 합니다. (예: images/room37_setting.png)

7. 앱 로컬 실행
Bash

streamlit run newchatbot.py
성공적으로 실행되면 웹 브라우저에서 챗봇 앱이 열립니다.

⚠️ 중요 주의사항
API 키 보안: PERPLEXITY_API_KEY와 GOOGLE_SERVICE_ACCOUNT_KEY는 절대로 GitHub 공개 저장소에 직접 업로드해서는 안 됩니다. 반드시 Streamlit Secrets 기능을 활용하거나 로컬 .streamlit/secrets.toml 파일을 사용하세요. 실수로 업로드된 경우 Git 기록에서 완전히 제거해야 합니다.
정보의 정확성: ORi 챗봇이 제공하는 정보는 참고용입니다. 실제 의료 업무 시에는 반드시 병원의 공식 프로토콜과 지침을 우선적으로 따르세요.
서비스 계정 권한: 구글 서비스 계정에 필요한 최소한의 권한만 부여하여 보안을 강화하세요.