# persona-evaluator

## セットアップ

1. 依存関係のインストール:
```bash
pip install -r requirements.txt
```

2. 環境変数を設定（`.env` でも可）:
```bash
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o
export APP_USERNAME=your_username
export APP_PASSWORD=your_secure_password
```

3. アプリの起動:
```bash
streamlit run app.py
```

## 使い方
- ログイン後、企業名・Web URL・PDF・課題を入力
- セグメントを指定するか、AI提案を利用
- ペルソナ生成を実行
- 事業アイデア（CSV または手入力）を追加
- ペルソナごとの評価を実行すると自動で集計されます
- 「PDFレポートを生成」ボタンからダウンロードできます

## 注意
- デフォルトのログイン情報はサンプルです。必ず `APP_USERNAME` / `APP_PASSWORD` を設定してください。
- クローリングには一般的な User-Agent を付与し、タイムアウトを設定しています。