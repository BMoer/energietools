import type { APIRoute } from "astro";
import { getCollection } from "astro:content";

// On-demand (serverless auf Vercel): zählt den Klick pro Slug hoch und leitet
// dann weiter. Misst INTERESSE (Klicks), nicht Nutzung — bewusst simpel.
export const prerender = false;

export const GET: APIRoute = async ({ params, redirect }) => {
  const slug = params.slug;
  if (!slug) return redirect("/", 302);

  const tool = (await getCollection("tools")).find((t) => t.id === slug);
  if (!tool) return redirect("/", 302);

  // Klick zählen — best effort, darf den Redirect niemals blockieren.
  await bumpCounter(slug).catch(() => {});

  return redirect(tool.data.url, 302);
};

async function bumpCounter(slug: string): Promise<void> {
  // Nur wenn Vercel KV konfiguriert ist (KV_REST_API_URL/_TOKEN). Sonst No-op.
  if (!import.meta.env.KV_REST_API_URL && !process.env.KV_REST_API_URL) return;
  const { kv } = await import("@vercel/kv");
  await kv.incr(`clicks:${slug}`);
}
