import streamlit as st
import os
import requests
from bs4 import BeautifulSoup
import certifi
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv
from openai import OpenAI
import pdfplumber
import pandas as pd

# === 初期設定 ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")

# === 関数定義 ===

def fetch_website_text(url):
    try:
        res = requests.get(url, timeout=5, verify=certifi.where())
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        for tag in soup(["script", "style"]): tag.decompose()
        lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
        return "\n".join(line for line in lines if line)
    except Exception as e:
        st.warning(f"{url} の取得失敗: {e}")
        return ""

def fetch_all_texts(base_url, max_pages=5):
    visited, to_visit, all_texts = set(), [base_url], []
    domain = urlparse(base_url).netloc
    while to_visit and len(visited) < max_pages:
        current_url = to_visit.pop(0)
        if current_url in visited: continue
        visited.add(current_url)
        text = fetch_website_text(current_url)
        if text: all_texts.append(text[:5000])
        try:
            res = requests.get(current_url, timeout=5, verify=certifi.where())
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all("a", href=True):
                href = a['href']
                new_url = urljoin(base_url, href)
                if urlparse(new_url).netloc == domain:
                    if new_url not in visited and new_url not in to_visit:
                        to_visit.append(new_url)
        except Exception: continue
    return "\n\n".join(all_texts)

def extract_text_from_pdf(uploaded_pdf):
    text = ""
    try:
        with pdfplumber.open(uploaded_pdf) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except Exception as e:
        st.warning(f"PDF解析失敗: {e}")
    return text

def suggest_segments_from_text(company_name, combined_text, issue_text, segment_num):
    prompt = f"""
あなたは優秀なマーケティングコンサルタントです。
以下の企業情報と既存事業の課題をもとに、有望な顧客セグメントを{segment_num}個提案してください。

【出力形式】
[年代]・[性別]・[属性]（例：30代・女性・共働き主婦）

各セグメントには、その理由（なぜこのターゲットが重要なのか）も1〜2文で添えてください。

# 会社名
{company_name}

# 企業情報
{combined_text}

# 既存事業の課題
{issue_text}
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()

def generate_persona_for_segment(company_name, combined_text, segment_description, issue_text):
    prompt = f"""
あなたはプロのマーケティングコンサルタントです。
以下の企業情報と課題に基づき、指定されたセグメントに沿って、リアルなペルソナを1人作成してください。

# セグメント
{segment_description}

# 会社名
{company_name}

# 企業情報
{combined_text}

# 課題
{issue_text}

# 出力フォーマット
- 名前:
- 年齢, 性別, 職業:
- 性格:
- 家族構成:
- ライフスタイル:
- 趣味・価値観:
- 日常の悩み:
- サービス利用シーン:
- 解決したい課題:
- どこに価値を感じるか:
- 情報収集チャネル:
- 購買決定プロセス:
- 競合サービス:
- 価格感度:
- 導入期待効果:
- 将来展望:
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()

