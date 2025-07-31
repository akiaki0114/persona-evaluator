import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from openai import OpenAI
from dotenv import load_dotenv
import os
import certifi
import pdfplumber
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from serpapi import GoogleSearch
from generate_pdf_report import generate_pdf_report
import re

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")

def run_with_spinner(label, func, *args, **kwargs):
    with st.spinner(label):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            st.error(f"{label} でエラー: {e}")
            return None

def get_official_site(company_name):
    search = GoogleSearch({
        "q": f"{company_name} 公式サイト",
        "hl": "ja",
        "api_key": os.getenv("SERPAPI_KEY")
    })
    results = search.get_dict()
    try:
        return results["organic_results"][0]["link"]
    except (KeyError, IndexError):
        return ""

def fetch_website_text(url):
    try:
        res = requests.get(url, timeout=5, verify=certifi.where())
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
        return "\n".join(line for line in lines if line)
    except Exception as e:
        st.warning(f"{url} 取得失敗: {e}")
        return ""

def fetch_all_texts(base_url, max_pages=10):
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
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all("a", href=True):
                href = a['href']
                new_url = urljoin(base_url, href)
                if urlparse(new_url).netloc == domain and new_url not in visited and new_url not in to_visit:
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

def generate_personas(company_name, combined_text):
    prompt = f"""
あなたはトップ戦略コンサルタント兼マーケターです。
以下の情報を元に、この会社の顧客（消費者または取引先）としてのペルソナを4人作成してください。

重要:
- {company_name} の社員や関係者は含めない。
- あくまでこの会社の商品・サービスを利用する顧客像です。

# 会社名
{company_name}

# Webサイト情報 + PDF資料
{combined_text}

## ペルソナ1〜4
- 名前
- 年齢, 性別, 職業, 性格, 家族構成, 趣味・価値観, 日常の悩み,
  サービス利用シーン, 解決したい課題, どこに最も価値を感じるか,
  情報収集チャネル, 購買決定プロセス, 競合サービス利用状況,
  価格感度, 導入後期待ROI, 長期ビジョン
"""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def generate_persona_image(persona_desc):
    prompt = f"""
{persona_desc} を参考にした30-50代ビジネスパーソンの顧客の日常風景のスナップ。
自然光、生活感のある背景、リラックスした表情。
リアルな質感、文字やラベルなし、広告ではなくドキュメンタリー風。
"""
    img = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024"
    )
    return img.data[0].url

def evaluate_persona_score(persona, idea_name, idea_content):
    prompt = f"""
あなたはペルソナ本人の気持ちになりきって、下記の事業アイデアを「自分なら本当に使いたいか/生活がどう広がるか」の観点で現実的に評価してください。
100点満点で点数をつけ、その理由を1文で述べてください。
点数は広がりを持たせて（高得点も時々出るイメージで）、忖度せずに正直に、なるべく生活の中での利用イメージと広がりまで想像して回答してください。

# ペルソナ
{persona}

# 事業アイデア
名称: {idea_name}
内容: {idea_content}

# 出力フォーマット
- スコア（100点満点・数字のみ）
- 理由（1文、利用シーンの想像・生活への広がりを踏まえて）
"""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def evaluate_strategy_multiaxis(company_name, idea_name, idea_content):
    prompt = f"""
あなたは極めて現実的な戦略コンサルタントです。
下記の事業アイデアを「市場性」「競争優位性」「収益性」「実現可能性」「成長性」の5軸で100点満点で評価し、それぞれ理由を簡潔に述べてください。
表記ゆれなく必ず下記フォーマット通り、点数と理由を出力してください。

# 会社名
{company_name}

# 事業アイデア
名称: {idea_name}
内容: {idea_content}

# 出力フォーマット
- 市場性: xx点（理由: 〜〜〜）
- 競争優位性: xx点（理由: 〜〜〜）
- 収益性: xx点（理由: 〜〜〜）
- 実現可能性: xx点（理由: 〜〜〜）
- 成長性: xx点（理由: 〜〜〜）
"""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def generate_new_potential_personas(company_name, existing_personas, idea_name, idea_content):
    persona_list_str = "\n".join([p[:400] for p in existing_personas])
    prompt = f"""
あなたはトップ戦略コンサルタントです。
下記の事業アイデアは、これまでの顧客層にはリーチしていなかった“新たな潜在顧客層”の開拓にもつながる可能性があります。

# 事業アイデア
名称: {idea_name}
内容: {idea_content}

# 既存顧客ペルソナ一覧
{persona_list_str}

絶対条件:
- {company_name}の社員や関係者は含めないこと
- 既存ペルソナと属性や特徴が重複しない、新たな顧客層（潜在ニーズ）を2名分

## ペルソナ出力フォーマット
- 名前
- 年齢・性別・職業・価値観・日常の悩み・このアイデアで惹かれる理由
"""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def extract_persona_names(persona_list):
    names = []
    for persona in persona_list:
        m = re.search(r'名前[:：]\s*([^\n]+)', persona)
        if m:
            names.append(m.group(1).strip())
        else:
            m2 = re.search(r'[:：]\s*([^\s（\(\-]+)', persona.split('\n')[0])
            if m2:
                names.append(m2.group(1))
            else:
                names.append(f"ペルソナ{len(names)+1}")
    return names

