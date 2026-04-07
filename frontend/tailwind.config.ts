import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#05060f",
          soft: "#0b0d22",
          panel: "rgba(18, 21, 45, 0.55)"
        },
        neon: {
          cyan: "#22d3ee",
          violet: "#a855f7",
          pink: "#f472b6",
          lime: "#a3e635"
        }
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"]
      },
      backgroundImage: {
        aurora:
          "radial-gradient(ellipse at 20% 10%, rgba(34,211,238,0.18), transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(168,85,247,0.22), transparent 60%), radial-gradient(ellipse at 60% 80%, rgba(244,114,182,0.15), transparent 60%)"
      },
      boxShadow: {
        neon: "0 0 40px rgba(168,85,247,0.35), 0 0 10px rgba(34,211,238,0.25)"
      },
      animation: {
        "pulse-slow": "pulse 4s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
        shimmer: "shimmer 2.5s linear infinite"
      },
      keyframes: {
        float: {
          "0%,100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" }
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" }
        }
      }
    }
  },
  plugins: []
};

export default config;
