import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { POSTS } from "./content/posts";
import SiteLayout from "./layout/SiteLayout";
import AboutPage from "./pages/AboutPage";
import BlogIndexPage from "./pages/BlogIndexPage";
import CareersPage from "./pages/CareersPage";
import LandingPage from "./pages/LandingPage";
import { PrivacyPolicyPage, TermsOfServicePage } from "./pages/LegalPages";
import NotFoundPage from "./pages/NotFoundPage";
import OrchestrationPage from "./pages/OrchestrationPage";
import AutoLeadGeneration from "./pages/blog/AutoLeadGeneration";
import MinkowskiHomeWeek from "./pages/blog/MinkowskiHomeWeek";
import MyndralOperations from "./pages/blog/MyndralOperations";
import WhatIsAnAiEmployee from "./pages/blog/WhatIsAnAiEmployee";

/**
 * Posts that were unpublished. Their URLs may still be linked or indexed, so
 * they redirect to the blog index rather than falling through to the 404.
 */
const RETIRED_POST_SLUGS = ["minkowski-case-study"] as const;

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="orchestration" element={<OrchestrationPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="careers" element={<CareersPage />} />
          <Route path="blogs" element={<BlogIndexPage />} />
          <Route
            path={`blogs/${POSTS.whatIsAnAiEmployee.slug}`}
            element={<WhatIsAnAiEmployee />}
          />
          <Route
            path={`blogs/${POSTS.minkowskiHomeWeek.slug}`}
            element={<MinkowskiHomeWeek />}
          />
          <Route
            path={`blogs/${POSTS.myndralOperations.slug}`}
            element={<MyndralOperations />}
          />
          <Route
            path={`blogs/${POSTS.autoLeadGeneration.slug}`}
            element={<AutoLeadGeneration />}
          />
          {RETIRED_POST_SLUGS.map((slug) => (
            <Route
              key={slug}
              path={`blogs/${slug}`}
              element={<Navigate to="/blogs" replace />}
            />
          ))}
          <Route path="terms" element={<TermsOfServicePage />} />
          <Route path="privacy" element={<PrivacyPolicyPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
