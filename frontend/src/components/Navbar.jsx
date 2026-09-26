import React from "react";

export default function Navbar({ activeTab, setActiveTab, savedCount }) {
  return (
    <header className="navbar">
      <div className="container nav-content">
        <div className="brand">
          <span>🇮🇳 Sahayak</span>
          <span className="brand-badge">Whost Showcase</span>
        </div>
        <nav className="nav-links">
          <button
            className={`nav-link ${activeTab === "schemes" ? "active" : ""}`}
            onClick={() => setActiveTab("schemes")}
          >
            Explore Schemes
          </button>
          <button
            className={`nav-link ${activeTab === "eligibility" ? "active" : ""}`}
            onClick={() => setActiveTab("eligibility")}
          >
            Check Eligibility
          </button>
          <button
            className={`nav-link ${activeTab === "architecture" ? "active" : ""}`}
            onClick={() => setActiveTab("architecture")}
          >
            Architecture & Services
          </button>
          <button
            className={`nav-link ${activeTab === "saved" ? "active" : ""}`}
            onClick={() => setActiveTab("saved")}
          >
            Saved ({savedCount})
          </button>
        </nav>
      </div>
    </header>
  );
}
