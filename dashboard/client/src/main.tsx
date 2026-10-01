import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "@fontsource/line-seed-jp/400.css";
import "@fontsource/line-seed-jp/700.css";
import "@fontsource/line-seed-jp/800.css";
import { Layout } from "./components/Layout";
import { Commands } from "./pages/Commands";
import { Errors } from "./pages/Errors";
import { Guilds } from "./pages/Guilds";
import { Maintenance } from "./pages/Maintenance";
import { Overview } from "./pages/Overview";
import { Quiz } from "./pages/Quiz";
import "./index.css";

const queryClient = new QueryClient({
	defaultOptions: {
		queries: {
			retry: 1,
			refetchOnWindowFocus: false,
		},
	},
});

createRoot(document.getElementById("root")!).render(
	<StrictMode>
		<QueryClientProvider client={queryClient}>
			<BrowserRouter>
				<Routes>
					<Route element={<Layout />}>
						<Route index element={<Overview />} />
						<Route path="commands" element={<Commands />} />
						<Route path="quiz" element={<Quiz />} />
						<Route path="errors" element={<Errors />} />
						<Route path="guilds" element={<Guilds />} />
						<Route path="maintenance" element={<Maintenance />} />
					</Route>
				</Routes>
			</BrowserRouter>
		</QueryClientProvider>
	</StrictMode>,
);
