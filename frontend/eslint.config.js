import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/api/generated", "e2e/shots", "test-results", "playwright-report"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
  {
    /**
     * Money guard.
     *
     * The API sends money, percentages and quantities as decimal strings.
     * Coercing one to a JS number is a correctness bug, not a style choice, so
     * feature code may not do it — `src/api/money.ts` is the only place that
     * converts, and it converts to Decimal.
     */
    files: ["src/features/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "parseFloat", message: "Use dec() from @/api/money — API numerics are decimal strings." },
        { name: "parseInt", message: "Use dec() from @/api/money — API numerics are decimal strings." },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='Number'] > MemberExpression",
          message:
            "Do not coerce an API value with Number(). Use dec()/formatMoney()/formatPct() from @/api/money.",
        },
      ],
    },
  },
);
