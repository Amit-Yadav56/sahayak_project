import React, { useState, useEffect, useCallback } from "react";
import Navbar from "./components/Navbar.jsx";
import Hero from "./components/Hero.jsx";
import SchemeList from "./components/SchemeList.jsx";
import EligibilityChecker from "./components/EligibilityChecker.jsx";
import ArchitectureView from "./components/ArchitectureView.jsx";
import SchemeModal from "./components/SchemeModal.jsx";
import AuthModal from "./components/AuthModal.jsx";
import ProfileForm from "./components/ProfileForm.jsx";
import MySchemes from "./components/MySchemes.jsx";
import { INITIAL_SCHEMES } from "./data/schemes.js";
import {
  fetchAllSchemes,
  semanticSearch,
  getMe,
  logout,
  isLoggedIn,
  fetchSavedSchemes,
  saveScheme,
  unsaveScheme,
} from "./api.js";

export default function App() {
  // ── Auth state ───────────────────────────────────────────────────
  const [user, setUser] = useState(null);            // { name, email } or null
  const [showAuth, setShowAuth] = useState(false);   // AuthModal visibility

  // ── Tab ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState("schemes");

  // ── Schemes (explore) ────────────────────────────────────────────
  const [schemes, setSchemes] = useState(INITIAL_SCHEMES);
  const [displayedSchemes, setDisplayedSchemes] = useState(INITIAL_SCHEMES);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [apiAvailable, setApiAvailable] = useState(null); // null | true | false

  // ── Scheme detail modal ──────────────────────────────────────────
  const [selectedScheme, setSelectedScheme] = useState(null);

  // ── Saved schemes ────────────────────────────────────────────────
  // For logged-out users: falls back to localStorage.
  // For logged-in users: synced with backend via /api/saved.
  const [savedSchemeIds, setSavedSchemeIds] = useState(() => {
    try {
      const raw = localStorage.getItem("sahayak_saved_schemes");
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter(id => typeof id === "number") : [];
    } catch { return []; }
  });

  // ── My Schemes refresh key ───────────────────────────────────────
  const [profileRefreshKey, setProfileRefreshKey] = useState(0);

  // ── Restore session + load saved schemes from API ────────────────
  useEffect(() => {
    if (!isLoggedIn()) return;
    getMe()
      .then(userData => {
        setUser(userData);
        // load saved scheme IDs from the backend
        return fetchSavedSchemes();
      })
      .then(saved => {
        if (Array.isArray(saved)) {
          setSavedSchemeIds(saved.map(s => s.schemeId ?? s.id ?? s.scheme?.id).filter(Boolean));
        }
      })
      .catch(() => {/* token expired or backend down — stay as-is */});
  }, []);

  // ── Persist to localStorage for logged-out users ─────────────────
  useEffect(() => {
    try {
      localStorage.setItem("sahayak_saved_schemes", JSON.stringify(savedSchemeIds));
    } catch { /* ignore */ }
  }, [savedSchemeIds]);

  // ── Load live schemes from API on mount ─────────────────────────
  useEffect(() => {
    fetchAllSchemes()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setSchemes(data);
          setDisplayedSchemes(data);
          setApiAvailable(true);
        }
      })
      .catch(() => setApiAvailable(false));
  }, []);

  // ── Category filter applied on top of search results ────────────
  const categoryFiltered = displayedSchemes.filter((scheme) => {
    if (activeTab === "saved" && !savedSchemeIds.includes(scheme.id)) return false;
    if (selectedCategory !== "All" && scheme.category !== selectedCategory) return false;
    return true;
  });

  // ── Semantic search ──────────────────────────────────────────────
  const handleSearch = useCallback(async (query) => {
    if (!query.trim()) {
      setDisplayedSchemes(schemes);
      setSearchError(null);
      return;
    }

    setIsSearching(true);
    setSearchError(null);

    // Try semantic search via Spring Boot → FastAPI
    if (apiAvailable !== false) {
      try {
        const result = await semanticSearch(query, 20);
        const names = new Set((result.results || []).map((r) => r.name));
        // Prefer full local records; supplement with ML-only stubs
        const matched = schemes.filter((s) => names.has(s.name));
        const mlOnly = (result.results || [])
          .filter((r) => !matched.some((s) => s.name === r.name))
          .map((r, i) => ({
            id: `ml-${i}`, name: r.name, category: r.category,
            state: r.state, description: r.snippet, ministry: "",
            benefitType: "", benefitAmount: "", eligibilitySummary: r.snippet,
            applicationUrl: "#", criteria: {},
          }));

        // Keep ML ranking order
        const ordered = [
          ...(result.results || [])
            .map((r) => matched.find((s) => s.name === r.name))
            .filter(Boolean),
          ...mlOnly,
        ];

        setDisplayedSchemes(ordered.length > 0 ? ordered : schemes);
        setApiAvailable(true);
        setIsSearching(false);
        return;
      } catch {
        setApiAvailable(false);
      }
    }

    // Fallback: local keyword search
    const q = query.toLowerCase();
    const local = schemes.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.description || "").toLowerCase().includes(q) ||
        (s.ministry || "").toLowerCase().includes(q) ||
        (s.category || "").toLowerCase().includes(q)
    );
    setDisplayedSchemes(local.length > 0 ? local : schemes);
    if (apiAvailable === false) {
      setSearchError("Semantic search unavailable (backend offline). Showing local keyword results.");
    }
    setIsSearching(false);
  }, [schemes, apiAvailable]);

  // ── Auth handlers ────────────────────────────────────────────────
  function handleAuthSuccess(userData) {
    setUser(userData);
    setShowAuth(false);
    setActiveTab("my-schemes");
  }

  function handleLogout() {
    logout();
    setUser(null);
    setSavedSchemeIds([]);
    setActiveTab("schemes");
  }

  // ── Save toggle — calls the backend API when logged in ───────────
  async function handleToggleSave(schemeId) {
    const isSaved = savedSchemeIds.includes(schemeId);
    // Optimistic UI update
    setSavedSchemeIds(prev => isSaved ? prev.filter(id => id !== schemeId) : [...prev, schemeId]);

    if (isLoggedIn()) {
      try {
        if (isSaved) await unsaveScheme(schemeId);
        else await saveScheme(schemeId);
      } catch {
        // Rollback on failure
        setSavedSchemeIds(prev => isSaved ? [...prev, schemeId] : prev.filter(id => id !== schemeId));
      }
    }
  }

  // ── Profile saved → re-fetch My Schemes ─────────────────────────
  function handleProfileSaved() {
    setProfileRefreshKey((k) => k + 1);
    setActiveTab("my-schemes");
  }

  // ── Render ───────────────────────────────────────────────────────
  return (
    <div className="app">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        savedCount={savedSchemeIds.length}
        user={user}
        onAuthClick={() => setShowAuth(true)}
        onLogout={handleLogout}
      />

      {/* Hero search bar — only on Explore tab */}
      {activeTab === "schemes" && (
        <Hero
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onSearch={handleSearch}
          isSearching={isSearching}
        />
      )}

      <main className="container" style={{ padding: "32px 20px" }}>

        {/* ── Offline banner ── */}
        {apiAvailable === false && (
          <div style={{
            background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: 8,
            padding: "10px 16px", marginBottom: 20, fontSize: "0.85rem", color: "#92400e"
          }}>
            ⚠️ <strong>Backend offline</strong> — showing local sample data.
            Start Spring Boot on port 8080 for live data &amp; semantic search.
          </div>
        )}

        {/* ── Search degraded banner ── */}
        {searchError && (
          <div style={{
            background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: 8,
            padding: "10px 16px", marginBottom: 20, fontSize: "0.85rem", color: "#92400e"
          }}>
            ℹ️ {searchError}
          </div>
        )}

        {/* ── Explore Schemes ── */}
        {activeTab === "schemes" && (
          <SchemeList
            schemes={categoryFiltered}
            selectedCategory={selectedCategory}
            setSelectedCategory={setSelectedCategory}
            onSelectScheme={setSelectedScheme}
            savedSchemeIds={savedSchemeIds}
            onToggleSave={handleToggleSave}
          />
        )}

        {/* ── My Schemes (ML personalised) ── */}
        {activeTab === "my-schemes" && user && (
          <div>
            {/* Prompt to complete profile if not done */}
            <div style={{ marginBottom: 24 }}>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: 12 }}>
                Not seeing relevant results?{" "}
                <button
                  style={{ background: "none", border: "none", color: "var(--primary)", cursor: "pointer", fontWeight: 600 }}
                  onClick={() => setActiveTab("profile")}
                >
                  Update your profile →
                </button>
              </p>
            </div>
            <MySchemes
              onSelectScheme={setSelectedScheme}
              refreshKey={profileRefreshKey}
            />
          </div>
        )}

        {/* ── My Schemes — not logged in ── */}
        {activeTab === "my-schemes" && !user && (
          <div style={{ textAlign: "center", padding: "60px 20px" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16 }}>🔒</div>
            <h2 style={{ marginBottom: 8 }}>Sign in to get personalised matches</h2>
            <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
              The ML model needs your socioeconomic profile to rank schemes by eligibility.
            </p>
            <button className="btn-sm btn-primary" style={{ padding: "12px 28px", fontSize: "1rem" }}
              onClick={() => setShowAuth(true)}>
              Sign In / Register
            </button>
          </div>
        )}

        {/* ── Profile ── */}
        {activeTab === "profile" && user && (
          <ProfileForm onProfileSaved={handleProfileSaved} />
        )}

        {/* ── Saved Schemes ── */}
        {activeTab === "saved" && (
          <div>
            <h2 className="checker-title" style={{ marginBottom: 16 }}>
              Saved Schemes ({savedSchemeIds.length})
            </h2>
            <SchemeList
              schemes={categoryFiltered}
              selectedCategory="All"
              setSelectedCategory={() => {}}
              onSelectScheme={setSelectedScheme}
              savedSchemeIds={savedSchemeIds}
              onToggleSave={handleToggleSave}
            />
          </div>
        )}

        {/* ── Eligibility Checker (local) ── */}
        {activeTab === "eligibility" && (
          <EligibilityChecker
            schemes={schemes}
            onSelectScheme={setSelectedScheme}
          />
        )}

        {/* ── Architecture ── */}
        {activeTab === "architecture" && <ArchitectureView />}
      </main>

      {/* ── Scheme detail modal ── */}
      <SchemeModal
        scheme={selectedScheme}
        onClose={() => setSelectedScheme(null)}
      />

      {/* ── Auth modal ── */}
      {showAuth && (
        <AuthModal
          onSuccess={handleAuthSuccess}
          onClose={() => setShowAuth(false)}
        />
      )}

      <footer className="footer">
        <div className="container">
          <p>
            <strong>Sahayak</strong> — Open welfare scheme discovery &amp; eligibility platform.
          </p>
          <p style={{ marginTop: 6, fontSize: "0.8rem", color: "#94a3b8" }}>
            React + Vite • Spring Boot :8080 • FastAPI ML :8000 • PostgreSQL
            {apiAvailable === true && (
              <span style={{ color: "#4ade80", marginLeft: 10 }}>● API connected</span>
            )}
            {apiAvailable === false && (
              <span style={{ color: "#f87171", marginLeft: 10 }}>● API offline</span>
            )}
          </p>
        </div>
      </footer>
    </div>
  );
}
