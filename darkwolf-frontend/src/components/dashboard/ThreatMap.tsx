import { useEffect, useState } from "react";
import { MapContainer, GeoJSON } from "react-leaflet";
import countries from "../../data/countries.json";
import "leaflet/dist/leaflet.css";

type CountryCount = {
  country: string;
  normalized_name: string;
  country_code: string;
  count: number;
};

const countryNameByCode = Object.fromEntries(
  (countries as any).features.map((feature: any) => [
    feature.properties["ISO3166-1-Alpha-2"],
    feature.properties.name.toLowerCase().trim(),
  ]),
) as Record<string, string>;

// Natural Earth uses -99 for France and CN-TW for Taiwan. Our API emits ISO
// alpha-2 codes, so provide explicit joins for those two map features.
const mapNameByCode: Record<string, string> = {
  ...countryNameByCode,
  FR: "france",
  TW: "taiwan",
};

const getCountryStyle = (count: number) => {
  if (count === 0) {
    return {
      fillColor: "#07131A",
      fillOpacity: 1,
      color: "#12384A",
      weight: 0.7,
    };
  }

  if (count < 10) {
    return {
      fillColor: "#0B526B",
      fillOpacity: 0.85,
      color: "#14718D",
      weight: 0.8,
    };
  }

  if (count < 50) {
    return {
      fillColor: "#008FAF",
      fillOpacity: 0.9,
      color: "#00B8D9",
      weight: 0.9,
    };
  }

  if (count < 200) {
    return {
      fillColor: "#00BFFF",
      fillOpacity: 0.92,
      color: "#4DD9FF",
      weight: 1,
    };
  }

  if (count < 400) {
    return {
      fillColor: "#3B82F6",
      fillOpacity: 0.95,
      color: "#60A5FA",
      weight: 1,
    };
  }

  return {
    fillColor: "#8B5CF6",
    fillOpacity: 0.98,
    color: "#C4B5FD",
    weight: 1.1,
  };
};

export default function ThreatMap({ group = "all", range = "30" }: { group?: string; range?: string }) {
  const [countryCounts, setCountryCounts] = useState<
    Record<string, number>
  >({});

  useEffect(() => {
    const query = new URLSearchParams({ range });
    if (group !== "all") query.set("group", group);
    fetch(`http://127.0.0.1:8000/api/v1/dashboard/countries?${query.toString()}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch country data");
        }

        return response.json();
      })
      .then((data: CountryCount[]) => {
        const counts: Record<string, number> = {};

        data.forEach((item) => {
          const countryName = mapNameByCode[item.country_code];
          if (countryName) counts[countryName] = item.count;
        });

        setCountryCounts(counts);
      })
      .catch((error) => {
        console.error(
          "Failed to load country threat data:",
          error
        );
      });
  }, [group, range]);

  return (
    <div className="threat-map-wrapper">
      <MapContainer
        center={[15, 0]}
        minZoom={1}
        maxZoom={5}
        zoom={1}
        zoomSnap={0.1}
        zoomDelta={0.5}
        maxBounds={[
          [-75, -180],
          [85, 180],
        ]}
        maxBoundsViscosity={0.8}
        worldCopyJump={false}
        style={{
          height: "100%",
          width: "100%",
        }}
        zoomControl={true}
        attributionControl={true}
      >
        <GeoJSON
          key={JSON.stringify(countryCounts)}
          data={countries as any}
          style={(feature) => {
            const normalizedName =
              feature?.properties?.name
                ?.toLowerCase()
                ?.trim();

            const count =
              countryCounts[normalizedName] || 0;

            return getCountryStyle(count);
          }}
          onEachFeature={(feature, layer) => {
            const normalizedName =
              feature?.properties?.name
                ?.toLowerCase()
                ?.trim();

            const count =
              countryCounts[normalizedName] || 0;

            layer.bindTooltip(
              `${feature?.properties?.name || "Unknown"}: ${count} victims`,
              {
                sticky: true,
                direction: "top",
                className: "darkwolf-map-tooltip",
              }
            );

            layer.on({
              mouseover: (event) => {
                const currentCount =
                  countryCounts[normalizedName] || 0;

                event.target.setStyle({
                  fillColor: "#00bfff",
                  fillOpacity: 0.75,
                  color: "#6cddff",
                  weight: 1.5,
                });

                event.target.setTooltipContent(
                  `${
                    feature?.properties?.name || "Unknown"
                  }: ${currentCount} victims`
                );

                event.target.bringToFront();
              },

              mouseout: (event) => {
                event.target.setStyle(
                  getCountryStyle(
                    currentCountForCountry()
                  )
                );
              },
            });

            function currentCountForCountry() {
              return countryCounts[normalizedName] || 0;
            }
          }}
        />
      </MapContainer>

      {/* MAP LEGEND */}

      <div className="map-legend">
        <span className="legend-label">LOW</span>

        <span
          className="legend-swatch"
          style={{ background: "#0B526B" }}
        />

        <span
          className="legend-swatch"
          style={{ background: "#008FAF" }}
        />

        <span
          className="legend-swatch"
          style={{ background: "#00BFFF" }}
        />

        <span
          className="legend-swatch"
          style={{ background: "#3B82F6" }}
        />

        <span
          className="legend-swatch"
          style={{ background: "#8B5CF6" }}
        />

        <span className="legend-label">HIGH</span>
      </div>
    </div>
  );
}
