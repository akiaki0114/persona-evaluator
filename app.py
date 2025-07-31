
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


# === 👤 ログイン認証の追加 ===
import streamlit as st

USERNAME = "admin"
PASSWORD = "DDmirai2025!"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 ログイン")
    username = st.text_input("ユーザー名")
    password = st.text_input("パスワード", type="password")
    if st.button("ログイン"):
        if username == USERNAME and password == PASSWORD:
            st.session_state.authenticated = True
        else:
            st.error("ユーザー名またはパスワードが違います")
    st.stop()  # ログインしてない限り以降は描画されない


# === 初期設定 ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")

# === 各種関数 ===
def fetch_website_text(url):
    try:
        res = requests.get(url, timeout=5, verify=certifi.where())
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        for tag in soup(["script", "style"]):
            tag.decompose()
        lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
        return "\n".join(line for line in lines if line)
    except Exception as e:
        st.warning(f"{url} 取得失敗: {e}")
        return ""

def fetch_all_texts(base_url, max_pages=5):
    visited, to_visit, all_texts = set(), [base_url], []
    domain = urlparse(base_url).netloc
    while to_visit and len(visited) < max_pages:
        current_url = to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)
        text = fetch_website_text(current_url)
        if text:
            all_texts.append(text[:5000])
        try:
            res = requests.get(current_url, timeout=5, verify=certifi.where())
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all("a", href=True):
                href = a['href']
                new_url = urljoin(base_url, href)
                if urlparse(new_url).netloc == domain:
                    if new_url not in visited and new_url not in to_visit:
                        to_visit.append(new_url)
        except Exception:
            continue
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

def suggest_segments_from_text(company_name, combined_text, issue_text, num_segments):
    prompt = f"""
あなたは優秀なマーケティングコンサルタントです。
以下の企業情報と、既存事業の課題に基づいて、マーケティング的に有望と思われる顧客セグメントを{num_segments}個、【セグメント名 + その理由】の形式で提案してください。

# 出力フォーマット
1. セグメント名：〇〇〇〇
   理由：〇〇〇〇
2. セグメント名：・・・
   理由：・・・

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
    return res.choices[0].message.content

def generate_persona_for_segment(company_name, combined_text, segment_description, issue_text):
    prompt = f"""
あなたはプロのマーケティングコンサルタントです。
以下の企業情報と事業課題に基づき、指定されたセグメントに沿って、戦略的に有効なペルソナを1人作成してください。

# セグメント
{segment_description}

# 会社名
{company_name}

# 企業情報（Web/PDF）
{combined_text}

# 既存事業の課題
{issue_text}

# 出力フォーマット（この構成・順番を厳守）
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
    return res.choices[0].message.content

