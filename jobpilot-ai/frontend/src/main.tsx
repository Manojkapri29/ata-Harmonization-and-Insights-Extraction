import { StrictMode, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import { ToastProvider } from "./components/Toast";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const JobSearch = lazy(() => import("./pages/JobSearch"));
const JobMatches = lazy(() => import("./pages/JobMatches"));
const JobDetailPage = lazy(() => import("./pages/JobDetail"));
const ResumePage = lazy(() => import("./pages/Resume"));
const AtsAnalyzer = lazy(() => import("./pages/AtsAnalyzer"));
const Applications = lazy(() => import("./pages/Applications"));
const Outreach = lazy(() => import("./pages/Outreach"));
const Followups = lazy(() => import("./pages/Followups"));
const Analytics = lazy(() => import("./pages/Analytics"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const ImportPage = lazy(() => import("./pages/Import"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="search" element={<JobSearch />} />
            <Route path="matches" element={<JobMatches />} />
            <Route path="jobs/:id" element={<JobDetailPage />} />
            <Route path="resume" element={<ResumePage />} />
            <Route path="ats" element={<AtsAnalyzer />} />
            <Route path="applications" element={<Applications />} />
            <Route path="outreach" element={<Outreach />} />
            <Route path="followups" element={<Followups />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="import" element={<ImportPage />} />
            <Route path="*" element={<div className="py-20 text-center text-slate-500">Page not found.</div>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  </StrictMode>,
);
