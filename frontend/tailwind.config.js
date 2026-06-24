/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#f76902", // RIT orange
          dark: "#c95400",
        },
      },
    },
  },
  plugins: [],
};
