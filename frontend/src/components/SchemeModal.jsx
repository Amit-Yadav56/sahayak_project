import React from "react";

/**
 * Splits any pipe-separated string into styled, animated sections.
 * Segments ending with ":" become uppercase label headings.
 * Everything else is rendered as a paragraph.
 */
function PipeSections({ text }) {
  if (!text) return null;

  const parts = text.split(" | ").map(s => s.trim()).filter(Boolean);

  if (parts.length <= 1) {
    return <p style={{ margin: 0, lineHeight: "1.7" }}>{text}</p>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {parts.map((part, i) => {
        const isLabel = part.endsWith(":");
        return (
          <div key={i} style={{ animation: "fadeSlideIn 0.3s ease both", animationDelay: `${i * 0.05}s` }}>
            {i > 0 && (
              <div style={{
                height: "1px",
                background: "linear-gradient(to right, transparent, var(--border), transparent)",
                marginBottom: "10px",
                opacity: 0.6,
              }} />
            )}
            {isLabel ? (
              <span style={{
                fontWeight: 600,
                color: "var(--text-secondary)",
                fontSize: "0.8rem",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}>
                {part.slice(0, -1)}
              </span>
            ) : (
              <p style={{ margin: 0, lineHeight: "1.7", color: "var(--text-primary)" }}>{part}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function SchemeModal({ scheme, onClose }) {
  if (!scheme) return null;

  const howToApply = scheme.howToApply || scheme.how_to_apply;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>

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
          <div className="modal-section-body">
            <PipeSections text={scheme.description} />
          </div>
        </div>

        <div className="modal-section">
          <div className="modal-section-title">Eligibility Criteria</div>
          <div className="modal-section-body">
            {scheme.eligibilitySummary || scheme.eligibility_summary ? (
              <ul style={{ paddingLeft: "18px", margin: 0, lineHeight: "1.6" }}>
                {(scheme.eligibilitySummary || scheme.eligibility_summary)
                  .split(";")
                  .map(item => item.trim())
                  .filter(Boolean)
                  .map((item, idx) => (
                    <li key={idx} style={{ marginBottom: "6px" }}>{item}</li>
                  ))}
              </ul>
            ) : (
              <p style={{ color: "var(--text-muted)", fontStyle: "italic", margin: 0 }}>
                Open to eligible citizens meeting basic category guidelines. Refer to the official portal for complete documentation.
              </p>
            )}
          </div>
        </div>

        {(scheme.documentsRequired || scheme.documents_required) && (
          <div className="modal-section">
            <div className="modal-section-title">Required Documents</div>
            <div className="modal-section-body">
              <ul style={{ paddingLeft: "18px", margin: 0, lineHeight: "1.6" }}>
                {(scheme.documentsRequired || scheme.documents_required)
                  .split(";")
                  .map(item => item.trim())
                  .filter(Boolean)
                  .map((item, idx) => (
                    <li key={idx} style={{ marginBottom: "6px" }}>{item}</li>
                  ))}
              </ul>
            </div>
          </div>
        )}

        {howToApply && (
          <div className="modal-section">
            <div className="modal-section-title">How to Apply</div>
            <div className="modal-section-body">
              <PipeSections text={howToApply} />
            </div>
          </div>
        )}

        <div style={{ marginTop: "24px", display: "flex", justifyContent: "flex-end", gap: "12px" }}>
          <button type="button" className="btn-sm btn-outline" onClick={onClose}>Close</button>
          <a href={scheme.applicationUrl} target="_blank" rel="noreferrer" className="btn-sm btn-primary">
            Go to Official Portal ↗
          </a>
        </div>
      </div>
    </div>
  );
}
