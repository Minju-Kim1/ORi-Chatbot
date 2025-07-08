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

# --- Define System Message (defined first for initialization) ---
system_message_content = """
You are a friendly and helpful AI assistant for operating room nurses.
Provide answers as concisely as possible so they can be immediately understood and followed, even in urgent situations.
The target audience for this chatbot is operating room nurses. Please refer to tables and figures in your answers.
Please respond in English.
"""

# --- Initialize session state variables at the top of the code ---
# Manage login state
if "login" not in st.session_state:
    st.session_state["login"] = False

# Perplexity model initialization
if "perplexity_model" not in st.session_state:
    st.session_state["perplexity_model"] = "sonar-pro"

# Chat history related session state variables initialization
if "chat_logs" not in st.session_state:
    st.session_state["chat_logs"] = {} # Dictionary to store all chat logs

if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None # ID of the currently viewed chat

# Message list initialization
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": system_message_content}
    ]
# Add flag for showing guidelines
if "show_guidelines" not in st.session_state:
    st.session_state.show_guidelines = True

# --- Define Synonym Dictionary ---
SYNONYM_MAP = {
    "surgery preparation": ["surgical setup", "surgery setup", "setup", "preparation"],
    "equipment": ["instruments", "supplies", "items"],
    "method": ["procedure", "process"],
    "TUC": ["TUR", "tuc", "transurethral", "resection"], # Assuming TUR is common in English for TUC context
    "using": ["needed", "required equipment", "needed equipment", "required items", "needed items", "required instruments", "needed instruments"]
}

# --- Query expansion function ---
def expand_query_with_synonyms(query):
    expanded_queries = [query]
    for main_term, synonyms in SYNONYM_MAP.items():
        if main_term in query.lower(): # Use .lower() for case-insensitive matching
            for syn in synonyms:
                if syn.lower() not in query.lower():
                    expanded_queries.append(query.replace(main_term, syn, 1)) # Replace only first occurrence
        for syn in synonyms:
            if syn.lower() in query.lower():
                if main_term.lower() not in query.lower():
                    expanded_queries.append(query.replace(syn, main_term, 1))
                for other_syn in [s for s in synonyms if s.lower() != syn.lower()]:
                    if other_syn.lower() not in query.lower():
                        expanded_queries.append(query.replace(syn, other_syn, 1))
    return list(set(expanded_queries))


# --- Image Base64 encoding function (to reduce duplicate code) ---
@st.cache_data
def get_ori_icon_base64():
    try:
        with open("ori_icon.png", "rb") as f:
            image_bytes = f.read()
            return base64.b64encode(image_bytes).decode()
    except FileNotFoundError:
        st.warning("ori_icon.png not found. Please check the path.")
        return None

# --- Title and icon rendering function ---
def render_title_and_icon(is_clickable=False):
    col1_main, col2_main, col3_main = st.columns([0.5, 3, 0.5])

    with col2_main:
        st.markdown("<h1 style='text-align: center; display: block; width: 100%; margin-bottom: 0px;'>My Scrub Mate ORi</h1>", unsafe_allow_html=True)
        
        encoded_image = get_ori_icon_base64()
        if encoded_image:
            st.markdown(
                f"<p style='text-align: center; width: 100%; margin-top: 5px;'><img src='data:image/png;base64,{encoded_image}' width='100'></p>",
                unsafe_allow_html=True
            )

def login():
    render_title_and_icon(is_clickable=False)

    st.subheader("Login")
    user_id = st.text_input("ID")
    user_pw = st.text_input("Password", type="password")
    if st.button("Login"):
        if user_id == "ori" and user_pw == "0":
            st.session_state["login"] = True
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Incorrect ID or password.")


if not st.session_state["login"]:
    login()
    st.stop()

def extract_image_url(text):
    return None

def extract_core_summary(answer):
    return answer.split('\n')[0].strip()

# --- [Modified Title and Icon Centering Start] ---
render_title_and_icon(is_clickable=False)
# --- [Modified Title and Icon Centering End] ---

# Display chatbot guidelines
if st.session_state.show_guidelines and len(st.session_state.messages) == 1:
    st.markdown("---")
    st.subheader("🏥 How to Use ORi")
    st.markdown("##### **Quickly provides OR setup and equipment information!**")
    st.markdown("---")
    col1_guide, col2_guide = st.columns(2)

    with col1_guide:
        st.markdown("##### 💡 Ask like this")
        st.info("• How to set up Room 37 for TUC surgery")
        st.info("• Equipment needed for TUC surgery")

    with col2_guide:
        st.markdown("##### ✨ Get answers like this")
        st.success("• Key information summarized")
        st.success("• Relevant images/tables provided")

    st.markdown("---")
    st.markdown("##### 💬 Feel free to ask anything!")
    st.warning("⚠️ **ORi is for reference only.** Always prioritize hospital protocols during actual work!")
    st.markdown("---")

