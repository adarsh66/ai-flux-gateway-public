import { useSession } from "../session";
import { ApiError } from "../client";
import { AsyncView, Badge, useAsync } from "./ui";
import { DisplayPriceDetails } from "./DisplayPrice";

/** Discovery is separate from the accepted chat list; never offers a Play action. */
export function DeploymentStatus() {
  const { api } = useSession();
  const state = useAsync(async () => {
    try {
      const deployments = await api.modelDeployments();
      const garden = await api.modelGarden();
      return { ...deployments, items: deployments.items.map(m => ({
        ...m, display_price: garden.items.find(g => g.id === m.id)?.display_price,
      })) };
    } catch (error) {
      // Compatibility with the existing API image. Admin-managed metadata is
      // not a replacement for fresh ARM evidence or route acceptance.
      if (!(error instanceof ApiError) || error.status !== 404) throw error;
      const garden = await api.modelGarden();
      return {
        verified_at: "Unavailable from this API version; showing admin-managed metadata only",
        auto_enabled: false,
        items: garden.items.map((m) => ({
          id: m.id, provider: m.vendor, model_name: m.backend_model,
          model_version: "Not exposed by this API version",
          role: m.capabilities.includes("routing-only") ? "routing-only" : "chat",
          status: m.capabilities.includes("routing-only") ? "integration-unavailable" : "admin-managed metadata",
          chat_selectable: m.enabled && !m.coming_soon && m.capabilities.includes("chat"),
          pricing_status: "unknown", limitation: m.description,
          display_price: m.display_price,
        })),
      };
    }
  }, [api]);
  return <section aria-label="Verified deployment inventory">
    <h2>Deployment and gateway status</h2>
    <p>Deployment does not publish a gateway route. Auto-routing is unavailable until its actual integration is verified; a keyword simulator is not Decision-1 inference.</p>
    <p>Sourced display estimates are not invoices or a monetary-ledger guarantee. Unavailable prices are not free.</p>
    <AsyncView state={state} isEmpty={(d) => d.items.length === 0} emptyTitle="No verified deployments" emptyHint="An operator must refresh inventory.">
      {(d) => <><p>Inventory verified: {d.verified_at}</p><ul className="cards">{d.items.map((m) => <li className="card" key={m.id}>
        <h3>{m.id}</h3><p>{m.provider} · {m.model_name} · {m.model_version}</p>
        <Badge tone={m.chat_selectable ? "info" : "warn"}>{m.status}</Badge> <Badge tone="info">{m.role}</Badge>
        <DisplayPriceDetails price={m.display_price} />
        {"credential_healthy" in m && <p>External credential verification: {m.credential_healthy ? "Healthy at last accepted probe" : "Pending — external route unavailable"}</p>}
        {m.limitation && <p>{m.limitation}</p>}
      </li>)}</ul></>}
    </AsyncView>
  </section>;
}