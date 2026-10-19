import React, { useState, useEffect, useCallback } from "react";
import { getMySchemes } from "../api.js";

const STATUS_META = {
  ELIGIBLE:        { label: "Eligible",         color: "#166534", bg: "#dcfce7", border: "#86efac" },
  LIKELY_ELIGIBLE: { label: "Likely Eligible",  color: "#92400e", bg: "#fef3c7", border: "#fcd34d" },
  CHECK_REQUIRED:  { label: "Check Required",   color: "#1e40af", bg: "#dbeafe", border: "#93c5fd" },
  NOT_ELIGIBLE:    { label: "Not Eligible",      color: "#991b1b", bg: "#fee2e2", border: "#fca5a5" },
};

const CRITERIA_LABELS = {
  age:        "Age",
  income:     "Income",
  gender:     "Gender",
  caste:      "Caste",
  state:      "State",
  disability: "Disability",
};

/**
 * MySchemes — shows ML-personalised scheme matches for the logged-in user.
 * Props:
 *   onSelectScheme(scheme)   open the detail modal
 *   refreshKey               bump this to force a re-fetch (after profile save)
 */
export default function MySchemes({ onSelectScheme, refreshKey }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [minStatus, setMinStatus] = useState("LIKELY_ELIGIBLE");
  const [topN, setTopN] = useState(20);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getMySchemes(topN, minStatus)
      .then(setResults)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [topN, minStatus, refreshKey]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text-muted)" }}>
        <div style={{ fontSize: "2rem", marginBottom: 12 }}>🤖</div>
        <p style={{ fontSize: "1.1rem", fontWeight: 500 }}>Running eligibility model…</p>
        <p style={{ fontSize: "0.85rem", marginTop: 6 }}>
          The ML service is scoring all schemes against your profile — usually under 2 seconds.
        </p>
      </div>
    );
  }

  if (error) {
    const isProfile = error.toLowerCase().includes("profile");
    return (
      <div style={{
        background: "#fef3c7", border: "1px solid #f59e0b",
        borderRadius: 10, padding: "24px 28px", textAlign: "center"
      }}>
        <div style={{ fontSize: "2rem", marginBottom: 10 }}>⚠️</div>
        <p style={{ fontWeight: 600, color: "#92400e", marginBottom: 8 }}>
          {isProfile ? "Profile not found" : "Could not load your schemes"}
        </p>
        <p style={{ fontSize: "0.88rem", color: "#78350f" }}>
          {isProfile
            ? "Please complete your socioeconomic profile first so the model can match schemes for you."
            : error}
        </p>
      </div>
    );
  }

  if (!results) return null;

  const { total_schemes, returned, elapsed_ms, results: schemes } = results;

  return (
    <div>
      {/* Header + controls */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 20 }}>
        <div style={{ flex: 1 }}>
          <h2 className="checker-title" style={{ marginBottom: 4 }}>
            Your Personalised Scheme Matches
          </h2>
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
            Scored {total_schemes.toLocaleString()} schemes in {elapsed_ms} ms —
            showing <strong>{returned}</strong> matches
          </p>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <select
            className="form-control"
            style={{ width: "auto", fontSize: "0.85rem" }}
            value={minStatus}
            onChange={(e) => setMinStatus(e.target.value)}
          >
            <option value="ELIGIBLE">Eligible only</option>
            <option value="LIKELY_ELIGIBLE">Likely Eligible+</option>
            <option value="CHECK_REQUIRED">Check Required+</option>
          </select>

          <select
            className="form-control"
            style={{ width: "auto", fontSize: "0.85rem" }}
            value={topN}
            onChange={(e) => setTopN(Number(e.target.value))}
          >
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
            <option value={50}>Top 50</option>
          </select>

          <button className="btn-sm btn-outline" onClick={load}>↻ Refresh</button>
        </div>
      </div>

      {schemes.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
          No schemes matched your current filter. Try lowering the minimum status.
        </div>
      ) : (
        <div className="schemes-grid">
          {schemes.map((item) => {
            const meta = STATUS_META[item.status] || STATUS_META["CHECK_REQUIRED"];
            const scorePercent = Math.round(item.score * 100);
            const criteria = item.matched_criteria || {};

            return (
              <div key={item.scheme_id} className="scheme-card">
                {/* Status badge + score */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <span style={{
                    fontSize: "0.75rem", fontWeight: 700, padding: "3px 10px",
                    borderRadius: 20, background: meta.bg, color: meta.color, border: `1px solid ${meta.border}`
                  }}>
                    {meta.label}
                  </span>
                  <span style={{
                    fontSize: "0.78rem", fontWeight: 700, color: "var(--text-muted)",
                    background: "#f1f5f9", borderRadius: 20, padding: "3px 10px"
                  }}>
                    {scorePercent}% match
                  </span>
                </div>

                {/* Score bar */}
                <div style={{
                  height: 4, borderRadius: 2, background: "#e2e8f0", marginBottom: 12, overflow: "hidden"
                }}>
                  <div style={{
                    width: `${scorePercent}%`, height: "100%",
                    background: scorePercent >= 80 ? "#22c55e" : scorePercent >= 50 ? "#f59e0b" : "#ef4444",
                    borderRadius: 2, transition: "width 0.6s ease"
                  }} />
                </div>

                <span className="scheme-category-badge" style={{ marginBottom: 8, display: "inline-block" }}>
                  {item.category}
                </span>
                <h3 className="scheme-title">{item.name}</h3>
                <div className="scheme-ministry">{item.ministry}</div>

                {item.state && (
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: 2 }}>
                    📍 {item.state}
                  </div>
                )}

                {/* Benefit */}
                <div className="scheme-benefit" style={{ marginTop: 10 }}>
                  <div className="benefit-label">Benefit</div>
                  <div className="benefit-val">{item.benefit_amount || "—"}</div>
                  {item.benefit_type && (
                    <div style={{ fontSize: "0.78rem", color: "#166534", marginTop: 2 }}>{item.benefit_type}</div>
                  )}
                </div>

                {/* Criteria indicators */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, margin: "10px 0" }}>
                  {Object.entries(criteria).map(([key, val]) => {
                    if (val === null) return null; // no constraint — skip
                    return (
                      <span key={key} style={{
                        fontSize: "0.7rem", padding: "2px 7px", borderRadius: 10,
                        background: val ? "#dcfce7" : "#fee2e2",
                        color: val ? "#166534" : "#991b1b",
                        border: `1px solid ${val ? "#86efac" : "#fca5a5"}`
                      }}>
                        {val ? "✓" : "✗"} {CRITERIA_LABELS[key] || key}
                      </span>
                    );
                  })}
                </div>

                {/* Description snippet */}
                {item.description && (
                  <p className="scheme-desc" style={{ fontSize: "0.82rem" }}>
                    {item.description.length > 120
                      ? item.description.slice(0, 120) + "…"
                      : item.description}
                  </p>
                )}

                <div className="scheme-footer">
                  <button
                    type="button"
                    className="btn-sm btn-outline"
                    onClick={() => onSelectScheme?.({
                      name: item.name,
                      category: item.category,
                      ministry: item.ministry,
                      state: item.state,
                      benefitType: item.benefit_type,
                      benefitAmount: item.benefit_amount,
                      description: item.description,
                      eligibilitySummary: item.eligibility_summary,
                      documentsRequired: item.documents_required,
                      howToApply: item.how_to_apply,
                      applicationUrl: item.application_url,
                    })}
                  >
                    Details
                  </button>
                  {item.application_url && item.application_url !== "#" && (
                    <a href={item.application_url} target="_blank" rel="noreferrer"
                      className="btn-sm btn-primary">
                      Apply Now ↗
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
