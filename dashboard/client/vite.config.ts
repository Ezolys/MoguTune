import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [react(), tailwindcss()],
	server: {
		port: 5173,
		proxy: {
			// 開発時は FastAPI サーバーへ API をプロキシする
			"/api": {
				target: process.env.VITE_API_TARGET ?? "http://localhost:8787",
				changeOrigin: true,
			},
		},
	},
});
