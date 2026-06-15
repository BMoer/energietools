import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// Galerie-Eintrag = eine Markdown-Datei in src/content/tools/.
// Frontmatter = Metadaten (Datenmodell laut Briefing), Body = ausführliche
// Beschreibung. Neuer Eintrag = simpler Datei-Commit.
const tools = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/tools" }),
  schema: ({ image }) =>
    z.object({
      name: z.string(),
      operator: z.string(),
      // Lead-Kontakt zum jeweiligen Betreiber — NICHT zentral zum Seitenbetreiber.
      contact: z.string(),
      contactLabel: z.string().optional(),
      description: z.string(),
      hosting: z.enum(["hosted", "external"]),
      // hosted: interner Subpath (z.B. /tools/netzkosten/) · external: fremde Domain
      url: z.string(),
      thumbnail: image().optional(),
      // Vom Autor selbst geschrieben: die Bruchlinie Engine (geteilt) ↔ proprietär.
      // Weil das Repo offen ist, ist diese Angabe nachprüfbar.
      engineUsage: z.string(),
      tags: z.array(z.string()).default([]),
      // Reihenfolge in der Galerie (kleiner = weiter vorne); sonst alphabetisch.
      order: z.number().default(100),
      featured: z.boolean().default(false),
    }),
});

export const collections = { tools };
