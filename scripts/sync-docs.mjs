#!/usr/bin/env node
/**
 * Pull pages from master's docs/ into the site. docs/ on master stays the single source of
 * truth; this branch only holds the site and this mapping.
 *
 * - DOCS_SOURCE: path to a checkout of docs/ (CI: source/docs; locally: ../credit-risk-ml-system/docs)
 * - SOURCE_SHA:  commit the pages were built from (shown in the footer for reproducibility)
 *
 * Per page: the first "# Heading" becomes the frontmatter title, relative links to other synced
 * pages become site links, links to anything else in the repo go to GitHub, images are copied
 * to public/, and ```mermaid fences become <pre class="mermaid"> for the client-side renderer.
 */
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, normalize, posix, relative, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = resolve(SITE, process.env.DOCS_SOURCE ?? "../credit-risk-ml-system/docs");
const BASE = "/credit-risk-ml-system";
const REPO = "https://github.com/ngnquanq/credit-risk-ml-system";
const OUT = join(SITE, "src/content/docs/synced");
const ASSETS = join(SITE, "public/docs-assets");

/** docs/ path -> site slug (files live under src/content/docs/synced; the slug sets the URL). */
export const PAGES = {
  "01-business/business-outcomes.md": "delivery/business-outcomes",
  "architecture/c4/docs/01-overview.md": "architecture/overview",
  "architecture/c4/docs/02-context-and-containers.md": "architecture/context-and-containers",
  "architecture/domain-model.md": "architecture/domain-model",
  "adr/0013-role-based-data-and-explanation-visibility.md": "decisions/0013-role-based-visibility",
  "adr/0014-applicant-personal-data-and-opaque-ids.md": "decisions/0014-personal-data-and-opaque-ids",
  "security/threat-model.md": "security/threat-model",
};

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function rewriteLink(target, fromDoc) {
  if (/^([a-z]+:|#|\/\/)/i.test(target)) return target;
  const [path, anchor] = target.split("#");
  const resolved = posix.normalize(posix.join(posix.dirname(fromDoc), path));
  const hash = anchor ? `#${anchor}` : "";
  if (PAGES[resolved]) return `${BASE}/${PAGES[resolved]}/${hash}`;
  // Anything else in the repository: link to it on GitHub (docs/ is the repo's docs folder).
  const repoPath = posix.normalize(posix.join("docs", resolved));
  if (repoPath.startsWith("..")) return target;
  const kind = /\.[a-z0-9]+$/i.test(repoPath) ? "blob" : "tree";
  return `${REPO}/${kind}/master/${repoPath.replace(/\/$/, "")}${hash}`;
}

function convert(markdown, fromDoc) {
  let title = fromDoc;
  let body = markdown.replace(/^#\s+(.+)\n+/m, (_, h) => {
    title = h.trim();
    return "";
  });
  // Mermaid: HTML block type 1 (<pre>) may contain blank lines, so the diagram survives intact.
  body = body.replace(/```mermaid\n([\s\S]*?)```/g, (_, code) => `<pre class="mermaid">\n${escapeHtml(code)}</pre>`);
  // Images: copy and point at public/.
  body = body.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (match, alt, src) => {
    if (/^[a-z]+:/i.test(src)) return match;
    const rel = posix.normalize(posix.join(posix.dirname(fromDoc), src));
    const from = join(SOURCE, rel);
    if (!existsSync(from)) return match;
    mkdirSync(dirname(join(ASSETS, rel)), { recursive: true });
    cpSync(from, join(ASSETS, rel));
    return `![${alt}](${BASE}/docs-assets/${rel})`;
  });
  // Links (not images).
  body = body.replace(/(?<!!)\[([^\]]+)\]\(([^)\s]+)\)/g, (_, text, target) => `[${text}](${rewriteLink(target, fromDoc)})`);
  return { title, body };
}

function sourceSha() {
  if (process.env.SOURCE_SHA) return process.env.SOURCE_SHA;
  try {
    return execFileSync("git", ["-C", SOURCE, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

rmSync(OUT, { recursive: true, force: true });
rmSync(ASSETS, { recursive: true, force: true });
let count = 0;
for (const [doc, slug] of Object.entries(PAGES)) {
  const file = join(SOURCE, doc);
  if (!existsSync(file)) {
    console.warn(`skip (missing on source): ${doc}`);
    continue;
  }
  const { title, body } = convert(readFileSync(file, "utf8"), doc);
  const front = [
    "---",
    `title: ${JSON.stringify(title)}`,
    `slug: ${slug}`,
    `editUrl: ${REPO}/edit/master/docs/${doc}`,
    "---",
    "",
  ].join("\n");
  const out = join(OUT, normalize(slug) + ".md");
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, front + body);
  count++;
}
const sha = sourceSha();
writeFileSync(join(SITE, "src/synced-meta.json"), JSON.stringify({ sha, syncedAt: new Date().toISOString() }, null, 2));
console.log(`synced ${count} pages from ${relative(SITE, SOURCE)} @ ${sha.slice(0, 7)}`);
