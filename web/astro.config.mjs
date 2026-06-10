// @ts-check
import { defineConfig } from "astro/config";
import vercel from "@astrojs/vercel";

// Statisch generierte Galerie; einzelne Routen (der /go-Klickzähler) laufen
// on-demand serverless auf Vercel (siehe `prerender = false` im Endpoint).
export default defineConfig({
  site: "https://energietools.at",
  output: "static",
  adapter: vercel(),
});
