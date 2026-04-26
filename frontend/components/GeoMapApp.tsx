"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { GeoJSON as LeafletGeoJSON, Map as LeafletMap } from "leaflet";
import type { GeoJsonObject } from "geojson";
import styles from "./GeoMapApp.module.css";

type MlitStatus = {
  configured: boolean;
  command_env: string;
  tool_env: string;
};

type MlitQueryResponse = {
  query: string;
  tool: string;
  arguments: Record<string, unknown>;
  geojson: GeoJsonObject | null;
  text: string;
  raw: Record<string, unknown>;
};

const examples = [
  "東京駅周辺の地価公示ポイント",
  "新宿駅周辺の用途地域",
  "35.681236,139.767125 周辺の都市計画"
];

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
          setMessage(`${data.command_env} が未設定です。バックエンド起動時に国交省MCPサーバーの起動コマンドを設定してください。`);
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
        const properties = feature.properties || {};
        const title =
          properties.name ||
          properties.title ||
          properties.Name ||
          properties["名称"] ||
          "MLIT data";
        featureLayer.bindPopup(String(title));
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
        setMessage(`取得成功: ${typedData.tool} を使って地図に表示しました。`);
        setMessageType("success");
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
              command: {status.command_env} / tool: {status.tool_env}
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
