import type { Config } from "tailwindcss";

// Hex CSS variables don't support Tailwind's `/opacity` modifier on their own;
// color-mix lets `bg-danger/10`, `border-primary/30`, etc. work with tokens.
const token = (name: string) =>
  `color-mix(in srgb, var(--${name}) calc(<alpha-value> * 100%), transparent)`;

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: token("background"),
        foreground: token("foreground"),
        card: token("card"),
        "card-foreground": token("card-foreground"),
        "surface-raised": token("surface-raised"),
        popover: token("popover"),
        "popover-foreground": token("popover-foreground"),
        primary: token("primary"),
        "primary-foreground": token("primary-foreground"),
        secondary: token("secondary"),
        "secondary-foreground": token("secondary-foreground"),
        muted: token("muted"),
        "muted-foreground": token("muted-foreground"),
        accent: token("accent"),
        "accent-foreground": token("accent-foreground"),
        destructive: token("destructive"),
        "destructive-foreground": token("destructive-foreground"),
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        input: token("input"),
        ring: token("ring"),
        danger: token("danger"),
        warning: token("warning"),
        success: token("success"),
        info: token("info"),
        severity: {
          critical: token("severity-critical"),
          high: token("severity-high"),
          medium: token("severity-medium"),
          low: token("severity-low"),
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};
export default config;