st.title("顧客ペルソナ×事業アイデア評価ツール")

# STEP 1
st.header("STEP 1: 企業情報")
col1, col2 = st.columns(2)
company_name = col1.text_input("① 企業名（例: 三越伊勢丹）")
manual_url = col2.text_input("② URLを直接指定")
uploaded_pdf = st.file_uploader("③ 中期経営計画や決算資料などのPDFアップロード（任意・複数可）", type=["pdf"], accept_multiple_files=True)
generate_images = st.checkbox("ペルソナイメージも生成する")

if st.button("🚀 STEP1: ペルソナを生成スタート"):
    combined_text = ""
    url = get_official_site(company_name) if company_name and not manual_url else manual_url
    if url:
        web_text = run_with_spinner("複数ページクロール中...", fetch_all_texts, url)
        combined_text += web_text + "\n"

    if uploaded_pdf:
        for pdf_file in uploaded_pdf:
            pdf_text = run_with_spinner(f"{pdf_file.name} を解析中...", extract_text_from_pdf, pdf_file)
            combined_text += pdf_text + "\n"

    combined_text = combined_text[:60000]

    if combined_text:
        personas_text = run_with_spinner("ペルソナ生成中...", generate_personas, company_name or manual_url, combined_text)
        if not personas_text:
            st.error("ペルソナ生成に失敗しました。もう一度試してください。")
        else:
            persona_list = personas_text.split("## ペルソナ")[1:]
            persona_images, persona_images_bytes = [], []
            for i, persona in enumerate(persona_list, start=1):
                if generate_images:
                    img_url = run_with_spinner(f"ペルソナ{i} のイメージ生成中...", generate_persona_image, persona)
                    persona_images.append(img_url)
                    try:
                        img_bytes = requests.get(img_url, verify=False).content
                        persona_images_bytes.append(BytesIO(img_bytes))
                    except Exception as e:
                        st.warning(f"画像ダウンロード失敗: {e}")
                        persona_images_bytes.append(None)
                else:
                    persona_images.append(None)
                    persona_images_bytes.append(None)
            st.session_state["persona_list"] = persona_list
            st.session_state["persona_images"] = persona_images
            st.session_state["persona_images_bytes"] = persona_images_bytes
            st.success("✅ ペルソナ生成完了！")
    else:
        st.warning("企業情報（Web / PDF）を入力してください。")

if "persona_list" in st.session_state:
    st.header("【生成されたペルソナ】")
    persona_names = extract_persona_names(st.session_state["persona_list"])
    for i, (persona, img_url, name) in enumerate(zip(st.session_state["persona_list"], st.session_state["persona_images"], persona_names), start=1):
        cols = st.columns([1,3])
        with cols[0]:
            if img_url:
                st.image(img_url, caption=f"{name}")
        with cols[1]:
            st.text(persona.strip()[:1000] + "...")

# STEP 2
st.header("STEP 2: 事業アイデア入力（複数可）")
if "idea_texts" not in st.session_state:
    st.session_state["idea_texts"] = [("", "")]
if "add_idea_flag" not in st.session_state:
    st.session_state.add_idea_flag = False

uploaded_file = st.file_uploader("CSVアップロード（事業アイデア名, 事業内容）", type=["csv"])
ideas = []

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    for _, row in df.iterrows():
        ideas.append((row["事業アイデア名"], row["事業内容"]))
