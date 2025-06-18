# ORi 수술실 챗봇

구글 시트의 데이터를 기반으로 수술실 관련 질문에 답변하는 AI 챗봇입니다.

## 설정 방법

### 1. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 구글 서비스 계정 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에서 새 프로젝트 생성
2. Google Sheets API와 Google Drive API 활성화
3. 서비스 계정 생성:
   - IAM 및 관리 > 서비스 계정
   - "서비스 계정 만들기" 클릭
   - 이름 입력 후 "만들기" 클릭
4. 서비스 계정 키 생성:
   - 생성된 서비스 계정 클릭
   - "키" 탭 > "키 추가" > "새 키 만들기" > "JSON" 선택
   - 다운로드된 JSON 파일을 `service_key.json`으로 이름 변경하여 프로젝트 루트에 저장

### 3. 구글 시트 공유 설정

1. 구글 시트를 열고 "공유" 버튼 클릭
2. 서비스 계정 이메일 주소를 추가하고 "편집자" 권한 부여
3. 시트 URL에서 시트 ID 확인 (현재 코드에 이미 포함됨)

### 4. Streamlit Secrets 설정

`.streamlit/secrets.toml` 파일 생성:
```toml
PERPLEXITY_API_KEY = "your-perplexity-api-key"
```

### 5. 실행

```bash
streamlit run Chatbot.py
```

## 주요 기능

- 구글 시트의 데이터를 실시간으로 로드
- 수술실 관련 질문에 대한 정확한 답변
- 제공된 데이터 범위 내에서만 답변
- 스트리밍 응답으로 자연스러운 대화 경험

## 주의사항

- `service_key.json` 파일은 절대 공개 저장소에 업로드하지 마세요
- 구글 시트의 데이터 구조가 변경되면 코드 수정이 필요할 수 있습니다
- 현재는 'Sheet1' 시트를 사용하도록 설정되어 있습니다 

