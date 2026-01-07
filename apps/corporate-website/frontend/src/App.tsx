import { BrowserRouter, Routes, Route } from "react-router-dom";
import AboutPage from "./AboutPage";
import MinkopsLanding from "./MinkopsLanding";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MinkopsLanding />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<MinkopsLanding />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
