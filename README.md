# GeoAI App

GeoAI App は、国土交通省MCPサーバーから地理空間データを取得し、GeoJSONをLeaflet地図上に表示するための FastAPI + Next.js アプリケーションです。

バックエンドAPIとReactフロントエンドを分離した構成にしているため、今後アプリ規模が大きくなっても、API、MCP連携、UIをそれぞれ拡張しやすくなっています。

## 構成

```text
.
├── backend/
│   └── app/
│       ├── api/          # FastAPIのルート定義
│       ├── core/         # 設定関連のヘルパー
│       ├── services/     # MCPクライアントとレスポンス解析
│       ├── main.py       # FastAPIアプリ生成
│       └── schemas.py    # リクエスト/レスポンス用モデル
├── frontend/
│   ├── app/              # Next.js App Routerのページ
│   ├── components/       # Reactコンポーネント
│   ├── next.config.mjs   # FastAPIへのAPIプロキシ設定
│   └── package.json
├── main.py               # uvicorn main:app 用の互換エントリーポイント
├── requirements.txt
└── README.md
```

## バックエンド

バックエンドはJSON APIを提供し、設定された国土交通省MCPサーバーを stdio JSON-RPC 経由で呼び出します。

バックエンドを起動する前に、MCPサーバーの起動コマンドを `MLIT_MCP_COMMAND` に設定してください。

```bash
export MLIT_MCP_COMMAND="your-mlit-mcp-server-command"
```

MCPサーバーが複数のツールを公開していて、利用するツールを明示したい場合は `MLIT_MCP_TOOL` を設定します。

```bash
export MLIT_MCP_TOOL="search"
```

FastAPIを起動します。

```bash
venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

互換用に、以下の起動方法も使えます。

```bash
venv/bin/uvicorn main:app --reload --port 8000
```

## フロントエンド

フロントエンドの依存関係をインストールします。

```bash
cd frontend
npm install
```

Next.jsを起動します。

```bash
npm run dev
```

ブラウザで以下を開きます。

```text
http://127.0.0.1:3000
```

フロントエンドは、デフォルトで `/api/*` へのリクエストを `http://127.0.0.1:8000` のFastAPIバックエンドへプロキシします。別のバックエンドURLを使う場合は、次のように指定します。

```bash
NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001" npm run dev
```

## エンドポイント

| メソッド | パス | 説明 |
| --- | --- | --- |
| GET | `/` | シンプルなJSONメッセージを返します。 |
| GET | `/health` | アプリケーションのヘルスチェック情報を返します。 |
| GET | `/api/mlit/status` | `MLIT_MCP_COMMAND` が設定されているかを返します。 |
| POST | `/api/mlit/query` | 自然言語の問い合わせを国土交通省MCPサーバーへ送り、テキスト、MCPの生レスポンス、見つかったGeoJSONを返します。 |

## 地図画面の使い方

1. FastAPIバックエンドを起動します。
2. Next.jsフロントエンドを起動します。
3. `http://127.0.0.1:3000` を開きます。
4. `東京駅周辺の地価公示ポイント` のように、取得したいデータを入力します。
5. `国交省MCPから取得` をクリックします。

MCPレスポンスにGeoJSONが含まれている場合、フロントエンドがLeaflet地図上に描画し、取得結果の範囲へズームします。GeoJSONが含まれていない場合でも、取得したテキスト結果はサイドパネルに表示されます。
