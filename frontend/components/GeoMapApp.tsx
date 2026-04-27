"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { GeoJSON as LeafletGeoJSON, Layer, Map as LeafletMap, PathOptions } from "leaflet";
import type { Feature, FeatureCollection, GeoJsonObject, Geometry } from "geojson";
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
  request_id?: string;
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

type FeatureSummary = {
  key: string;
  title: string;
  subtitle: string;
  providerLabel: string;
  geometryType: string;
  coordinateLabel: string;
  properties: JsonRecord;
};

type PanelTab = "detail" | "raw";

const examples = [
  "東京駅周辺 5km の道路を国土交通データプラットフォームから検索",
  "新宿駅周辺の用途地域",
  "東京駅周辺の地価公示ポイント",
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

const hiddenPropertyKeys = new Set(["__geoai_key"]);

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

function titleFromProperties(properties: JsonRecord, detail?: JsonRecord | null): string {
  const metadata = findMetadata(detail);
  return (
    textValue(properties.name) ||
    textValue(properties.title) ||
    textValue(properties.Name) ||
    textValue(properties["名称"]) ||
    textValue(detail?.title) ||
    textValue(metadata["DPF:title"]) ||
    "MLIT data"
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
  const title = titleFromProperties(properties, detail);
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

function isFeatureCollection(value: GeoJsonObject): value is FeatureCollection {
  return value.type === "FeatureCollection";
}

function isFeature(value: GeoJsonObject): value is Feature {
  return value.type === "Feature";
}

function featureKey(properties: JsonRecord, index: number): string {
  const stablePart =
    textValue(properties.id) ||
    textValue(properties["DPF:id"]) ||
    textValue(properties.title) ||
    textValue(properties.name) ||
    "feature";
  return `${index}-${stablePart}`;
}

function coordinateLabel(geometry: Geometry | null): string {
  if (!geometry || geometry.type !== "Point") {
    return "";
  }
  const [lon, lat] = geometry.coordinates;
  if (typeof lat !== "number" || typeof lon !== "number") {
    return "";
  }
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function subtitleFromProperties(properties: JsonRecord): string {
  return (
    textValue(properties["DPF:object_category"]) ||
    textValue(properties.dataset_id) ||
    textValue(properties["DPF:dataset_id"]) ||
    textValue(properties.catalog_id) ||
    textValue(properties["DPF:catalog_id"]) ||
    "GeoJSON Feature"
  );
}

function providerLabel(properties: JsonRecord): string {
  const catalog = textValue(properties.catalog_id) || textValue(properties["DPF:catalog_id"]);
  if (catalog === "rsdb") {
    return "道路DB";
  }
  if (catalog === "nlni_ksj") {
    return "国土数値情報";
  }
  return catalog || "MLIT";
}

function decorateFeature(feature: Feature, index: number): { feature: Feature; summary: FeatureSummary } {
  const properties = { ...(asRecord(feature.properties) || {}) };
  const key = featureKey(properties, index);
  properties.__geoai_key = key;
  const decoratedFeature = { ...feature, properties };

  return {
    feature: decoratedFeature,
    summary: {
      key,
      title: titleFromProperties(properties),
      subtitle: subtitleFromProperties(properties),
      providerLabel: providerLabel(properties),
      geometryType: feature.geometry?.type || "Unknown",
      coordinateLabel: coordinateLabel(feature.geometry),
      properties
    }
  };
}

function decorateGeoJson(geojson: GeoJsonObject): { geojson: GeoJsonObject; summaries: FeatureSummary[] } {
  if (isFeatureCollection(geojson)) {
    const decorated = geojson.features.map((feature, index) => decorateFeature(feature, index));
    const featureCollection: FeatureCollection = { ...geojson, features: decorated.map((item) => item.feature) };
    return {
      geojson: featureCollection,
      summaries: decorated.map((item) => item.summary)
    };
  }

  if (isFeature(geojson)) {
    const decorated = decorateFeature(geojson, 0);
    return { geojson: decorated.feature, summaries: [decorated.summary] };
  }

  return { geojson, summaries: [] };
}

function compactJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function visiblePropertyEntries(properties: JsonRecord): [string, unknown][] {
  return Object.entries(properties).filter(([key, value]) => !hiddenPropertyKeys.has(key) && value !== null && value !== undefined);
}

function providerStateLabel(configured?: boolean): string {
  return configured ? "接続済み" : "未接続";
}

export default function GeoMapApp() {
  const mapNodeRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const dataLayerRef = useRef<LeafletGeoJSON | null>(null);
  const layerByKeyRef = useRef(new Map<string, Layer>());
  const [query, setQuery] = useState(examples[0]);
  const [status, setStatus] = useState<MlitStatus | null>(null);
  const [message, setMessage] = useState("MCP設定を確認しています...");
  const [messageType, setMessageType] = useState<"info" | "error" | "success">("info");
  const [result, setResult] = useState("");
  const [lastResponse, setLastResponse] = useState<MlitQueryResponse | null>(null);
  const [features, setFeatures] = useState<FeatureSummary[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [featureFilter, setFeatureFilter] = useState("");
  const [panelTab, setPanelTab] = useState<PanelTab>("detail");
  const [isLoading, setIsLoading] = useState(false);

  const selectedFeature = features.find((feature) => feature.key === selectedKey) || features[0] || null;
  const filteredFeatures = useMemo(() => {
    const keyword = featureFilter.trim().toLowerCase();
    if (!keyword) {
      return features;
    }
    return features.filter((feature) => {
      const target = `${feature.title} ${feature.subtitle} ${feature.providerLabel} ${feature.coordinateLabel}`.toLowerCase();
      return target.includes(keyword);
    });
  }, [featureFilter, features]);

  const resultStats = useMemo(() => {
    const pointCount = features.filter((feature) => feature.geometryType === "Point").length;
    const areaCount = features.filter((feature) => feature.geometryType !== "Point").length;
    return { pointCount, areaCount };
  }, [features]);

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

      const map = leaflet.map(mapNodeRef.current, { zoomControl: false }).setView([35.681236, 139.767125], 13);
      leaflet.control.zoom({ position: "bottomright" }).addTo(map);
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

  function selectFeature(feature: FeatureSummary) {
    const map = mapRef.current;
    const layer = layerByKeyRef.current.get(feature.key);
    setSelectedKey(feature.key);

    if (!map || !layer) {
      return;
    }

    if ("getLatLng" in layer && typeof layer.getLatLng === "function") {
      const latLng = layer.getLatLng();
      map.flyTo(latLng, Math.max(map.getZoom(), 15), { duration: 0.5 });
    } else if ("getBounds" in layer && typeof layer.getBounds === "function") {
      const bounds = layer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [36, 36] });
      }
    }

    if ("openPopup" in layer && typeof layer.openPopup === "function") {
      layer.openPopup();
    }
  }

  function renderGeoJson(geojson: GeoJsonObject) {
    const map = mapRef.current;
    const leaflet = leafletRef.current;
    if (!map || !leaflet) {
      return;
    }

    if (dataLayerRef.current) {
      dataLayerRef.current.removeFrom(map);
    }
    layerByKeyRef.current.clear();

    const decorated = decorateGeoJson(geojson);
    setFeatures(decorated.summaries);
    setSelectedKey(decorated.summaries[0]?.key || null);
    setFeatureFilter("");
    setPanelTab("detail");

    const pathStyle: PathOptions = {
      color: "#1268d8",
      fillColor: "#2fb182",
      fillOpacity: 0.22,
      opacity: 0.88,
      weight: 3
    };

    const layer = leaflet.geoJSON(decorated.geojson, {
      style: () => pathStyle,
      pointToLayer(_feature, latLng) {
        return leaflet.circleMarker(latLng, {
          radius: 7,
          color: "#ffffff",
          fillColor: "#0b63ce",
          fillOpacity: 0.96,
          opacity: 1,
          weight: 2
        });
      },
      onEachFeature(feature, featureLayer) {
        const properties = (feature.properties || {}) as JsonRecord;
        const key = textValue(properties.__geoai_key);
        const { datasetId, dataId } = getDataPlatformIds(properties);
        const popupLayer = featureLayer as typeof featureLayer & {
          setPopupContent: (content: string) => void;
          on: (eventName: "popupopen" | "click", callback: () => void) => void;
        };
        let detailLoaded = false;

        if (key) {
          layerByKeyRef.current.set(key, featureLayer);
        }

        popupLayer.bindPopup(buildPopupContent(properties));
        popupLayer.on("click", () => {
          if (key) {
            setSelectedKey(key);
          }
        });

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
      map.fitBounds(bounds, { padding: [46, 46] });
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
    setLastResponse(null);
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
      setLastResponse(typedData);
      setResult(typedData.text || compactJson(typedData.raw));

      if (typedData.geojson) {
        renderGeoJson(typedData.geojson);
        setMessage(`取得成功: ${typedData.provider || "MCP"} / ${typedData.tool} を使って地図に表示しました。`);
        setMessageType("success");
      } else if (typedData.warning) {
        setFeatures([]);
        setSelectedKey(null);
        setMessage(typedData.warning);
        setMessageType("error");
      } else {
        setFeatures([]);
        setSelectedKey(null);
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
    <main className={styles.appFrame}>
      <section className={styles.commandPanel} aria-label="検索">
        <div className={styles.brandBlock}>
          <span className={styles.kicker}>MLIT MCP / GeoAI</span>
          <h1>GeoAI Map Console</h1>
        </div>

        <form className={styles.searchForm} onSubmit={handleSubmit}>
          <label htmlFor="query">自然言語クエリ</label>
          <textarea
            id="query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例: 東京駅周辺 5km の道路を国土交通データプラットフォームから検索"
          />
          <button className={styles.primaryAction} type="submit" disabled={isLoading}>
            {isLoading ? "解析・取得中" : "MCPで取得"}
          </button>
        </form>

        <div className={styles.exampleGrid} aria-label="入力例">
          {examples.map((example) => (
            <button className={styles.exampleButton} key={example} type="button" onClick={() => setQuery(example)}>
              {example}
            </button>
          ))}
        </div>

        <section className={`${styles.notice} ${styles[messageType]}`}>
          <strong>状態</strong>
          <span>{message}</span>
        </section>

        <section className={styles.providerGrid} aria-label="接続状態">
          <div>
            <span>OpenAI</span>
            <strong>{providerStateLabel(status?.openai_configured)}</strong>
          </div>
          <div>
            <span>不動産情報</span>
            <strong>{providerStateLabel(status?.providers?.reinfolib?.api_configured || status?.library_api_configured)}</strong>
          </div>
          <div>
            <span>DPF</span>
            <strong>{providerStateLabel(status?.providers?.data_platform?.api_configured || status?.data_platform_api_configured)}</strong>
          </div>
        </section>

        <section className={styles.runSummary} aria-label="取得サマリ">
          <div>
            <span>Provider</span>
            <strong>{lastResponse?.provider || "-"}</strong>
          </div>
          <div>
            <span>Tool</span>
            <strong>{lastResponse?.tool || "-"}</strong>
          </div>
          <div>
            <span>Features</span>
            <strong>{features.length}</strong>
          </div>
        </section>
      </section>

      <section className={styles.mapStage} aria-label="地図">
        <div className={styles.mapToolbar}>
          <div>
            <span>表示中</span>
            <strong>{features.length ? `${features.length}件` : "データなし"}</strong>
          </div>
          <div>
            <span>Point</span>
            <strong>{resultStats.pointCount}</strong>
          </div>
          <div>
            <span>Area/Line</span>
            <strong>{resultStats.areaCount}</strong>
          </div>
        </div>
        <div className={styles.map} ref={mapNodeRef} />
      </section>

      <aside className={styles.inspector} aria-label="結果">
        <div className={styles.inspectorHeader}>
          <div>
            <span className={styles.kicker}>Results</span>
            <h2>取得データ</h2>
          </div>
          <div className={styles.segmented}>
            <button className={panelTab === "detail" ? styles.activeSegment : ""} type="button" onClick={() => setPanelTab("detail")}>
              詳細
            </button>
            <button className={panelTab === "raw" ? styles.activeSegment : ""} type="button" onClick={() => setPanelTab("raw")}>
              JSON
            </button>
          </div>
        </div>

        {panelTab === "detail" ? (
          <>
            <div className={styles.featureSearch}>
              <label htmlFor="feature-filter">結果内検索</label>
              <input
                id="feature-filter"
                value={featureFilter}
                onChange={(event) => setFeatureFilter(event.target.value)}
                placeholder="名称、データセット、座標"
              />
            </div>

            <div className={styles.featureList} aria-label="フィーチャ一覧">
              {filteredFeatures.length ? (
                filteredFeatures.map((feature) => (
                  <button
                    className={`${styles.featureItem} ${feature.key === selectedFeature?.key ? styles.selectedFeature : ""}`}
                    key={feature.key}
                    type="button"
                    onClick={() => selectFeature(feature)}
                  >
                    <span>{feature.providerLabel}</span>
                    <strong>{feature.title}</strong>
                    <small>{feature.subtitle}</small>
                  </button>
                ))
              ) : (
                <div className={styles.emptyState}>表示できる結果はまだありません。</div>
              )}
            </div>

            <section className={styles.detailPane} aria-label="選択中データ">
              {selectedFeature ? (
                <>
                  <div className={styles.detailTitle}>
                    <span>{selectedFeature.geometryType}</span>
                    <h3>{selectedFeature.title}</h3>
                    {selectedFeature.coordinateLabel ? <p>{selectedFeature.coordinateLabel}</p> : null}
                  </div>
                  <dl className={styles.propertyGrid}>
                    {visiblePropertyEntries(selectedFeature.properties).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key}</dt>
                        <dd>{typeof value === "object" ? compactJson(value) : String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              ) : (
                <div className={styles.emptyState}>地図上のデータを取得すると詳細が表示されます。</div>
              )}
            </section>
          </>
        ) : (
          <section className={styles.rawPane} aria-label="Raw JSON">
            <pre>{result || "まだ結果はありません。"}</pre>
          </section>
        )}
      </aside>
    </main>
  );
}