@st.cache_data
def load_google_sheet_data():
    try:
        # 1. Check if GOOGLE_SERVICE_ACCOUNT_KEY exists in secrets
        if "GOOGLE_SERVICE_ACCOUNT_KEY" not in st.secrets:
            st.error("❌ GOOGLE_SERVICE_ACCOUNT_KEY is not set in Streamlit Secrets.")
            st.info("📝 Please add your Google Service Account Key (JSON content) to Streamlit Cloud app settings > Advanced settings > Secrets.")
            return None

        # 2. Get and parse JSON string from secrets
        json_key_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_KEY"])

        # 3. Use service_account.Credentials.from_service_account_info
        credentials = service_account.Credentials.from_service_account_info(
            json_key_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets',
                            'https://www.googleapis.com/auth/drive']
        )
        gc = gspread.authorize(credentials)
        sheet_url = "https://docs.google.com/spreadsheets/d/11DUuktRmn1UlchUbeytQAsxC9RaHmL-PW-6480vXYSo/edit?gid=0#gid=0"
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
        sh = gc.open_by_key(sheet_id)
        
        # --- Load existing Sheet1 ---
        worksheet_main = sh.worksheet('Sheet1') # Existing 'Sheet1'
        data_main = worksheet_main.get_all_values()
        df_main = pd.DataFrame(data_main[1:], columns=data_main[0])
        
        # --- Load new Data_Input sheet ---
        df_input_full = pd.DataFrame() # Initialize variable to hold full Data_Input data
        try:
            worksheet_input = sh.worksheet('Data_Input') # Newly added 'Data_Input' sheet
            data_input = worksheet_input.get_all_values()
            if data_input: # Create DataFrame only if data exists
                df_input_full = pd.DataFrame(data_input[1:], columns=data_input[0])
            else:
                st.info("ℹ️ 'Data_Input' worksheet is empty. Please enter new information.")
            
            # --- Keep the logic to combine '질문', '답변', 'Image URL' columns here ---
            cols_to_use = ['질문', '답변', 'Image URL'] # Assuming these column names are fixed in Korean in Google Sheet
            df_main_filtered = df_main[cols_to_use] if all(col in df_main.columns for col in cols_to_use) else pd.DataFrame(columns=cols_to_use)
            df_input_filtered = df_input_full[cols_to_use] if all(col in df_input_full.columns for col in cols_to_use) else pd.DataFrame(columns=cols_to_use)

            combined_df = pd.concat([df_main_filtered, df_input_filtered], ignore_index=True)

        except gspread.exceptions.WorksheetNotFound:
            st.warning("⚠️ 'Data_Input' worksheet not found. Please create the sheet to save new information.")
            combined_df = df_main # If Data_Input is not found, use only existing Sheet1

        if len(combined_df) < 1 or combined_df.empty:
            st.warning("No valid data found in Google Sheet. Please ensure the sheet contains '질문', '답변', 'Image URL' columns and data.")
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
            'full_data_input': df_input_full # Return the full dataframe of 'Data_Input' sheet
        }

    except json.JSONDecodeError:
        st.error("❌ Content of GOOGLE_SERVICE_ACCOUNT_KEY in Streamlit Secrets is not a valid JSON format.")
        st.info("📝 Please ensure you have copied the entire content of your service_key.json file accurately within double quotes.")
        return None
    except Exception as e:
        st.error(f"❌ Google Sheet connection or authentication error: {type(e).__name__} - {str(e)}")
        st.info("📝 1. Please check if your Google Service Account email address is shared with your Google Sheet.\n"
                "📝 2. Please verify that the content of GOOGLE_SERVICE_ACCOUNT_KEY entered in Streamlit Secrets is correct.")
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
        st.info("ℹ️ No questions registered in Google Sheet. Please add question/answer data to the sheet.")
else:
    st.info("ℹ️ Failed to load Google Sheet data. Please check the error message above.")


if "PERPLEXITY_API_KEY" not in st.secrets:
    st.error("❌ PERPLEXITY_API_KEY is not set.")
    st.info("📝 Please add your API key to the .streamlit/secrets.toml file.")
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

# Function to start a new chat (existing logic retained)
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
            log_title = first_user_message["content"] if first_user_message else "New Chat"
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

# Function to load a specific chat (existing logic retained)
def load_chat_log(chat_id):
    if st.session_state.current_chat_id and st.session_state.current_chat_id != chat_id:
        if len(st.session_state.messages) > 1:
            if st.session_state.current_chat_id not in st.session_state.chat_logs:
                first_user_message = next((m for m in st.session_state.messages if m["role"] == "user"), None)
                log_title = first_user_message["content"] if first_user_message else "New Chat"
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

