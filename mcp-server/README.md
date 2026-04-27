# MCPサーバー配置方針

このディレクトリには、GeoAI App から呼び出す国土交通省MCPサーバーを配置します。

現在は、国土交通省ページから案内されている公開実装 `chirikuuka/mlit-geospatial-mcp` を `mlit-geospatial-mcp/` 配下に置いています。

## 現在の配置

```text
mcp-server/
└── mlit-geospatial-mcp/
    ├── src/server.py
    ├── requirements.txt
    └── README.md
```

## アプリからの呼び出し

FastAPIバックエンドは、`.env` の `MLIT_MCP_COMMAND` を使ってMCPサーバーを子プロセスとして起動します。

```env
MLIT_MCP_COMMAND=python mcp-server/mlit-geospatial-mcp/src/server.py
```

MCPサーバー側では、不動産情報ライブラリAPIキーが必要です。

```env
LIBRARY_API_KEY=your-api-key
```

## OpenAI Plannerとの関係

このアプリでは、OpenAI APIが `tools/list` の結果とユーザーの自然言語クエリを見て、呼び出すMCPツールと引数を決定します。

```text
FastAPI
  -> MCP tools/list
  -> OpenAI Planner
  -> MCP tools/call
```

## 注意

- このディレクトリにあるMCPサーバーはstdio型です。
- FastAPIはMCPサーバーをHTTP越しではなく、子プロセスとして起動して通信します。
- 実データ取得には `LIBRARY_API_KEY` が必要です。
- `OPENAI_API_KEY` が未設定の場合、ツール選択は簡易ヒューリスティックになります。
