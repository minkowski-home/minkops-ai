import { BrowserRouter, Routes, Route } from "react-router-dom";
import AboutPage from "./AboutPage";
import MinkopsLanding from "./MinkopsLanding";
import TermsOfService from "./TermsOfService";
import PrivacyPolicy from "./PrivacyPolicy";
import CareersPage from "./CareersPage";
import BlogsPage from "./BlogsPage";
import BlogPost1 from "./BlogPost1";
import OrchestrationPage from "./OrchestrationPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MinkopsLanding />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/terms" element={<TermsOfService />} />
        <Route path="/privacy" element={<PrivacyPolicy />} />
        <Route path="/careers" element={<CareersPage />} />
        <Route path="/blogs" element={<BlogsPage />} />
        <Route path="/blogs/minkowski-case-study" element={<BlogPost1 />} />
        <Route path="/orchestration" element={<OrchestrationPage />} />
        <Route path="*" element={<MinkopsLanding />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
