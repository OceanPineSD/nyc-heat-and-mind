import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";

// MapLibre v6 loads its worker from a separate module; let Vite bundle it and point MapLibre at it.
maplibregl.setWorkerUrl(workerUrl);

export default maplibregl;
