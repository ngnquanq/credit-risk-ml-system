// @ts-check
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

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
              themeVariables: dark
                ? { primaryColor: "#27272a", primaryTextColor: "#f4f4f5", primaryBorderColor: "#ef4d63",
                    lineColor: "#a1a1aa", secondaryColor: "#3f1218", tertiaryColor: "#18181b", noteBkgColor: "#3f1218" }
                : { primaryColor: "#ffffff", primaryTextColor: "#111111", primaryBorderColor: "#c8102e",
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
          label: "Technical report",
          badge: { text: "draft", variant: "caution" },
          items: [{ label: "Fairness without the protected attribute", link: "/report/" }],
        },
        {
          label: "Architecture",
          items: [
            { label: "System overview (C4)", link: "/architecture/overview/" },
            { label: "Context and containers", link: "/architecture/context-and-containers/" },
            { label: "Domain model", link: "/architecture/domain-model/" },
          ],
        },
        {
          label: "Decisions (ADRs)",
          items: [
            { label: "0013 · Role-based visibility", link: "/decisions/0013-role-based-visibility/" },
            { label: "0014 · Personal data and opaque ids", link: "/decisions/0014-personal-data-and-opaque-ids/" },
          ],
        },
        { label: "Delivery", items: [{ label: "Business outcomes", link: "/delivery/business-outcomes/" }] },
        { label: "Security", items: [{ label: "Threat model", link: "/security/threat-model/" }] },
        { label: "References", link: "/references/" },
      ],
    }),
    mermaid(),
  ],
});
