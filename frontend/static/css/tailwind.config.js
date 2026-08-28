/**
 * Config do Tailwind (build estático).
 *
 * Extraída de frontend/templates/base.html — deve permanecer idêntica à
 * configuração que era usada pelo Play CDN para não alterar o visual.
 * Ao mudar a paleta/aqui, rodar: frontend/build-tailwind.sh
 */
module.exports = {
    // Caminhos relativos a frontend/static/css (onde o CLI é executado).
    content: [
        "../../../apps/**/templates/**/*.html",
        "../../../apps/**/*.py",
        "../../templates/**/*.html",
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
            },
            colors: {
                navy: {
                    50: "#f0f4fa",
                    100: "#dce5f2",
                    500: "#2d4a86",
                    600: "#22396b",
                    700: "#0a2a52",
                    800: "#06203f",
                    900: "#001B3D",
                    950: "#00112a",
                },
                brand: {
                    50: "#e8f3ff",
                    100: "#d5e9ff",
                    500: "#0a8afb",
                    600: "#0878F9",
                    700: "#0665d4",
                },
            },
        },
    },
};
