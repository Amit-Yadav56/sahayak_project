import React from "react";

export default function Hero({ searchQuery, setSearchQuery, onSearch, isSearching }) {
  const quickSearches = [
    "PM Kisan",
    "Health insurance",
    "Rural housing",
    "SC Scholarship",
    "Solar pump"
  ];

  return (
    <section className="hero">
      <div className="container">
        <h1 className="hero-title">
          Find Government Schemes You Qualify For
        </h1>
        <p className="hero-subtitle">
          Search across central and state welfare programs, check your eligibility rules, and get direct application links.
        </p>

        <div className="search-wrapper">
          <form
            className="search-input-group"
            onSubmit={function(e) {
              e.preventDefault();
              onSearch(searchQuery);
            }}
          >
            <input
              type="text"
              className="search-input"
              placeholder="Search by keyword (e.g. farmer, pension, scholarship, loan)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <button type="submit" className="search-btn" disabled={isSearching}>
              {isSearching ? "Searching…" : "Search"}
            </button>
          </form>

          <div className="quick-prompts">
            <span>Quick search:</span>
            {quickSearches.map(function(item, idx) {
              return (
                <button
                  key={idx}
                  type="button"
                  className="chip"
                  onClick={function() {
                    setSearchQuery(item);
                    onSearch(item);
                  }}
                >
                  {item}
                </button>
              );
            })}
          </div>
        </div>

        <div className="hero-stats">
          <div className="stat-item">
            <div className="stat-num">3,500+</div>
            <div className="stat-label">Government Schemes</div>
          </div>
          <div className="stat-item">
            <div className="stat-num">Instant</div>
            <div className="stat-label">Eligibility Matching</div>
          </div>
          <div className="stat-item">
            <div className="stat-num">Direct</div>
            <div className="stat-label">Official Portal Links</div>
          </div>
        </div>
      </div>
    </section>
  );
}
