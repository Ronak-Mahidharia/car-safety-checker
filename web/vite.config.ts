import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// The built page may only load its own files and call NHTSA's API: no other servers,
// no inline scripts or styles, no plugins, and no form posts.
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "connect-src 'self' https://api.nhtsa.gov",
  "img-src 'self' data:",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

// Added to the built page only: the development server needs inline scripts for live reloading.
function contentSecurityPolicy(): Plugin {
  return {
    name: "content-security-policy",
    apply: "build",
    transformIndexHtml: (html) => {
      const charset = '<meta charset="UTF-8" />';
      if (!html.includes(charset)) throw new Error("index.html must declare its charset");
      return html.replace(charset, `${charset}\n    <meta http-equiv="Content-Security-Policy" content="${CONTENT_SECURITY_POLICY}" />`);
    },
  };
}

export default defineConfig({
  plugins: [react(), contentSecurityPolicy()],
  test: { environment: "node" },
});
