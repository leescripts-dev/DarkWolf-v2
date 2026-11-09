import { useEffect, useState } from "react";
import "flag-icons/css/flag-icons.min.css";
import countryGeoJson from "../../data/countries.json";

type CountryCount = {
  country: string;
  normalized_name: string;
  country_code: string;
  count: number;
};

const countryNames = Object.fromEntries(
  (countryGeoJson as any).features.map((feature: any) => [
    feature.properties["ISO3166-1-Alpha-2"],
    feature.properties.name,
  ]),
) as Record<string, string>;

const countryNameOverrides: Record<string, string> = {
  FR: "France",
  TW: "Taiwan",
};

export default function CountryChart({ group = "all", range = "30" }: { group?: string; range?: string }) {
  const [countries, setCountries] = useState<CountryCount[]>([]);
  const [loading, setLoading] = useState(true);

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
        setCountries(data.slice(0, 8));
      })
      .catch((error) => {
        console.error("Failed to load country chart:", error);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [group, range]);

  if (loading) {
    return (
      <div className="country-chart">
        <div className="chart-loading">
          Loading country data...
        </div>
      </div>
    );
  }

  const maxCount = countries[0]?.count || 1;

  return (
    <div className="country-chart">
      {countries.map((item) => {
        const countryCode = item.country_code.toLowerCase();
        const countryLabel = countryNames[item.country_code]
          || countryNameOverrides[item.country_code]
          || item.country;
        const width = (item.count / maxCount) * 100;

        return (
          <div
            className="country-row"
            key={countryCode}
          >
            <div className="country-row-header">
              <span className="country-name">
                <span
                  className={`fi fi-${countryCode} country-flag`}
                  aria-label={countryLabel}
                  title={countryLabel}
                />

                <span className="country-label">
                  {countryLabel}
                </span>
              </span>

              <span className="country-count">
                {item.count}
              </span>
            </div>

            <div className="country-bar-track">
              <div
                className="country-bar"
                style={{
                  width: `${width}%`,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