else:
    for i, (name, content) in enumerate(st.session_state["idea_texts"]):
        name = st.text_input(f"事業アイデア{i+1} 名称", value=name, key=f"idea_name_{i}")
        content = st.text_area(f"事業アイデア{i+1} 内容", value=content, key=f"idea_content_{i}")
        st.session_state["idea_texts"][i] = (name, content)

    if st.button("事業アイデアを追加"):
        st.session_state.add_idea_flag = True

    if st.session_state.add_idea_flag:
        st.session_state["idea_texts"].append(("", ""))
        st.session_state.add_idea_flag = False
        st.rerun()

    ideas = [idea for idea in st.session_state["idea_texts"] if idea[0] and idea[1]]

if st.button("🚀 STEP2: 全アイデアを評価"):
    persona_list = st.session_state.get("persona_list", [])
    persona_images_bytes = st.session_state.get("persona_images_bytes", [])
    persona_names = extract_persona_names(persona_list)
    if persona_list and ideas:
        records = []
        strategy_eval_dict = {}
        new_potential_personas_dict = {}
        for idea_name, idea_content in ideas:
            result_row = {"事業アイデア名": idea_name}
            # 各ペルソナ受容性評価
            for i, persona in enumerate(persona_list, start=1):
                eval_result = run_with_spinner(f"{idea_name} × {persona_names[i-1]} 受容性評価中...", evaluate_persona_score, "## ペルソナ"+persona, idea_name, idea_content)
                try:
                    score_line = next(line for line in eval_result.splitlines() if "スコア" in line or "点" in line)
                    score = re.search(r'(\d+)', score_line).group(1)
                except Exception:
                    score = "N/A"
                try:
                    reason_line = next(line for line in eval_result.splitlines() if "理由" in line)
                    reason = reason_line.split(":")[-1].strip()
                except StopIteration:
                    reason = ""
                result_row[f"ペルソナ{i}スコア"] = score
                result_row[f"ペルソナ{i}理由"] = reason

            # 多軸戦略評価
            multi_eval_result = run_with_spinner(f"{idea_name} 多軸戦略評価中...", evaluate_strategy_multiaxis, company_name, idea_name, idea_content)
            strategy_eval_dict[idea_name] = multi_eval_result

            # 新規潜在顧客ペルソナ生成
            new_persona_text = run_with_spinner(
                f"{idea_name}向け 新規潜在顧客ペルソナ生成中...",
                generate_new_potential_personas, company_name, persona_list, idea_name, idea_content
            )
            new_potential_personas_dict[idea_name] = new_persona_text
            records.append(result_row)

        df = pd.DataFrame(records)
        st.session_state["result_df"] = df
        st.session_state["latest_persona_list"] = persona_list
        st.session_state["latest_persona_images_bytes"] = persona_images_bytes
        st.session_state["new_potential_personas"] = new_potential_personas_dict
        st.session_state["strategy_eval_dict"] = strategy_eval_dict
        st.dataframe(df)
        st.header("【多軸戦略評価】")
        for idea_name, eval_text in strategy_eval_dict.items():
            st.markdown(f"### ■ {idea_name}")
            st.markdown(f"<pre>{eval_text}</pre>", unsafe_allow_html=True)
        st.header("【新規潜在顧客ペルソナ】")
        for idea_name, new_pers in new_potential_personas_dict.items():
            st.markdown(f"### ■ {idea_name}")
            st.markdown(f"<pre>{new_pers}</pre>", unsafe_allow_html=True)
    else:
        st.warning("まずSTEP1を実行しペルソナを生成してください。")

if "result_df" in st.session_state and not st.session_state["result_df"].empty:
    st.header("【ダウンロード】")
    if st.button("PDFをダウンロード"):
        pdf = generate_pdf_report(
            st.session_state["latest_persona_list"],
            st.session_state["result_df"],
            company_name or "manual",
            st.session_state["latest_persona_images_bytes"],
            st.session_state.get("new_potential_personas", None),
            st.session_state.get("strategy_eval_dict", None),
        )
        st.download_button("📄 PDFダウンロード", data=pdf, file_name=f"{company_name or 'manual'}_評価レポート.pdf", mime="application/pdf")
    if st.button("CSVをダウンロード"):
        csv = st.session_state["result_df"].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("CSVダウンロード（UTF-8 Excel対応）", data=csv, file_name=f"{company_name or 'manual'}_評価結果.csv", mime='text/csv')
else:
    st.info("まず全アイデア評価を実行してください。")
