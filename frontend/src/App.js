import React from "react";
import "@/App.css";
import { BrowserRouter, Route, Routes, useParams } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { LangProvider } from "@/lib/lang";
import Landing from "@/pages/Landing";
import HostSetup from "@/pages/HostSetup";
import HostConsole from "@/pages/HostConsole";
import BigScreen from "@/pages/BigScreen";
import Join from "@/pages/Join";
import Play from "@/pages/Play";
import WrongCode from "@/pages/WrongCode";

function Keyed({ C }) {
  const { code } = useParams();
  return <C key={code} />;
}

export default function App() {
  return (
    <LangProvider>
      <div className="App">
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/host" element={<HostSetup />} />
            <Route path="/host/:code" element={<Keyed C={HostConsole} />} />
            <Route path="/screen/:code" element={<Keyed C={BigScreen} />} />
            <Route path="/join/:code" element={<Keyed C={Join} />} />
            <Route path="/play/:code" element={<Keyed C={Play} />} />
            <Route path="*" element={<WrongCode />} />
          </Routes>
        </BrowserRouter>
        <Toaster
          position="top-center"
          visibleToasts={3}
          closeButton
          toastOptions={{
            style: { background: "var(--hh-raised)", color: "var(--hh-text)", border: "1px solid var(--hh-line)", borderRadius: 0, fontFamily: "inherit", fontWeight: 500 },
          }}
        />
      </div>
    </LangProvider>
  );
}
