import { BrowserRouter, Routes, Route } from "react-router-dom";
import AboutPage from "./AboutPage";
import MinkopsLanding from "./MinkopsLanding";
import TermsOfService from "./TermsOfService";
import PrivacyPolicy from "./PrivacyPolicy";
import CareersPage from "./CareersPage";
import BlogsPage from "./BlogsPage";
import BlogPost1 from "./BlogPost1";
import BlogPost2 from "./BlogPost2";
import BlogPost3 from "./BlogPost3";
import BlogPost4 from "./BlogPost4";
import BlogPost5 from "./BlogPost5";
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
        <Route path="/blogs/auto-lead-generation-agent" element={<BlogPost2 />} />
        <Route path="/blogs/what-is-an-ai-employee" element={<BlogPost3 />} />
        <Route path="/blogs/minkowski-home-day-to-day-operations" element={<BlogPost4 />} />
        <Route path="/blogs/myndral-day-to-day-operations" element={<BlogPost5 />} />
        <Route path="/orchestration" element={<OrchestrationPage />} />
        <Route path="*" element={<MinkopsLanding />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
