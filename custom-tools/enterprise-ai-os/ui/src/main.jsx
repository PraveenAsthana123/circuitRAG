// Vite entrypoint — bootstrap for App.jsx.
// Not in Tool Set 31 source; added so `npm run dev` actually starts.

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
