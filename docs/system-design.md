# GeoAI App システム設計図

## 目的

GeoAI App は、自然言語クエリを OpenAI Planner で解釈し、不動産情報ライブラリMCP (`reinfolib`) と国土交通データプラットフォームMCP (`data_platform`) を使い分けて地理空間データを取得する Web 地図アプリです。

FastAPI が MCP クライアントとして動作し、MCP の `tools/list` 結果とユーザークエリを OpenAI Planner に渡します。Planner は `provider_name`、`tool_name`、`arguments_json` を返し、FastAPI が選択された MCP ツールを `tools/call` します。

開発用サンプルGeoJSONへのフォールバックはありません。MCPレスポンスだけでGeoJSONが得られない場合、不動産情報ライブラリ系に限り、同じ引数から不動産情報ライブラリAPIを直接再取得して地図表示を試みます。

## Component UML

```mermaid
flowchart LR
    actor[User]
    browser[Browser]

    subgraph Frontend[Next.js Frontend]
        Page[app/map/page.tsx]
        GeoMap[GeoMapApp.tsx]
        Leaflet[Leaflet Map]
        Rewrite[next.config.mjs rewrites]
    end

    subgraph Backend[FastAPI Backend]
        Routes[api/routes.py]
        Config[core/config.py]
        McpClient[services/mcp_client.py]
        Planner[services/ai_planner.py]
        Schemas[schemas.py]
        DirectReinfolib[Direct Reinfolib fetch]
    end

    subgraph MCP[MCP Providers]
        ReinfolibMcp[reinfolib MCP<br/>mlit-geospatial-mcp]
        DataPlatformMcp[data_platform MCP<br/>mlit-dpf-mcp]
    end

    subgraph External[External Services]
        OpenAI[OpenAI Responses API]
        ReinfolibApi[不動産情報ライブラリAPI]
        DataPlatformApi[国土交通データプラットフォームAPI]
        OSM[OpenStreetMap Tiles]
    end

    actor --> browser --> Page --> GeoMap
    GeoMap --> Leaflet
    Leaflet --> OSM
    GeoMap -->|GET /api/mlit/status<br/>POST /api/mlit/query<br/>GET /api/mlit/data-platform/detail| Rewrite --> Routes

    Routes --> Config
    Routes --> Schemas
    Routes --> McpClient
    Routes --> DirectReinfolib
    McpClient --> Planner
    Planner --> OpenAI
    McpClient -->|stdio JSON-RPC| ReinfolibMcp
    McpClient -->|stdio JSON-RPC| DataPlatformMcp
    ReinfolibMcp --> ReinfolibApi
    DataPlatformMcp --> DataPlatformApi
    DirectReinfolib --> ReinfolibApi
```

## Deployment UML

```mermaid
flowchart TB
    subgraph Host[Local / Docker Host]
        subgraph Compose[docker-compose.yml]
            FrontendContainer[frontend<br/>Next.js :3000]
            BackendContainer[backend<br/>FastAPI :8000]
            ReinfolibContainer[mcp-reinfolib<br/>image validation / standalone]
            DataPlatformContainer[mcp-data-platform<br/>image validation / standalone]
        end

        EnvFile[.env]
        ReinfolibCode[mcp-server/mlit-geospatial-mcp/src/server.py]
        DataPlatformCode[mcp-server/mlit-dpf-mcp/src/server.py]
    end

    UserBrowser[User Browser] -->|http://127.0.0.1:3000| FrontendContainer
    FrontendContainer -->|NEXT_PUBLIC_API_BASE_URL<br/>/api/* rewrite| BackendContainer
    BackendContainer --> EnvFile
    BackendContainer -->|REINFOLIB_MCP_COMMAND<br/>subprocess stdio| ReinfolibCode
    BackendContainer -->|MLIT_DATA_PLATFORM_MCP_COMMAND<br/>subprocess stdio| DataPlatformCode

    ReinfolibContainer -. same source tree .-> ReinfolibCode
    DataPlatformContainer -. same source tree .-> DataPlatformCode

    BackendContainer -->|HTTPS| OpenAI[OpenAI API]
    ReinfolibCode -->|HTTPS + API key| ReinfolibApi[reinfolib.mlit.go.jp]
    DataPlatformCode -->|HTTPS + API key| DataPlatformApi[data-platform.mlit.go.jp]
    BackendContainer -->|direct HTTPS fallback| ReinfolibApi
```