def evaluate_persona_score(persona_text, idea_name, idea_desc):
    prompt = f"""
以下のペルソナに対して、事業アイデアがどれだけ魅力的かを5段階で評価してください。

# ペルソナ
{persona_text}

# 事業アイデア
名称: {idea_name}
内容: {idea_desc}

# 出力形式
- 評価スコア（1〜5）:
- 理由（100文字程度）:
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()

# === UI ===
st.title("🎯 ペルソナ生成 ＋ 事業評価ツール")

# 入力項目
company_name = st.text_input("① 企業名")
website_url = st.text_input("② WebサイトURL（任意）")
uploaded_pdfs = st.file_uploader("③ PDF資料アップロード（任意）", type=["pdf"], accept_multiple_files=True)
issue_text = st.text_area("④ 既存事業の課題", height=100)
persona_mode = st.radio("⑤ ペルソナ生成モード", ["ユーザーがセグメントを指定", "AIがセグメントを自動提案"])
num_personas = st.slider("⑥ 各セグメントごとのペルソナ人数", 1, 3, 1)
segment_num = st.slider("⑦ AIに提案してほしいセグメント数", 1, 6, 4)

# 状態保持
if "segments" not in st.session_state: st.session_state.segments = []
if "confirmed" not in st.session_state: st.session_state.confirmed = False
if "personas" not in st.session_state: st.session_state.personas = []
if "ideas" not in st.session_state: st.session_state.ideas = []
if "evaluation_ready" not in st.session_state: st.session_state.evaluation_ready = False

# セグメント処理
if persona_mode == "ユーザーがセグメントを指定":
    input_text = st.text_area("⑧ セグメントを1行ずつ入力（例：30代・女性・主婦）", height=150)
    if input_text:
        st.session_state.segments = [s.strip() for s in input_text.splitlines() if s.strip()]
        st.session_state.confirmed = True

elif persona_mode == "AIがセグメントを自動提案":
    if st.button("🔍 AIにセグメント提案を依頼"):
        combined_text = ""
        if website_url: combined_text += fetch_all_texts(website_url)
        if uploaded_pdfs:
            for pdf in uploaded_pdfs:
                combined_text += extract_text_from_pdf(pdf)
        if company_name and issue_text and (combined_text or website_url):
            suggestion = suggest_segments_from_text(company_name, combined_text, issue_text, segment_num)
            st.text_area("📝 AIの提案（編集可能）", suggestion, key="ai_suggestion", height=250)
            if st.button("✅ セグメントを確定"):
                lines = [line.split(".", 1)[-1].strip() if "." in line else line.strip() for line in suggestion.splitlines()]
                st.session_state.segments = [l for l in lines if l]
                st.session_state.confirmed = True
                st.success("セグメントを確定しました。")

# ペルソナ生成
if st.session_state.confirmed and st.button("🚀 ペルソナを生成する"):
    combined_text = ""
    if website_url: combined_text += fetch_all_texts(website_url)
    if uploaded_pdfs:
        for pdf in uploaded_pdfs:
            combined_text += extract_text_from_pdf(pdf)
    st.session_state.personas = []
    for seg in st.session_state.segments:
        for _ in range(num_personas):
            persona = generate_persona_for_segment(company_name, combined_text, seg, issue_text)
            st.session_state.personas.append({"segment": seg, "text": persona})
    st.success("ペルソナ生成が完了しました。")

# ペルソナ表示
if st.session_state.personas:
    st.subheader("🧑‍🎤 生成されたペルソナ一覧")
    for i, p in enumerate(st.session_state.personas, 1):
        st.markdown(f"**{i}. セグメント：{p['segment']}**")
        st.text_area(label="", value=p['text'], height=400, key=f"persona_{i}")

# アイデア登録
st.subheader("💡 事業アイデア登録")
uploaded_csv = st.file_uploader("CSV（事業アイデア名, 事業内容）", type="csv")
if uploaded_csv:
    df = pd.read_csv(uploaded_csv)
    for _, row in df.iterrows():
        st.session_state.ideas.append({"name": row["事業アイデア名"], "desc": row["事業内容"]})
    st.success("CSVからアイデアを読み込みました。")
    st.session_state.evaluation_ready = False

idea_name = st.text_input("新規アイデア名")
idea_desc = st.text_area("事業内容", height=100)
if st.button("➕ アイデア追加"):
    if idea_name and idea_desc:
        st.session_state.ideas.append({"name": idea_name, "desc": idea_desc})
        st.success("アイデアを追加しました。")
        st.session_state.evaluation_ready = False

# 事業評価
if st.session_state.personas and st.session_state.ideas:
    if st.button("📊 ペルソナごとに事業評価を実施"):
        st.session_state.evaluation_ready = True

if st.session_state.evaluation_ready:
    st.header("🧠 各ペルソナごとの事業評価")
    for persona in st.session_state.personas:
        st.subheader(f"🎯 {persona['segment']} 向け")
        for idea in st.session_state.ideas:
            result = evaluate_persona_score(persona["text"], idea["name"], idea["desc"])
            st.markdown(f"**📝 {idea['name']}**")
            st.code(result)
