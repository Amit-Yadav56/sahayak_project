import React from "react";

export default function ArchitectureView() {
  return (
    <div className="arch-card">
      <h2 className="checker-title">How The Project Works</h2>
      <p className="checker-subtitle">
        The application is split into three simple services that connect to each other.
      </p>

      <div className="arch-grid">
        <div className="service-card highlight">
          <h3 className="service-title">1. React Frontend</h3>
          <div className="service-port">Runs in browser (Port 3000)</div>
          <p className="service-desc">
            The user interface where citizens can search schemes, test their eligibility parameters, and view details.
          </p>
        </div>

        <div className="service-card">
          <h3 className="service-title">2. Spring Boot Backend</h3>
          <div className="service-port">Java REST API (Port 8080)</div>
          <p className="service-desc">
            Handles user accounts, JWT login tokens, profiles, bookmarks, and relays requests to the Python service.
          </p>
        </div>

        <div className="service-card">
          <h3 className="service-title">3. Python ML Service</h3>
          <div className="service-port">FastAPI (Port 8000)</div>
          <p className="service-desc">
            Runs the XGBoost eligibility scoring model, spaCy criteria parser, and semantic vector search.
          </p>
        </div>

        <div className="service-card">
          <h3 className="service-title">4. PostgreSQL</h3>
          <div className="service-port">Database (Port 5432)</div>
          <p className="service-desc">
            Stores all scheme records, user accounts, and saved items.
          </p>
        </div>
      </div>

      <div style={{ marginTop: "24px", padding: "16px", background: "#f8fafc", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
        <h4 style={{ fontSize: "0.95rem", marginBottom: "8px" }}>Simple Request Flow:</h4>
        <p style={{ fontSize: "0.88rem", color: "#475569", lineHeight: "1.6" }}>
          User fills out profile in the UI ➔ Request goes to Spring Boot (`/api/schemes/my`) ➔ Spring Boot forwards user data to Python FastAPI (`/match`) ➔ Python scores each scheme with the trained model ➔ Ranked list returns back to the user on screen.
        </p>
      </div>
    </div>
  );
}