def evaluate_persona_score(persona_text, idea_name, idea_desc):
    prompt = f"""
あなたはマーケティングリサーチの専門家です。
以下のペルソナと事業アイデアの内容を読み、このアイデアがこの人物にとって魅力的かどうかを5段階で評価してください。

# ペルソナ
{persona_text}

# 事業アイデア
名称: {idea_name}
内容: {idea_desc}

# 出力フォーマット
- 評価スコア（1〜5）: 
- 理由（100文字程度）:
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content

# === UI ===
st.title("🧩 ペルソナ生成 ＋ 事業評価ツール")

company_name = st.text_input("① 企業名")
website_url = st.text_input("② WebサイトURL（任意）")
uploaded_pdfs = st.file_uploader("③ PDF資料アップロード（任意）", type=["pdf"], accept_multiple_files=True)
issue_text = st.text_area("④ 既存事業の課題")

persona_mode = st.radio("⑤ ペルソナ生成モード", ["ユーザーがセグメントを指定", "AIがセグメントを自動提案"])
num_personas = st.slider("⑥ 各セグメントごとのペルソナ人数", 1, 3, 1)
num_segments_to_suggest = st.slider("⑦ 提案セグメント数（AI使用時）", 1, 6, 4)

if "segments" not in st.session_state:
    st.session_state.segments = ""
if "confirmed" not in st.session_state:
    st.session_state.confirmed = False
if "parsed_segments" not in st.session_state:
    st.session_state.parsed_segments = []
if "personas" not in st.session_state:
    st.session_state.personas = []
if "ideas" not in st.session_state:
    st.session_state.ideas = []

if persona_mode == "ユーザーがセグメントを指定":
    st.session_state.segments = st.text_area("⑧ セグメントを1行ずつ入力", height=150)
    if st.session_state.segments:
        st.session_state.confirmed = True

if persona_mode == "AIがセグメントを自動提案" and st.button("🔍 AIにセグメントを提案してもらう"):
    combined_text = ""
    if website_url:
        combined_text += fetch_all_texts(website_url)
    if uploaded_pdfs:
        for pdf in uploaded_pdfs:
            combined_text += extract_text_from_pdf(pdf)
    if company_name and issue_text and combined_text:
        raw_output = suggest_segments_from_text(company_name, combined_text, issue_text, num_segments_to_suggest)

        parsed_segments = []
        for block in raw_output.strip().split("\n"):
            if "セグメント名：" in block:
                name = block.replace("セグメント名：", "").strip()
                parsed_segments.append({"name": name, "reason": ""})
            elif "理由：" in block and parsed_segments:
                parsed_segments[-1]["reason"] = block.replace("理由：", "").strip()

        st.session_state.segments = "\n".join([seg["name"] for seg in parsed_segments])
        st.session_state.parsed_segments = parsed_segments
        st.session_state.confirmed = False
        st.success("AIによるセグメント提案が完了しました。編集後に確定してください。")

if st.session_state.parsed_segments and not st.session_state.confirmed:
    st.markdown("### 🤖 AIが提案したセグメント（理由つき）")
    for i, seg in enumerate(st.session_state.parsed_segments, 1):
        st.markdown(f"**{i}. {seg['name']}**  \n📝 理由: {seg['reason']}")

if st.session_state.segments and not st.session_state.confirmed:
    st.text_area("📝 編集可能なセグメント一覧（1行ずつ）", value=st.session_state.segments, height=150, key="segments_editable")
    if st.button("✅ 編集済みセグメントを確定"):
        st.session_state.segments = st.session_state.segments_editable
        st.session_state.confirmed = True
        st.success("セグメントを確定しました。")

# ペルソナ生成
if st.session_state.segments and st.session_state.confirmed and st.button("🚀 ペルソナ生成を実行"):
    combined_text = ""
    if website_url:
        combined_text += fetch_all_texts(website_url)
    if uploaded_pdfs:
        for pdf in uploaded_pdfs:
            combined_text += extract_text_from_pdf(pdf)
    st.session_state.personas = []
    for seg in st.session_state.segments.split("\n"):
        for i in range(num_personas):
            persona = generate_persona_for_segment(company_name, combined_text, seg, issue_text)
            st.session_state.personas.append({"segment": seg, "text": persona})

# CSVアップロードと事業評価制御
uploaded_csv = st.file_uploader("CSVアップロード（事業アイデア名, 事業内容）", type="csv")
if uploaded_csv:
    if st.button("📥 CSVから事業アイデアを読み込む"):
        df = pd.read_csv(uploaded_csv)
        for _, row in df.iterrows():
            st.session_state.ideas.append({
                "name": row["事業アイデア名"],
                "desc": row["事業内容"]
            })
        st.success("CSVから事業アイデアを読み込みました。")

idea_name = st.text_input("🆕 事業アイデア名")
idea_desc = st.text_area("📝 事業内容", height=120)
if st.button("➕ アイデア追加"):
    if idea_name and idea_desc:
        st.session_state.ideas.append({"name": idea_name, "desc": idea_desc})
        st.success("事業アイデアを追加しました。")

# 評価ボタン表示
if st.session_state.personas and st.session_state.ideas:
    if st.button("🧠 ペルソナごとの事業評価を実行"):
        for persona in st.session_state.personas:
            st.subheader(f"🎯 {persona['segment']} 向けペルソナの評価")
            for idea in st.session_state.ideas:
                result = evaluate_persona_score(persona["text"], idea["name"], idea["desc"])
                st.markdown(f"**📝 アイデア名：{idea['name']}**")
                st.code(result)