## Sequence UML: Query

```mermaid
sequenceDiagram
    actor U as User
    participant F as GeoMapApp
    participant B as FastAPI routes.py
    participant C as MCP client
    participant R as Reinfolib MCP
    participant D as Data Platform MCP
    participant P as OpenAI Planner
    participant O as OpenAI API
    participant X as External MLIT API

    U->>F: 自然言語クエリ入力
    F->>B: POST /api/mlit/query { query }
    B->>B: request_id生成 / 空クエリ検証
    B->>C: call_mlit_mcp(query, request_id)

    par provider tools/list
        C->>R: initialize + tools/list
        R-->>C: reinfolib tools
    and provider tools/list
        C->>D: initialize + tools/list
        D-->>C: data_platform tools
    end

    alt OPENAI_API_KEYあり
        C->>P: query + available providers/tools
        P->>O: Responses API structured output
        O-->>P: McpToolPlan
        P-->>C: provider_name / tool_name / arguments_json
    else OpenAI未設定または呼び出し失敗
        C->>C: heuristic_provider_plan
    end

    C->>C: provider/tool存在確認 + arguments正規化

    alt provider = reinfolib
        C->>R: initialize + tools/call
        R->>X: 不動産情報ライブラリAPI
        X-->>R: result
        R-->>C: MCP result
    else provider = data_platform
        C->>D: initialize + tools/call
        D->>X: 国土交通データプラットフォームAPI
        X-->>D: result
        D-->>C: MCP result
    end

    C-->>B: provider / tool / arguments / planner / diagnostics / result
    B->>B: GeoJSON抽出 / text抽出 / warning生成
    B-->>F: query response
    F->>F: GeoJSONがあればLeaflet描画
```

## Sequence UML: Data Platform Popup Detail

```mermaid
sequenceDiagram
    actor U as User
    participant F as GeoMapApp
    participant B as FastAPI routes.py
    participant C as MCP client
    participant D as Data Platform MCP
    participant A as Data Platform API

    U->>F: 地図上のFeatureをクリック
    F->>F: propertiesから dataset_id / data_id を抽出
    F->>B: GET /api/mlit/data-platform/detail
    B->>C: call_mcp_tool_by_name(data_platform, get_data)
    C->>D: initialize + tools/call get_data
    D->>A: データ詳細取得
    A-->>D: detail result
    D-->>C: MCP result
    C-->>B: detail payload

    alt hasThumbnail = true
        B->>C: call_mcp_tool_by_name(data_platform, get_thumbnail_urls)
        C->>D: tools/call get_thumbnail_urls
        D->>A: thumbnail URL取得
        A-->>D: thumbnail URLs
        D-->>C: MCP result
        C-->>B: thumbnails
    end

    B-->>F: detail / thumbnails / thumbnail_warning
    F->>F: Popupを詳細情報と画像で更新
```

## Sequence UML: Reinfolib Direct Re-fetch

```mermaid
sequenceDiagram
    participant B as FastAPI routes.py
    participant C as MCP client
    participant R as Reinfolib MCP
    participant A as Reinfolib API

    B->>C: call_mlit_mcp(query)
    C->>R: tools/call get_multi_api
    R-->>C: result without GeoJSON
    C-->>B: provider=reinfolib, arguments, result
    B->>B: find_geojson(result) == null

    alt LIBRARY_API_KEYあり
        B->>B: lat/lonからタイル(z/x/y)計算
        loop target_apis
            B->>A: GET XPT002/XKT001/XKT002 response_format=geojson
            A-->>B: GeoJSON or error
        end
        B->>B: 用途地域/都市計画は対象地点でFeatureを絞り込み
        B-->>B: direct_reinfolib_diagnostics生成
    else API keyなし
        B-->>B: warning生成
    end
```

