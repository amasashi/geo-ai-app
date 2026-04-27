"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { GeoJSON as LeafletGeoJSON, Map as LeafletMap } from "leaflet";
import type { GeoJsonObject } from "geojson";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import styles from "./GeoMapApp.module.css";

type MlitStatus = {
  configured: boolean;
  openai_configured: boolean;
  library_api_configured: boolean;
  data_platform_api_configured: boolean;
  providers?: {
    reinfolib?: { configured: boolean; api_configured: boolean; command_env: string; tool_env: string };
    data_platform?: { configured: boolean; api_configured: boolean; command_env: string; tool_env: string };
  };
};

type MlitQueryResponse = {
  query: string;
  provider?: string;
  tool: string;
  arguments: Record<string, unknown>;
  planner?: Record<string, unknown> | null;
  geojson: GeoJsonObject | null;
  warning?: string | null;
  text: string;
  raw: Record<string, unknown>;
};

type JsonRecord = Record<string, unknown>;

type DataPlatformDetailResponse = {
  detail?: JsonRecord | null;
  thumbnails?: { id: string; url: string }[];
  thumbnail_warning?: string | null;
};

const examples = [
  "東京駅周辺の地価公示ポイント",
  "新宿駅周辺の用途地域",
  "東京駅周辺のバス停を国土交通データプラットフォームから検索",
  "35.681236,139.767125 周辺の都市計画"
];

const imagePropertyKeys = [
  "thumbnail_url",
  "thumbnailUrl",
  "thumbnailURL",
  "image_url",
  "imageUrl",
  "imageURL",
  "photo_url",
  "photoUrl",
  "URL",
  "url"
];

function assetSrc(asset: string | { src: string }): string {
  return typeof asset === "string" ? asset : asset.src;
}

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : null;
}

function textValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeUrl(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : null;
}

function isLikelyImageUrl(url: string): boolean {
  return /\.(avif|gif|jpe?g|png|webp)(\?|#|$)/i.test(url) || /thumbnail|image|photo|download/i.test(url);
}

function findUrlInValue(value: unknown, imageOnly: boolean): string | null {
  const directUrl = normalizeUrl(value);
  if (directUrl && (!imageOnly || isLikelyImageUrl(directUrl))) {
    return directUrl;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findUrlInValue(item, imageOnly);
      if (found) {
        return found;
      }
    }
  }

  const record = asRecord(value);
  if (record) {
    for (const key of imagePropertyKeys) {
      const found = findUrlInValue(record[key], imageOnly);
      if (found) {
        return found;
      }
    }
  }

  return null;
}

function getDataPlatformIds(properties: JsonRecord): { datasetId: string | null; dataId: string | null } {
  return {
    datasetId: textValue(properties.dataset_id) || textValue(properties["DPF:dataset_id"]),
    dataId: textValue(properties.id) || textValue(properties["DPF:id"])
  };
}

function findMetadata(detail?: JsonRecord | null): JsonRecord {
  return asRecord(detail?.metadata) || {};
}

function findImageUrl(properties: JsonRecord, detailResponse?: DataPlatformDetailResponse | null): string | null {
  const thumbnail = detailResponse?.thumbnails?.find((item) => normalizeUrl(item.url));
  if (thumbnail) {
    return thumbnail.url;
  }

  const detail = detailResponse?.detail || null;
  const metadata = findMetadata(detail);
  return findUrlInValue(properties, true) || findUrlInValue(detail, true) || findUrlInValue(metadata, true);
}

function findDownloadUrl(detailResponse?: DataPlatformDetailResponse | null): string | null {
  const metadata = findMetadata(detailResponse?.detail || null);
  return (
    normalizeUrl(metadata["DPF:downloadURLs"]) ||
    findUrlInValue(metadata["DPF:downloadURLs"], false) ||
    normalizeUrl(metadata["DPF:dataURLs"]) ||
    findUrlInValue(metadata["DPF:dataURLs"], false)
  );
}

function popupRow(label: string, value: unknown): string {
  const display = textValue(value);
  if (!display) {
    return "";
  }
  return `<div class="geo-popup-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(display)}</strong></div>`;
}

