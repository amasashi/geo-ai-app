# GeoAI App

GeoAI App は、OpenAI API と2種類の国土交通省系MCPサーバーを組み合わせ、自然言語で指定した地理空間データを取得してLeaflet地図上に表示する FastAPI + Next.js アプリケーションです。

FastAPIバックエンドがMCPクライアントとして動作し、OpenAI APIが「不動産情報ライブラリMCPと国土交通データプラットフォームMCPのどちらを使うか」「どのMCPツールをどの引数で呼ぶか」を判断します。

## 構成

```text
.
├── backend/
│   └── app/
│       ├── api/          # FastAPIのルート定義
│       ├── core/         # 設定関連のヘルパー
│       ├── services/     # MCPクライアント、OpenAI Planner、レスポンス解析
│       ├── main.py       # FastAPIアプリ生成
│       └── schemas.py    # リクエスト/レスポンス用モデル
├── frontend/
│   ├── app/              # Next.js App Routerのページ
│   ├── components/       # Reactコンポーネント
│   ├── next.config.mjs   # FastAPIへのAPIプロキシ設定
│   └── package.json
├── mcp-server/
│   ├── mlit-geospatial-mcp/  # 不動産情報ライブラリ向けMCP Server
│   └── mlit-dpf-mcp/         # 国土交通データプラットフォーム向けMCP Server
├── docs/                 # Mermaid設計図
├── docker-compose.yml
├── main.py               # uvicorn main:app 用の互換エントリーポイント
├── requirements.txt
└── README.md
```

## 環境変数

`.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

主要な設定は以下です。

```env
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
REINFOLIB_API_KEY=your-reinfolib-api-key
LIBRARY_API_KEY=your-reinfolib-api-key
REINFOLIB_MCP_COMMAND=python mcp-server/mlit-geospatial-mcp/src/server.py
REINFOLIB_MCP_TOOL=
MLIT_DATA_PLATFORM_API_KEY=your-mlit-data-platform-api-key
MLIT_API_KEY=your-mlit-data-platform-api-key
MLIT_BASE_URL=https://data-platform.mlit.go.jp/api/v1/
MLIT_DATA_PLATFORM_MCP_COMMAND=python mcp-server/mlit-dpf-mcp/src/server.py
MLIT_DATA_PLATFORM_MCP_TOOL=
```

`OPENAI_API_KEY` が未設定の場合、MCPプロバイダ・ツール選択は簡易ヒューリスティックにフォールバックします。地価公示・用途地域など不動産情報ライブラリ系の取得には `REINFOLIB_API_KEY` / `LIBRARY_API_KEY` が必要です。国土交通データプラットフォーム系の検索には `MLIT_DATA_PLATFORM_API_KEY` / `MLIT_API_KEY` が必要です。

## MCPサーバー

`mcp-server/mlit-geospatial-mcp/` に不動産情報ライブラリ向けMCP、`mcp-server/mlit-dpf-mcp/` に国土交通データプラットフォーム向けMCPを配置しています。

どちらもstdio型なので、FastAPIバックエンドが `REINFOLIB_MCP_COMMAND` / `MLIT_DATA_PLATFORM_MCP_COMMAND` で指定されたコマンドを子プロセスとして起動し、MCP JSON-RPCで通信します。

## バックエンド

依存関係をインストールします。

```bash
venv/bin/pip install -r requirements.txt
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

## Docker Compose

FastAPI、Next.js、2種類のMCPサーバー用イメージをまとめて起動できます。

```bash
cp .env.example .env
docker compose up --build
```

起動後、以下を開きます。

```text
http://127.0.0.1:3000
```

補足: MCPサーバーはstdio型のため、FastAPIが実際に呼び出すMCPはバックエンドコンテナ内の `mcp-server/mlit-geospatial-mcp/src/server.py` と `mcp-server/mlit-dpf-mcp/src/server.py` です。

## エンドポイント

| メソッド | パス | 説明 |
| --- | --- | --- |
| GET | `/` | シンプルなJSONメッセージを返します。 |
| GET | `/health` | アプリケーションのヘルスチェック情報を返します。 |
| GET | `/api/mlit/status` | MCP設定とOpenAI設定の状態を返します。 |
| GET | `/api/mlit/reinfolib/diagnostics` | 不動産情報ライブラリAPIキーと代表APIの疎通を診断します。 |
| POST | `/api/mlit/query` | 自然言語の問い合わせをOpenAI PlannerでMCPプロバイダ・ツール呼び出しに変換し、該当MCPサーバーへ送ります。 |

## 地図画面の使い方

1. `.env` に `OPENAI_API_KEY`、必要に応じて `REINFOLIB_API_KEY` / `MLIT_DATA_PLATFORM_API_KEY` を設定します。
2. FastAPIバックエンドを起動します。
3. Next.jsフロントエンドを起動します。
4. `http://127.0.0.1:3000` を開きます。
5. `東京駅周辺の地価公示ポイント` のように、取得したいデータを入力します。
6. `国交省MCPから取得` をクリックします。

MCPレスポンスにGeoJSONが含まれている場合、フロントエンドがLeaflet地図上に描画し、取得結果の範囲へズームします。GeoJSONが含まれていない場合でも、取得したテキスト結果はサイドパネルに表示されます。

## 設計図

Mermaid形式の設計図は以下にあります。

```text
docs/system-design.md
```

## 参照

- 国土交通省 地理空間MCP Server: https://www.mlit.go.jp/tochi_fudousan_kensetsugyo/tochi_fudousan_kensetsugyo_fr17_000001_00047.html
- MLIT Geospatial MCP Server: https://github.com/chirikuuka/mlit-geospatial-mcp
- MLIT DATA PLATFORM MCP Server: https://github.com/MLIT-DATA-PLATFORM/mlit-dpf-mcp
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