## Activity UML: Query Processing

```mermaid
flowchart TD
    Start([Start]) --> Validate{query is empty?}
    Validate -->|Yes| BadRequest[400 Query is required]
    Validate -->|No| ListProviders[tools/list for configured providers]

    ListProviders --> HasTools{available tools exist?}
    HasTools -->|No| BadGateway[502 No MCP tools available]
    HasTools -->|Yes| Plan{OpenAI usable?}

    Plan -->|Yes| OpenAIPlan[create_mcp_provider_plan]
    Plan -->|No| Heuristic[heuristic_provider_plan]
    OpenAIPlan --> Clarify{needs_clarification?}
    Heuristic --> Clarify

    Clarify -->|Yes, save_file only| IgnoreClarify[ignore clarification]
    Clarify -->|Yes, other| ClarifyError[502 clarification question]
    Clarify -->|No| Normalize[normalize_tool_arguments]
    IgnoreClarify --> Normalize

    Normalize --> CallTool[tools/call selected provider/tool]
    CallTool --> Extract[extract text + find GeoJSON]
    Extract --> Provider{provider}

    Provider -->|data_platform| DataPlatformGeo[convert searchResults lat/lon to GeoJSON]
    Provider -->|reinfolib| ReinfolibGeo{GeoJSON exists?}
    Provider -->|other| Response

    DataPlatformGeo --> Response[return response]
    ReinfolibGeo -->|Yes| Response
    ReinfolibGeo -->|No + API key| DirectFetch[direct Reinfolib re-fetch]
    ReinfolibGeo -->|No + no API key| Warning[warning]
    DirectFetch --> Response
    Warning --> Response
    Response --> End([End])
```

## Class UML

```mermaid
classDiagram
    class MlitQuery {
        +str query
    }

    class MlitStatus {
        +bool configured
        +bool openai_configured
        +dict providers
        +bool library_api_configured
        +bool data_platform_api_configured
        +str library_api_env
    }

    class MlitQueryResult {
        +str request_id
        +str query
        +str provider
        +str tool
        +dict arguments
        +dict planner
        +dict geojson
        +str warning
        +dict direct_reinfolib_diagnostics
        +str text
        +dict raw
    }

    class McpToolPlan {
        +str provider_name
        +str tool_name
        +str arguments_json
        +str reasoning_summary
        +bool needs_clarification
        +str clarification_question
        +arguments() dict
    }

    class Config {
        +get_reinfolib_mcp_command()
        +get_data_platform_mcp_command()
        +get_reinfolib_configured_tool()
        +get_data_platform_configured_tool()
        +is_openai_configured()
        +is_library_api_configured()
        +is_data_platform_api_configured()
        +get_secret_fingerprint()
    }

    class PlannerService {
        +create_mcp_provider_plan(query, providers)
        +create_mcp_tool_plan(query, tools)
        +heuristic_provider_plan(query, providers)
        +heuristic_plan(query, tools)
    }

    class McpClient {
        +list_configured_providers(request_id)
        +list_mcp_tools(provider_name, request_id)
        +call_mlit_mcp(query, request_id)
        +call_selected_mcp_tool(provider, tool, arguments, plan, request_id)
        +find_geojson(value)
        +extract_result_text(result)
    }

    class Routes {
        +get_mlit_status()
        +diagnose_reinfolib_api()
        +query_mlit_data(payload)
        +fetch_direct_reinfolib_geojson(arguments, request_id)
        +geojson_from_data_platform_payload(payload)
    }

    MlitQueryResult --> McpToolPlan : planner
    Routes --> MlitQuery : receives
    Routes --> McpClient : calls
    Routes --> Config : reads
    McpClient --> PlannerService : asks for plan
    PlannerService --> McpToolPlan : returns
    McpClient --> Config : provider commands
```

