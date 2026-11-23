// @ts-check
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

const slugs = (items) => items.map(([slug, label]) => ({ slug, ...(label ? { label } : {}) }));

/** Renders <pre class="mermaid"> blocks in the browser, re-themed for light and dark mode. */
function mermaid() {
  return {
    name: "crs-mermaid",
    hooks: {
      "astro:config:setup": ({ injectScript }) => {
        injectScript(
          "page",
          `
          import mermaid from "mermaid";
          const sources = new Map();
          async function render() {
            const blocks = [...document.querySelectorAll("pre.mermaid")];
            if (!blocks.length) return;
            const dark = document.documentElement.dataset.theme === "dark";
            mermaid.initialize({
              startOnLoad: false,
              theme: "base",
              fontFamily: "Be Vietnam Pro, system-ui, sans-serif",
              flowchart: { useMaxWidth: true, nodeSpacing: 36, rankSpacing: 48, padding: 12 },
              sequence: { useMaxWidth: true, actorMargin: 36, messageMargin: 28 },
              themeVariables: dark
                ? { fontSize: "16px", primaryColor: "#27272a", primaryTextColor: "#f4f4f5", primaryBorderColor: "#ef4d63",
                    lineColor: "#a1a1aa", secondaryColor: "#3f1218", tertiaryColor: "#18181b", noteBkgColor: "#3f1218" }
                : { fontSize: "16px", primaryColor: "#ffffff", primaryTextColor: "#111111", primaryBorderColor: "#c8102e",
                    lineColor: "#52525b", secondaryColor: "#fdecee", tertiaryColor: "#f4f4f5", noteBkgColor: "#fdecee" },
            });
            for (const el of blocks) {
              if (!sources.has(el)) sources.set(el, el.textContent);
              el.removeAttribute("data-processed");
              el.textContent = sources.get(el);
            }
            await mermaid.run({ nodes: blocks });
          }
          render();
          new MutationObserver(render).observe(document.documentElement, { attributeFilter: ["data-theme"] });
          `,
        );
      },
    },
  };
}

/** Click any diagram or image in a page to open it full screen: fit / 100% / 200%, drag to pan, Esc to close. */
function zoomViewer() {
  return {
    name: "crs-zoom",
    hooks: {
      "astro:config:setup": ({ injectScript }) => {
        injectScript(
          "page",
          `
          let overlay;
          function build() {
            overlay = document.createElement("div");
            overlay.className = "zoom-overlay";
            overlay.hidden = true;
            overlay.innerHTML = '<div class="zoom-bar"><button data-mode="fit">Fit</button><button data-mode="1">100%</button>' +
              '<button data-mode="2">200%</button><span class="zoom-note">drag to move · Esc to close</span><button data-mode="close">Close</button></div>' +
              '<div class="zoom-stage"></div>';
            document.body.appendChild(overlay);
            overlay.addEventListener("click", (e) => {
              const mode = e.target instanceof HTMLElement ? e.target.dataset.mode : null;
              if (mode === "close" || e.target === overlay) close();
              else if (mode) apply(mode);
            });
            const stage = overlay.querySelector(".zoom-stage");
            let drag = null;
            stage.addEventListener("mousedown", (e) => { drag = [e.clientX, e.clientY, stage.scrollLeft, stage.scrollTop]; stage.classList.add("grabbing"); });
            window.addEventListener("mouseup", () => { drag = null; stage.classList.remove("grabbing"); });
            window.addEventListener("mousemove", (e) => { if (drag) { stage.scrollLeft = drag[2] - (e.clientX - drag[0]); stage.scrollTop = drag[3] - (e.clientY - drag[1]); } });
          }
          function natural(node) {
            if (node instanceof SVGElement) { const vb = node.viewBox.baseVal; return vb && vb.width ? vb.width : node.getBoundingClientRect().width; }
            return node.naturalWidth || node.getBoundingClientRect().width;
          }
          function apply(mode) {
            const node = overlay.querySelector(".zoom-stage").firstElementChild;
            if (!node) return;
            node.style.maxWidth = "none";
            node.style.height = "auto";
            node.style.width = mode === "fit" ? "100%" : (natural(node) * Number(mode)) + "px";
          }
          function close() { overlay.hidden = true; overlay.querySelector(".zoom-stage").replaceChildren(); document.body.classList.remove("zoom-open"); }
          function open(source) {
            if (!overlay) build();
            const copy = source.cloneNode(true);
            copy.removeAttribute("id");
            const stage = overlay.querySelector(".zoom-stage");
            stage.replaceChildren(copy);
            overlay.hidden = false;
            document.body.classList.add("zoom-open");
            apply("fit");
            stage.scrollTo(0, 0);
          }
          document.addEventListener("click", (e) => {
            const t = e.target instanceof Element ? e.target : null;
            if (!t || t.closest(".zoom-overlay") || t.closest("a")) return;
            // The whole diagram block is the click target, so the visible "Expand" label works too.
            const block = t.closest("pre.mermaid");
            const figure = t.closest(".zoomable-figure");
            const img = t.closest(".sl-markdown-content img");
            const svg = block && block.querySelector("svg");
            if (svg) open(svg);
            else if (figure && figure.querySelector("img")) open(figure.querySelector("img"));
            else if (img) open(img);
          });
          document.addEventListener("keydown", (e) => { if (e.key === "Escape" && overlay && !overlay.hidden) close(); });
          `,
        );
      },
    },
  };
}

