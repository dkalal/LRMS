module.exports = {
  content: [
    "../../templates/**/*.html",
    "../../**/templates/**/*.html",
    "../../**/*.py"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f9ff",
          500: "#0f766e",
          600: "#115e59",
          700: "#134e4a"
        }
      }
    }
  },
  plugins: [
    require("@tailwindcss/forms")
  ]
}
