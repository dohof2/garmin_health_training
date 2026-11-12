import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import {installLightDismiss} from "./lightDismiss";
installLightDismiss();
import "leaflet/dist/leaflet.css";
import "./styles.css";
import "./command.css";
import "./journal.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