# --- [Sidebar Implementation] ---
with st.sidebar:
    st.header("My Chat History")
    
    # "New Chat" button maintained to start new chats via sidebar
    if st.button("New Chat", key="new_chat_button"):
        start_new_chat()

    st.markdown("---")

    # Add 'Enter Information' section here
    st.header("Enter New Information")
    st.markdown("##### 📝 Add new surgical information")

    # Information input form
    with st.form("new_data_form", clear_on_submit=True):
        input_question = st.text_input("Question (e.g., TUC surgery setup method)", key="input_question_field")
        input_answer = st.text_area("Answer Content (e.g., detailed procedures, instrument list)", key="input_answer_field")

        # File upload (image)
        uploaded_file = st.file_uploader("Upload related image (Optional)", type=["png", "jpg", "jpeg"], key="image_uploader_field")
        
        # Text input fields
        input_doctor = st.text_input("Surgeon", key="input_doctor_field")
        input_room = st.text_input("Operating Room Number", key="input_room_field")
        input_surgery = st.text_input("Surgery Name", key="input_surgery_field")

        # --- This section is modified: 'Tool/Equipment Classification' replaced with 'Surgical Equipment', 'Surgical Tool' input fields ---
        input_surgery_device = st.text_input("Surgical Equipment (comma-separated)", help="e.g., C-arm, Electrocautery, Monitor", key="input_surgery_device_field")
        input_surgery_tool = st.text_input("Surgical Instruments (comma-separated)", help="e.g., Foley Catheter, Resectoscope Set", key="input_surgery_tool_field")
        # --- End of modification ---

        submitted = st.form_submit_button("Save Information")

        if submitted:
            # 1. Generate filename and save locally (for prototype)
            image_filename = None
            if uploaded_file is not None:
                file_extension = uploaded_file.name.split('.')[-1]
                image_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name.replace(' ', '_')}"
                
                if not os.path.exists("images"):
                    os.makedirs("images")
                
                with open(os.path.join("images", image_filename), "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success(f"Image '{image_filename}' saved to local 'images' folder. 💾")
            
            # 2. Add data to Google Sheets
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
                input_worksheet = sh.worksheet('Data_Input') # Select 'Data_Input' tab

                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # --- This section is modified: new_row order and column matching ---
                new_row = [
                    input_question,
                    input_answer,
                    image_filename if image_filename else "",
                    current_time,
                    input_doctor,
                    input_room,
                    input_surgery,
                    input_surgery_device, # Column H: Surgical Equipment
                    input_surgery_tool    # Column I: Surgical Tool
                ]
                # --- End of modification ---

                input_worksheet.append_row(new_row)
                st.success("New information successfully saved! ✅")
                
                load_google_sheet_data.clear()
                
            except Exception as e:
                st.error(f"Error saving information: {e}")
                st.warning("Please check Google Sheet permissions, tab name, and column names are correct.")

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
                    help="Click to load this chat history."
                ):
                    load_chat_log(chat_id)

            with col2_log:
                if st.button("🗑️", key=f"delete_{chat_id}", help="Delete this chat history."):
                    del st.session_state.chat_logs[chat_id]
                    if st.session_state.current_chat_id == chat_id:
                        start_new_chat()
                    else:
                        st.rerun()
            st.markdown("---")
    else:
        st.info("No saved chat history.")

    st.markdown("---")

    if st.button("Logout", key="logout_button", help="End current session and return to login screen."):
        st.session_state["login"] = False
        st.session_state.clear()
        st.rerun()

# --- [Existing chat display logic retained] ---
for message in st.session_state.messages:
    if message["role"] == "system":
        continue
    
    avatar_icon = "ori_icon.png" if message["role"] == "assistant" else "user"
    
    with st.chat_message(message["role"], avatar=avatar_icon):
        if "image_url" in message and message["image_url"]:
            local_image_path = os.path.join("images", message["image_url"])
            if os.path.exists(local_image_path):
                st.image(local_image_path, caption="OR Equipment Setup Example", use_container_width=True)
            else:
                st.warning(f"Image file not found: {message['image_url']}")
        st.markdown(message["content"])

# --- [User input processing logic retained] ---
if prompt := st.chat_input("How can I help you prepare for surgery?"):
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
        response_content = "No question data available. Please enter questions/answers in the Google Sheet."
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
                {"role": "system", "content": f"Here is information regarding a surgical question. Based on this information, answer the user's question concisely and to the point. Use numbering, icons, and tables if necessary. Omit unnecessary explanations. \n\nInformation: {answer_from_sheet}"},
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
                        st.image(local_image_path, caption="OR Equipment Setup Example", use_container_width=True)
                    else:
                        st.warning(f"Image file not found: {current_image_file_name}")
                
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
                "Sorry, I could not find that information.\n"
                "Do you have another question? \n"
                "Example) TUC surgery preparation"
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
