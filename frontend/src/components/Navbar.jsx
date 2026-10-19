import React from "react";

export default function Navbar({
  activeTab, setActiveTab,
  savedCount,
  user,           // { name, email } or null
  onAuthClick,    // open auth modal
  onLogout,
}) {
  return (
    <header className="navbar">
      <div className="container nav-content">
        <div className="brand">
          <span>🇮🇳 Sahayak</span>
          <span className="brand-badge">Welfare Schemes</span>
        </div>

        <nav className="nav-links">
          <button
            className={`nav-link ${activeTab === "schemes" ? "active" : ""}`}
            onClick={() => setActiveTab("schemes")}
          >
            Explore
          </button>

          {user && (
            <button
              className={`nav-link ${activeTab === "my-schemes" ? "active" : ""}`}
              onClick={() => setActiveTab("my-schemes")}
            >
              My Schemes ✨
            </button>
          )}

          <button
            className={`nav-link ${activeTab === "eligibility" ? "active" : ""}`}
            onClick={() => setActiveTab("eligibility")}
          >
            Eligibility Check
          </button>

          <button
            className={`nav-link ${activeTab === "saved" ? "active" : ""}`}
            onClick={() => setActiveTab("saved")}
          >
            Saved ({savedCount})
          </button>

          <button
            className={`nav-link ${activeTab === "architecture" ? "active" : ""}`}
            onClick={() => setActiveTab("architecture")}
          >
            About
          </button>
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {user ? (
            <>
              <button
                className={`nav-link ${activeTab === "profile" ? "active" : ""}`}
                style={{ fontSize: "0.8rem" }}
                onClick={() => setActiveTab("profile")}
              >
                👤 {user.name?.split(" ")[0] || user.email}
              </button>
              <button
                className="btn-sm btn-outline"
                style={{ fontSize: "0.78rem", padding: "4px 12px" }}
                onClick={onLogout}
              >
                Sign Out
              </button>
            </>
          ) : (
            <button
              className="btn-sm btn-primary"
              style={{ fontSize: "0.85rem", padding: "6px 16px" }}
              onClick={onAuthClick}
            >
              Sign In / Register
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
