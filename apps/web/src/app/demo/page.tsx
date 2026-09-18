import type { Metadata } from "next";
import { DemoDashboard } from "./DemoDashboard";

export const metadata: Metadata = {
  title: "Demo panel (sentetik veri)",
  description:
    "VisiOnRoute genel bakış panelinin salt okunur önizlemesi. Tüm araçlar, sürücüler, konumlar ve olaylar kurgusal ve sentetiktir.",
};

export default function DemoPage() {
  return <DemoDashboard />;
}
