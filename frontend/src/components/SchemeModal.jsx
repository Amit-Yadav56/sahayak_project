import React from "react";

export default function SchemeModal({ scheme, onClose }) {
  if (!scheme) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>
          ✕
        </button>

        <span className="scheme-category-badge">{scheme.category}</span>
        <h2 style={{ fontSize: "1.4rem", marginTop: "10px", marginBottom: "6px" }}>
          {scheme.name}
        </h2>
        <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: "16px" }}>
          {scheme.ministry} • {scheme.state || "Central Scheme"}
        </div>

        <div className="scheme-benefit">
          <div className="benefit-label">Scheme Benefits</div>
          <div className="benefit-val">{scheme.benefitAmount}</div>
          <div style={{ fontSize: "0.85rem", color: "#166534", marginTop: "4px" }}>
            Type: {scheme.benefitType}
          </div>
        </div>

        <div className="modal-section">
          <div className="modal-section-title">Description</div>
          <div className="modal-section-body">{scheme.description}</div>
        </div>

        <div className="modal-section">
          <div className="modal-section-title">Eligibility Criteria</div>
          <div className="modal-section-body">{scheme.eligibilitySummary}</div>
        </div>

        {scheme.documentsRequired && (
          <div className="modal-section">
            <div className="modal-section-title">Required Documents</div>
            <div className="modal-section-body">{scheme.documentsRequired}</div>
          </div>
        )}

        {scheme.howToApply && (
          <div className="modal-section">
            <div className="modal-section-title">How to Apply</div>
            <div className="modal-section-body">{scheme.howToApply}</div>
          </div>
        )}

        <div style={{ marginTop: "24px", display: "flex", justifyContent: "flex-end", gap: "12px" }}>
          <button type="button" className="btn-sm btn-outline" onClick={onClose}>
            Close
          </button>
          <a
            href={scheme.applicationUrl}
            target="_blank"
            rel="noreferrer"
            className="btn-sm btn-primary"
          >
            Go to Official Portal ↗
          </a>
        </div>
      </div>
    </div>
  );
}