function buildPopupContent(
  properties: JsonRecord,
  detailResponse?: DataPlatformDetailResponse | null,
  loadingDetail = false
): string {
  const detail = detailResponse?.detail || null;
  const metadata = findMetadata(detail);
  const title =
    textValue(properties.name) ||
    textValue(properties.title) ||
    textValue(properties.Name) ||
    textValue(properties["名称"]) ||
    textValue(detail?.title) ||
    textValue(metadata["DPF:title"]) ||
    "MLIT data";
  const imageUrl = findImageUrl(properties, detailResponse);
  const downloadUrl = findDownloadUrl(detailResponse);
  const rows = [
    popupRow("データセット", properties.dataset_id || metadata["DPF:dataset_id"]),
    popupRow("カタログ", properties.catalog_id || metadata["DPF:catalog_id"]),
    popupRow("年度", properties.year || metadata["DPF:year"]),
    popupRow("分類", metadata["DPF:object_category"]),
    popupRow("路線", metadata["DPF:route_name"])
  ].join("");

  const image = imageUrl
    ? `<img class="geo-popup-image" src="${escapeHtml(imageUrl)}" alt="${escapeHtml(title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'" />`
    : "";
  const link = downloadUrl
    ? `<a class="geo-popup-link" href="${escapeHtml(downloadUrl)}" target="_blank" rel="noreferrer">関連データを開く</a>`
    : "";
  const loading = loadingDetail ? `<div class="geo-popup-note">詳細と画像を読み込み中...</div>` : "";
  const thumbnailWarning =
    !imageUrl && detailResponse?.thumbnail_warning
      ? `<div class="geo-popup-note">${escapeHtml(detailResponse.thumbnail_warning)}</div>`
      : "";

  return `<div class="geo-popup"><strong class="geo-popup-title">${escapeHtml(title)}</strong>${image}<div class="geo-popup-rows">${rows}</div>${link}${loading}${thumbnailWarning}</div>`;
}

