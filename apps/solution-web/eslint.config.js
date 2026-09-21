import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactPlugin from "eslint-plugin-react";
import hooksPlugin from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import prettierConfig from "eslint-config-prettier";

export default tseslint.config(
  {
    ignores: ["dist", "node_modules", "postcss.config.cjs", "prettier.config.cjs"]
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        project: "./tsconfig.json"
      }
    },
    plugins: {
      react: reactPlugin,
      "react-hooks": hooksPlugin,
      "jsx-a11y": jsxA11y
    },
    settings: {
      react: {
        version: "detect"
      }
    },
    rules: {
      ...reactPlugin.configs.recommended.rules,
      ...reactPlugin.configs["jsx-runtime"].rules,
      ...hooksPlugin.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "react/react-in-jsx-scope": "off",
      "react/no-unescaped-entities": "off",
      "react/jsx-no-comment-textnodes": "off"
    }
  },
  prettierConfig
);
