import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import SnipOverlay from "./SnipOverlay";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SnipOverlay />
  </StrictMode>,
);
