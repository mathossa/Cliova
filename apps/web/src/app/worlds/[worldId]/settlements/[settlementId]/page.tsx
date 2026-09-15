import { LocalMapLoader } from "@/features/local-map/local-map-loader";

export default async function SettlementMapPage({
  params,
}: {
  params: Promise<{ worldId: string; settlementId: string }>;
}) {
  const { worldId, settlementId } = await params;
  return <LocalMapLoader worldId={worldId} settlementId={settlementId} />;
}
