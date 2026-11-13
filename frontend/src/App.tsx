import { useState } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { motion, MotionConfig } from "framer-motion";
import { Waypoints } from "lucide-react";
import { useApi } from "./api";
import { ClockContext, Wait } from "./ui";
import { Dashboard } from "./Dashboard";
import { Shipments } from "./Shipments";
import { Analysis } from "./Journey";
import { Performance } from "./Performance";
import type { Metadata } from "./types";
export function App() {
  const meta = useApi<Metadata>("/metadata"),
    [clock, setClock] = useState("");
  const location = useLocation();
  return (
    <MotionConfig reducedMotion="user">
      <div className="shell">
        <nav aria-label="Main navigation">
          <div className="brand">
            <span>
              <Waypoints size={19} />
            </span>
            Shipment ETA Prediction System
          </div>
          <div className="tabs">
            {[
              ["Dashboard", "/dashboard"],
              ["Shipments", "/shipments"],
              ["Delay Analysis", "/delay-analysis"],
              ["Model Performance", "/model-performance"],
            ].map(([name, path]) => (
              <NavLink key={path} to={path}>
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.i
                        className="navpill"
                        layoutId="active-tab"
                        transition={{ duration: 0.18 }}
                      />
                    )}
                    <span>{name}</span>
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </nav>
        <main>
          {!meta.data ? (
            <Wait {...meta} />
          ) : (
            <ClockContext.Provider
              value={{
                meta: meta.data,
                at: clock || meta.data.default_time,
                setAt: setClock,
              }}
            >
              <Routes location={location}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/shipments" element={<Shipments />} />
                <Route path="/shipments/:shipmentId" element={<Shipments />} />
                <Route path="/delay-analysis" element={<Analysis />} />
                <Route path="/model-performance" element={<Performance />} />
                <Route
                  path="*"
                  element={<Navigate to="/dashboard" replace />}
                />
              </Routes>
            </ClockContext.Provider>
          )}
        </main>
        <footer>
          Held-out synthetic shipment journeys <span>All times UTC</span>
        </footer>
      </div>
    </MotionConfig>
  );
}