export default defineConfig({
  site: "https://ngnquanq.github.io",
  base: "/credit-risk-ml-system",
  integrations: [
    starlight({
      title: "Credit Risk Decisioning Platform",
      description:
        "An open, end-to-end reference for explainable, fair and auditable credit decisions: from change-data capture to a human reviewer.",
      logo: { src: "./src/assets/logo.svg", replacesTitle: false },
      favicon: "/favicon.svg",
      social: [{ icon: "github", label: "GitHub", href: "https://github.com/ngnquanq/credit-risk-ml-system" }],
      customCss: [
        "@fontsource/be-vietnam-pro/400.css",
        "@fontsource/be-vietnam-pro/500.css",
        "@fontsource/be-vietnam-pro/600.css",
        "@fontsource/be-vietnam-pro/700.css",
        "@fontsource/jetbrains-mono/400.css",
        "./src/styles/theme.css",
      ],
      components: { Footer: "./src/components/Footer.astro" },
      lastUpdated: false,
      sidebar: [
        { label: "Start here", items: [{ label: "Overview", link: "/" }] },
        {
          // Mirrors the table of contents of the project README. Pages keep only the README's heading for now.
          label: "Project guide",
          items: [
            ...slugs([
              ["guide/business-objective"],
              ["guide/results"],
              ["architecture/at-a-glance", "Architecture"],
              ["guide/quick-start-ml-only"],
              ["guide/prerequisites"],
              ["guide/local-development-no-kubernetes"],
            ]),
            {
              label: "Full stack deployment",
              collapsed: true,
              items: slugs([
                ["guide/full-stack-deployment", "Overview"],
                ["guide/full-stack-deployment/phase-1-cluster"],
                ["guide/full-stack-deployment/phase-2-build-images"],
                ["guide/full-stack-deployment/phase-3-core-data-platform"],
                ["guide/full-stack-deployment/phase-4-stream-processing"],
                ["guide/full-stack-deployment/phase-5-warehouse-load"],
                ["guide/full-stack-deployment/phase-6-ml-platform"],
                ["guide/full-stack-deployment/phase-7-training-infrastructure"],
                ["guide/full-stack-deployment/phase-8-observability"],
                ["guide/full-stack-deployment/phase-9-port-forwards"],
              ]),
            },
            ...slugs([
              ["guide/verify-end-to-end"],
              ["guide/project-structure"],
              ["guide/testing"],
              ["guide/performance-optimization-log"],
              ["guide/troubleshooting"],
              ["guide/operations"],
              ["guide/dataset"],
              ["guide/notebooks"],
              ["guide/future-development"],
              ["guide/reference"],
              ["guide/assumptions"],
              ["guide/license"],
            ]),
          ],
        },
        {
          label: "Architecture (C4)",
          items: [
            ...slugs([
              ["architecture/at-a-glance", "At a glance"],
              ["architecture/c4/context", "Level 1 · Context"],
              ["architecture/c4/containers", "Level 2 · Containers"],
              ["architecture/c4/components", "Level 3 · Components"],
              ["architecture/c4/flows", "Runtime flows"],
              ["architecture/c4/deployment", "Deployment"],
              ["architecture/domain-model", "Domain model"],
              ["architecture/model-bundling-pipeline", "Model bundling pipeline"],
            ]),
            {
              label: "Full reference",
              collapsed: true,
              items: slugs([
                ["architecture/reference/c4-guide", "How the C4 model is built"],
                ["architecture/reference/overview", "1 · Overview"],
                ["architecture/reference/context-and-containers", "2 · Context and containers"],
                ["architecture/reference/components", "3 · Components"],
                ["architecture/reference/runtime-sequences", "4 · Runtime sequences"],
                ["architecture/reference/data-flow", "5 · Data flow"],
                ["architecture/reference/deployment", "6 · Deployment"],
                ["architecture/reference/findings", "7 · Findings"],
                ["architecture/system-overview-summary", "Short summary (superseded)"],
              ]),
            },
          ],
        },
        {
          label: "Decisions (ADRs)",
          collapsed: true,
          items: slugs([
            ["decisions/index", "About ADRs"],
            ["decisions/0001-clickhouse-data-warehouse", "0001 · ClickHouse warehouse"],
            ["decisions/0002-event-driven-kafka", "0002 · Event-driven with Kafka"],
            ["decisions/0003-feast-feature-store", "0003 · Feast feature store"],
            ["decisions/0004-kserve-bentoml-serving", "0004 · KServe and BentoML"],
            ["decisions/0005-kubernetes", "0005 · Kubernetes"],
            ["decisions/0007-flink-stream-processing", "0007 · Flink"],
            ["decisions/0008-load-test-fixes", "0008 · Load-test fixes"],
            ["decisions/0009-training-and-promotion", "0009 · Training and promotion"],
            ["decisions/0010-knative-sequence-scoring", "0010 · Knative scoring sequence"],
            ["decisions/0011-monorepo-layout", "0011 · Monorepo layout"],
            ["decisions/0012-keycloak-and-bff-portals", "0012 · Keycloak and portals"],
            ["decisions/0013-role-based-visibility", "0013 · Role-based visibility"],
            ["decisions/0014-personal-data-and-opaque-ids", "0014 · Personal data and opaque ids"],
          ]),
        },
        {
          label: "Security and audit",
          collapsed: true,
          items: slugs([
            ["security/threat-model", "Threat model"],
            ["security/e9-security-baseline", "API security baseline"],
            ["security/e11-identity-access", "Identity and access"],
            ["security/e12-portals", "Portals"],
            ["security/e13-audit-trail", "Audit trail"],
            ["security/e14-explainability", "Explainability"],
          ]),
        },
        {
          label: "Machine learning",
          collapsed: true,
          items: [
            { label: "Technical report", slug: "report", badge: { text: "draft", variant: "caution" } },
            ...slugs([
              ["ml/data-definition", "Data definition"],
              ["ml/modeling-references", "Modeling references"],
              ["delivery/e2-feature-catalog", "Feature catalog and parity"],
              ["delivery/e3-readiness", "Exactly-once readiness"],
              ["delivery/e5-decision-delivery", "Decision delivery"],
              ["delivery/e6-governed-model", "Fair, governed model"],
              ["delivery/feature-governance-plan", "Feature governance plan"],
            ]),
          ],
        },
        {
          label: "Delivery",
          collapsed: true,
          items: slugs([
            ["delivery/business-outcomes", "Business outcomes"],
            ["delivery/business-constraints", "Business constraints"],
            ["delivery/epics", "Epics"],
            ["delivery/handoff-index", "Handoff packages"],
          ]),
        },
        {
          label: "Operations",
          collapsed: true,
          items: slugs([
            ["ops/e15-resilience-failover", "Resilience and failover"],
            ["ops/e16-uat-release", "UAT and release"],
            ["ops/release-checklist", "Release checklist"],
            ["ops/uat-signoff-template", "UAT sign-off template"],
            ["ops/runbooks", "Runbooks"],
            ["ops/runbook-db-failover", "Runbook · Database failover"],
            ["ops/runbook-dlq-redrive", "Runbook · Dead-letter redrive"],
            ["ops/runbook-kafka-broker-lost", "Runbook · Kafka broker lost"],
            ["ops/runbook-keycloak-down", "Runbook · Keycloak down"],
            ["ops/runbook-scoring-down", "Runbook · Scoring down"],
          ]),
        },
        { label: "References", slug: "references" },
      ],
    }),
    mermaid(),
    zoomViewer(),
  ],
});
