import React, { useState, useEffect } from "react";
import Navbar from "./components/Navbar.jsx";
import Hero from "./components/Hero.jsx";
import SchemeList from "./components/SchemeList.jsx";
import EligibilityChecker from "./components/EligibilityChecker.jsx";
import ArchitectureView from "./components/ArchitectureView.jsx";
import SchemeModal from "./components/SchemeModal.jsx";
import { INITIAL_SCHEMES } from "./data/schemes.js";

export default function App() {
  const [activeTab, setActiveTab] = useState("schemes");
  const [schemes, setSchemes] = useState(INITIAL_SCHEMES);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedScheme, setSelectedScheme] = useState(null);
  const [savedSchemeIds, setSavedSchemeIds] = useState(() => {
    try {
      const stored = localStorage.getItem("sahayak_saved_schemes");
      return stored ? JSON.parse(stored) : [1, 2];
    } catch (e) {
      return [1, 2];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem("sahayak_saved_schemes", JSON.stringify(savedSchemeIds));
    } catch (e) {
      console.error(e);
    }
  }, [savedSchemeIds]);

  const handleToggleSave = (schemeId) => {
    setSavedSchemeIds((prev) =>
      prev.includes(schemeId)
        ? prev.filter((id) => id !== schemeId)
        : [...prev, schemeId]
    );
  };

  // Filter schemes based on search, category, and active tab
  const filteredSchemes = schemes.filter((scheme) => {
    if (activeTab === "saved" && !savedSchemeIds.includes(scheme.id)) {
      return false;
    }

    const matchesCategory =
      selectedCategory === "All" || scheme.category === selectedCategory;

    const matchesSearch =
      !searchQuery.trim() ||
      scheme.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      scheme.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      scheme.ministry.toLowerCase().includes(searchQuery.toLowerCase()) ||
      scheme.category.toLowerCase().includes(searchQuery.toLowerCase());

    return matchesCategory && matchesSearch;
  });

  return (
    <div className="app">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        savedCount={savedSchemeIds.length}
      />

      {activeTab === "schemes" && (
        <Hero
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onSearch={(query) => setSearchQuery(query)}
        />
      )}

      <main className="container" style={{ padding: "32px 20px" }}>
        {activeTab === "schemes" && (
          <SchemeList
            schemes={filteredSchemes}
            selectedCategory={selectedCategory}
            setSelectedCategory={setSelectedCategory}
            onSelectScheme={(scheme) => setSelectedScheme(scheme)}
            savedSchemeIds={savedSchemeIds}
            onToggleSave={handleToggleSave}
          />
        )}

        {activeTab === "saved" && (
          <div>
            <h2 className="checker-title" style={{ marginBottom: "16px" }}>
              Saved Schemes ({savedSchemeIds.length})
            </h2>
            <SchemeList
              schemes={filteredSchemes}
              selectedCategory="All"
              setSelectedCategory={() => {}}
              onSelectScheme={(scheme) => setSelectedScheme(scheme)}
              savedSchemeIds={savedSchemeIds}
              onToggleSave={handleToggleSave}
            />
          </div>
        )}

        {activeTab === "eligibility" && (
          <EligibilityChecker
            schemes={schemes}
            onSelectScheme={(scheme) => setSelectedScheme(scheme)}
          />
        )}

        {activeTab === "architecture" && <ArchitectureView />}
      </main>

      <SchemeModal
        scheme={selectedScheme}
        onClose={() => setSelectedScheme(null)}
      />

      <footer className="footer">
        <div className="container">
          <p>
            <strong>Sahayak</strong> — Open welfare scheme discovery & eligibility platform.
          </p>
          <p style={{ marginTop: "6px", fontSize: "0.8rem", color: "#94a3b8" }}>
            Frontend React Client • Spring Boot 8080 • FastAPI ML 8000
          </p>
        </div>
      </footer>
    </div>
  );
}
