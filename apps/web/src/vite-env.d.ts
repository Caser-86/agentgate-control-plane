/// <reference types="vite/client" />

interface Window {
  __AGENTGATE_CONFIG__?: import("./api/client").RuntimeConfig;
}
