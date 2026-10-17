import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Git-ignored data-job cache (see .gitignore). It holds downloaded/vendored scripts that are
    // absent in CI, so linting it would make a local run disagree with the lane that gates a push.
    ".cache/**",
  ]),
]);

export default eslintConfig;