## State UML: Query Response

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Validating: POST /api/mlit/query
    Validating --> Rejected: empty query
    Validating --> ListingTools: valid query
    ListingTools --> Failed: no provider tools
    ListingTools --> Planning: tools available
    Planning --> Failed: unavailable provider/tool
    Planning --> CallingMcp: plan accepted
    CallingMcp --> McpError: MCP result isError
    CallingMcp --> Extracting: MCP response received
    Extracting --> RenderingGeoJSON: GeoJSON found
    Extracting --> DataPlatformSynthesized: data_platform searchResults with lat/lon
    Extracting --> DirectReinfolibFetch: reinfolib + no GeoJSON + API key
    Extracting --> TextOnly: no GeoJSON
    DirectReinfolibFetch --> RenderingGeoJSON: direct GeoJSON found
    DirectReinfolibFetch --> TextOnly: no direct GeoJSON
    McpError --> TextOnly: warning + raw text
    RenderingGeoJSON --> [*]
    DataPlatformSynthesized --> [*]
    TextOnly --> [*]
    Rejected --> [*]
    Failed --> [*]
```

## API UML

```mermaid
flowchart LR
    subgraph API[FastAPI Routes]
        Root[GET /]
        Health[GET /health]
        Status[GET /api/mlit/status]
        Diagnostics[GET /api/mlit/reinfolib/diagnostics]
        Detail[GET /api/mlit/data-platform/detail]
        Query[POST /api/mlit/query]
    end

    Status --> ProviderStatus[provider configuration<br/>api key fingerprints<br/>OpenAI status]
    Diagnostics --> ReinfolibProbe[Reinfolib XPT002 probe<br/>request_id / status_code / body_prefix]
    Detail --> DetailResponse[dataset_id<br/>data_id<br/>detail<br/>thumbnails<br/>thumbnail_warning]
    Query --> QueryResponse[request_id<br/>provider<br/>tool<br/>arguments<br/>planner<br/>geojson<br/>warning<br/>direct_reinfolib_diagnostics<br/>text<br/>raw]
```

## Environment

| 環境変数 | 用途 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI Planner用。未設定時はヒューリスティック選択 |
| `OPENAI_MODEL` | Plannerモデル。デフォルトは `gpt-4o-mini` |
| `REINFOLIB_MCP_COMMAND` | 不動産情報ライブラリMCP起動コマンド |
| `REINFOLIB_MCP_TOOL` | 不動産情報ライブラリMCPツール固定 |
| `REINFOLIB_API_KEY` / `LIBRARY_API_KEY` | 不動産情報ライブラリAPIキー |
| `MLIT_DATA_PLATFORM_MCP_COMMAND` | 国土交通データプラットフォームMCP起動コマンド |
| `MLIT_DATA_PLATFORM_MCP_TOOL` | データプラットフォームMCPツール固定 |
| `MLIT_DATA_PLATFORM_API_KEY` / `MLIT_API_KEY` | 国土交通データプラットフォームAPIキー |
| `MLIT_BASE_URL` | データプラットフォームAPI URL |
| `NEXT_PUBLIC_API_BASE_URL` | Next.js rewrite先のFastAPI URL |

## Notes

- FastAPI は MCP サーバーを HTTP サービスとして呼ぶのではなく、`subprocess` で起動して stdio JSON-RPC で通信します。
- `mcp-reinfolib` と `mcp-data-platform` の Compose サービスは同じコードをコンテナ化しますが、バックエンドが実際に呼ぶ MCP は `REINFOLIB_MCP_COMMAND` / `MLIT_DATA_PLATFORM_MCP_COMMAND` で起動するローカルプロセスです。
- `save_file` を持つMCPツールでは、Web地図表示用に `save_file=false` を正規化します。
- 不動産情報ライブラリAPIの直接再取得は、MCPの結果が空でも地図表示できる可能性を上げるための実データ再取得処理です。開発用サンプルデータではありません。
