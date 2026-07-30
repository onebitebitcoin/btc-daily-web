/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
  // Preflight resets line-height to 1.5, which changes the ported deck layout
  // (badge/meta/hint heights) away from the static original. deck.css is the
  // design's only reset; utilities still work without it.
  corePlugins: { preflight: false },
};
