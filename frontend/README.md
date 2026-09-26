# Sahayak Frontend

React frontend for showcasing the Sahayak welfare scheme app.

## Running the app

If you just want to preview it quickly without installing Node or npm, run:

```bash
python -m http.server 3000
```

Then go to http://localhost:3000 in your browser.

If you have Node installed and want to use Vite:

```bash
npm install
npm run dev
```

## Structure

- `index.html`: Entry page, loads React 18 from CDN so it works out of the box.
- `src/App.jsx`: Main React component managing tabs and state.
- `src/components/EligibilityChecker.jsx`: The interactive eligibility form.
- `src/components/SchemeList.jsx`: Grid of scheme cards with category filters.
- `src/components/SchemeModal.jsx`: Modal popup showing details, documents, and application link.
- `src/components/ArchitectureView.jsx`: Explains how the frontend, Java backend, and Python ML service connect.
- `src/data/schemes.js`: Sample scheme data used for local testing.
- `src/index.css`: Simple styling for the layout and cards.