export default function GeoMapApp() {
  const mapNodeRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const dataLayerRef = useRef<LeafletGeoJSON | null>(null);
  const [query, setQuery] = useState(examples[0]);
  const [status, setStatus] = useState<MlitStatus | null>(null);
  const [message, setMessage] = useState("MCP設定を確認しています...");
  const [messageType, setMessageType] = useState<"info" | "error" | "success">("info");
  const [result, setResult] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!mapNodeRef.current || mapRef.current) {
      return;
    }

    let isMounted = true;

    import("leaflet").then((leaflet) => {
      if (!isMounted || !mapNodeRef.current || mapRef.current) {
        return;
      }

      leafletRef.current = leaflet;
      leaflet.Icon.Default.mergeOptions({
        iconRetinaUrl: assetSrc(markerIcon2x),
        iconUrl: assetSrc(markerIcon),
        shadowUrl: assetSrc(markerShadow)
      });

      const map = leaflet.map(mapNodeRef.current).setView([35.681236, 139.767125], 13);
      leaflet.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }).addTo(map);
      mapRef.current = map;
    });

    return () => {
      isMounted = false;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    fetch("/api/mlit/status")
      .then((response) => response.json())
      .then((data: MlitStatus) => {
        setStatus(data);
        if (data.configured) {
          setMessage("MCPサーバー設定済みです。取得したいデータを入力してください。");
          setMessageType("success");
        } else {
          setMessage("MCPサーバー設定が未設定です。バックエンド起動時のMCPコマンドを確認してください。");
          setMessageType("error");
        }
      })
      .catch(() => {
        setMessage("バックエンドAPIに接続できません。FastAPIサーバーを確認してください。");
        setMessageType("error");
      });
  }, []);

  function renderGeoJson(geojson: GeoJsonObject) {
    const map = mapRef.current;
    const leaflet = leafletRef.current;
    if (!map || !leaflet) {
      return;
    }

    if (dataLayerRef.current) {
      dataLayerRef.current.removeFrom(map);
    }

    const layer = leaflet.geoJSON(geojson, {
      onEachFeature(feature, featureLayer) {
        const properties = (feature.properties || {}) as JsonRecord;
        const { datasetId, dataId } = getDataPlatformIds(properties);
        const popupLayer = featureLayer as typeof featureLayer & {
          setPopupContent: (content: string) => void;
          on: (eventName: "popupopen", callback: () => void) => void;
        };
        let detailLoaded = false;

        popupLayer.bindPopup(buildPopupContent(properties));

        if (datasetId && dataId) {
          popupLayer.on("popupopen", () => {
            if (detailLoaded) {
              return;
            }
            detailLoaded = true;
            popupLayer.setPopupContent(buildPopupContent(properties, null, true));

            fetch(
              `/api/mlit/data-platform/detail?dataset_id=${encodeURIComponent(datasetId)}&data_id=${encodeURIComponent(dataId)}`
            )
              .then((response) => {
                if (!response.ok) {
                  throw new Error("詳細取得に失敗しました。");
                }
                return response.json();
              })
              .then((detailResponse: DataPlatformDetailResponse) => {
                popupLayer.setPopupContent(buildPopupContent(properties, detailResponse));
              })
              .catch((error) => {
                popupLayer.setPopupContent(
                  `${buildPopupContent(properties)}<div class="geo-popup-note">${escapeHtml(
                    error instanceof Error ? error.message : "詳細取得に失敗しました。"
                  )}</div>`
                );
              });
          });
        }
      }
    }).addTo(map);

    dataLayerRef.current = layer;
    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [28, 28] });
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setMessage("取得したいデータを入力してください。");
      setMessageType("error");
      return;
    }

    setIsLoading(true);
    setResult("");
    setMessage("国交省MCPサーバーへ問い合わせています...");
    setMessageType("info");

    try {
      const response = await fetch("/api/mlit/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmedQuery })
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "データ取得に失敗しました。");
      }

      const typedData = data as MlitQueryResponse;
      setResult(typedData.text || JSON.stringify(typedData.raw, null, 2));

      if (typedData.geojson) {
        renderGeoJson(typedData.geojson);
        setMessage(`取得成功: ${typedData.provider || "MCP"} / ${typedData.tool} を使って地図に表示しました。`);
        setMessageType("success");
      } else if (typedData.warning) {
        setMessage(typedData.warning);
        setMessageType("error");
      } else {
        setMessage("取得成功: GeoJSONは見つからなかったため、結果テキストのみ表示しています。");
        setMessageType("info");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "データ取得に失敗しました。");
      setMessageType("error");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.header}>
          <span className={styles.kicker}>MLIT MCP / GeoAI</span>
          <h1>GeoAI Map</h1>
          <p>国土交通省MCPサーバーから欲しい地理空間データを取得し、GeoJSONを地図に表示します。</p>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label htmlFor="query">取得したいデータ</label>
          <textarea
            id="query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例: 東京駅周辺の地価公示ポイント"
          />
          <button type="submit" disabled={isLoading}>
            {isLoading ? "取得中..." : "国交省MCPから取得"}
          </button>
        </form>

        <div className={styles.examples} aria-label="入力例">
          {examples.map((example) => (
            <button
              className={styles.exampleButton}
              key={example}
              type="button"
              onClick={() => setQuery(example)}
            >
              {example}
            </button>
          ))}
        </div>

        <section className={`${styles.status} ${styles[messageType]}`}>
          <strong>状態</strong>
          <span>{message}</span>
          {status ? (
            <small>
              OpenAI: {status.openai_configured ? "configured" : "not configured"} / reinfolib:{" "}
              {status.providers?.reinfolib?.api_configured || status.library_api_configured ? "configured" : "not configured"} / data platform:{" "}
              {status.providers?.data_platform?.api_configured || status.data_platform_api_configured ? "configured" : "not configured"}
            </small>
          ) : null}
        </section>

        <section className={styles.result}>
          <h2>取得結果</h2>
          <pre>{result || "まだ結果はありません。"}</pre>
        </section>
      </aside>

      <section className={styles.mapPane} aria-label="地図">
        <div className={styles.map} ref={mapNodeRef} />
      </section>
    </main>
  );
}
