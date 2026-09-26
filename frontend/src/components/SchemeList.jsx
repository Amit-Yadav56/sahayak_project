import React from "react";
import { CATEGORIES } from "../data/schemes.js";

export default function SchemeList({
  schemes,
  selectedCategory,
  setSelectedCategory,
  onSelectScheme,
  savedSchemeIds,
  onToggleSave
}) {
  return (
    <div>
      <div className="category-bar">
        {CATEGORIES.map(function(cat) {
          const isActive = selectedCategory === cat;
          return (
            <button
              key={cat}
              className={"category-btn" + (isActive ? " active" : "")}
              onClick={() => setSelectedCategory(cat)}
            >
              {cat}
            </button>
          );
        })}
      </div>

      <p style={{ margin: "14px 0", color: "#64748b", fontSize: "0.9rem" }}>
        Found {schemes.length} schemes in <strong>{selectedCategory}</strong>
      </p>

      {schemes.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px", color: "#94a3b8" }}>
          No schemes match your filter. Try picking a different category or search term.
        </div>
      ) : (
        <div className="schemes-grid">
          {schemes.map(function(scheme) {
            const isSaved = savedSchemeIds.includes(scheme.id);
            return (
              <div key={scheme.id} className="scheme-card">
                <div className="scheme-header">
                  <span className="scheme-category-badge">{scheme.category}</span>
                  <button
                    className={"scheme-save-btn" + (isSaved ? " saved" : "")}
                    onClick={() => onToggleSave(scheme.id)}
                    title={isSaved ? "Saved" : "Save this scheme"}
                  >
                    ★
                  </button>
                </div>

                <h3 className="scheme-title">{scheme.name}</h3>
                <div className="scheme-ministry">{scheme.ministry}</div>

                <div className="scheme-benefit">
                  <div className="benefit-label">Benefit</div>
                  <div className="benefit-val">{scheme.benefitAmount}</div>
                </div>

                <p className="scheme-desc">{scheme.description}</p>

                <div className="scheme-footer">
                  <button
                    type="button"
                    className="btn-sm btn-outline"
                    onClick={() => onSelectScheme(scheme)}
                  >
                    Details
                  </button>
                  <a
                    href={scheme.applicationUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-sm btn-primary"
                  >
                    Apply Now
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
